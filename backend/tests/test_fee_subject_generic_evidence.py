"""通用费用科目检索 + 证据对齐（非写死销售费用/华清单句）。"""

from __future__ import annotations

from backend.services.agent_kb_supplemental import (
    choose_supplemental_reply,
    evidence_constraint_addon,
    hermes_reply_needs_breakdown_revise,
)
from backend.services.evidence_reply_align import (
    reply_has_contradictory_change_reason,
    reply_has_derived_breakdown_amounts,
)
from backend.services.kb_retrieval_plan import TaskType, fee_subjects_from_query, plan_retrieval_queries
from backend.services import knowledge_pipeline as kp
from backend.services.hermes_stream_sanitize import (
    enforce_breakdown_compare_reply,
    finalize_agent_reply,
    strip_inline_source_markers,
)


RD_QUERY = "出一份华清25、24两年研发费用明细的对比分析报告"
MGMT_QUERY = "出一份华清25、24两年管理费用明细的对比分析报告"
SALES_QUERY = "出一份华清25、24两年销售费用明细的对比分析报告"


def test_fee_subjects_from_query_any_period_fee():
    assert fee_subjects_from_query(RD_QUERY) == ["研发费用"]
    assert fee_subjects_from_query(MGMT_QUERY) == ["管理费用"]
    assert fee_subjects_from_query(SALES_QUERY) == ["销售费用"]
    assert fee_subjects_from_query("成本下降明细对比") == []


def test_plan_breakdown_uses_query_fee_subject_not_only_sales():
    rd_qs = plan_retrieval_queries(RD_QUERY, TaskType.breakdown, entity="华清")
    joined_rd = " ".join(rd_qs)
    assert "研发费用" in joined_rd
    assert "销售费用" not in joined_rd or "研发费用" in rd_qs[1]
    assert any("## 研发费用" in q for q in rd_qs)

    mgmt_qs = plan_retrieval_queries(MGMT_QUERY, TaskType.breakdown, entity="华清")
    assert any("管理费用" in q for q in mgmt_qs)
    assert not any(q == "华清 ## 销售费用" for q in mgmt_qs)


def test_plan_generic_breakdown_still_has_default_subjects():
    qs = plan_retrieval_queries("成本下降明细对比", TaskType.breakdown, entity="华清")
    joined = " ".join(qs)
    assert "销售费用" in joined
    assert "管理费用" in joined


def test_is_fee_appendix_chunk_matches_rd_section():
    rd_appendix = (
        "## 32 、研发费用\n"
        "| 职工薪酬 | 70,863,000.00 | 122,568,000.00 |\n"
        "| 折旧 | 1,200,000.00 | 1,800,000.00 |\n"
    )
    sales_appendix = (
        "## 31 、销售费用\n| 职工薪酬 | 10,802,366.11 | 23,295,127.31 |\n"
    )
    assert kp.is_fee_appendix_chunk(rd_appendix, query=RD_QUERY)
    assert not kp.is_fee_appendix_chunk(sales_appendix, query=RD_QUERY)
    assert kp.is_fee_appendix_chunk(sales_appendix, query=SALES_QUERY)


def test_rd_appendix_scores_above_unrelated_notes():
    q = RD_QUERY
    terms = kp._expand_retrieval_terms(kp._tokenize_query(q), q)
    assert "## 研发费用" in terms
    notes = "## 审计报告附注\n税率说明。\n" * 3
    rd = "## 32 、研发费用\n| 职工薪酬 | 70,863,000.00 | 122,568,000.00 |\n"
    s_notes = kp._score_chunk_for_retrieval(notes, terms, q)
    s_rd = kp._score_chunk_for_retrieval(rd, terms, q)
    assert s_rd > s_notes


def test_reply_has_derived_breakdown_amounts_generic():
    derived = (
        "2025年职工薪酬 70,863,000.00，系根据2024年总额减去变动额计算得出："
        "122,568,000.00 - 51,705,000.00 = 70,863,000.00"
    )
    direct = "职工薪酬 70,863,000.00 122,568,000.00"
    assert reply_has_derived_breakdown_amounts(derived)
    assert not reply_has_derived_breakdown_amounts(direct)


def test_reply_contradictory_change_reason():
    bad = (
        "#### 3. 变动原因\n\n证据未提供变动原因说明，仅列示金额与分项对比。\n\n"
        "#### 4. 说明\n\n主要是由于人员减少，职工薪酬减少 5,170.50 万元。"
    )
    good = "变动原因：主要是由于人员减少，职工薪酬减少 5,170.50 万元。"
    assert reply_has_contradictory_change_reason(bad)
    assert not reply_has_contradictory_change_reason(good)


def test_enforce_strips_derived_line_items():
    raw = (
        "结论：研发费用合计 120,565,207.54 元。\n\n"
        "| 项目 | 2025 | 2024 |\n| 职工薪酬 | 70,863,000.00 | 122,568,000.00 |\n\n"
        "*(注：2025年职工薪酬系根据2024年减去变动额计算得出)*\n"
    )
    out = enforce_breakdown_compare_reply(raw, user_query=RD_QUERY)
    assert "计算得出" not in out
    assert "70,863,000.00" not in out
    assert "反推" in out or "费用明细说明" in out or "无法按科目" in out or "勿采信" in out


def test_strip_doc_id_backtick_from_reply():
    raw = "说明见 doc_id: `ud_0401544fb6f7425092db1d9f7a970917` 与正文。"
    assert "doc_id:" not in strip_inline_source_markers(raw)
    fin = finalize_agent_reply(raw, user_query=RD_QUERY, tier2_native=False)
    assert "ud_0401544fb6f7425092db1d9f7a970917" not in fin


def test_hermes_needs_revise_when_false_kb_denial():
    pack = {
        "task_type": "breakdown",
        "facets": [{"excerpt": "研发费用 120,565,207.54 172,697,867.39 职工薪酬"}],
    }
    hermes = "知识库中不包含研发费用的详细数据，无法提供研发费用的对比分析报告。"
    assert hermes_reply_needs_breakdown_revise(
        hermes,
        prefetch_result={"evidence_pack": pack, "ok": True},
        user_query=RD_QUERY,
    )


def test_hermes_needs_revise_on_derived_amounts():
    pack = {
        "task_type": "breakdown",
        "facets": [
            {
                "excerpt": "研发费用 120,565,207.54 172,697,867.39 职工薪酬 122,568,000.00",
            }
        ],
    }
    hermes = (
        "| 职工薪酬 | 70,863,000.00 | 122,568,000.00 |\n"
        "*(计算得出：122,568,000.00 - 51,705,000.00)*"
    )
    assert hermes_reply_needs_breakdown_revise(
        hermes,
        prefetch_result={"evidence_pack": pack},
        user_query=RD_QUERY,
    )


def test_choose_supplemental_rejects_synth_with_derived_amounts():
    pack = {
        "facets": [
            {"excerpt": "研发费用 120,565,207.54 172,697,867.39"},
        ]
    }
    hermes = "结论：研发费用 120,565,207.54 元，172,697,867.39 元。"
    synth_derived = (
        "| 职工薪酬 | 70,863,000.00 | 122,568,000.00 |\n"
        "*(计算得出)*"
    )
    final, adopted, reason = choose_supplemental_reply(
        hermes_reply=hermes,
        synth_reply=synth_derived,
        prefetch_result={"evidence_pack": pack},
    )
    assert adopted is False
    assert reason == "reject_synth_derived_amounts"
    assert "120,565,207.54" in final


def test_evidence_constraint_mentions_no_derived():
    addon = evidence_constraint_addon(tier="lite")
    assert "计算得出" in addon
    assert "反推" in addon
