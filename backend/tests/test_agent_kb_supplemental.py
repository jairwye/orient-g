"""Hermes 未 MCP 补检索时，Orient-G 自动补检索与修订。"""

from __future__ import annotations

from unittest.mock import patch

from backend.services.agent_kb_router import AgentRoute
from backend.services.agent_kb_supplemental import (
    hermes_orientg_kb_ask_count,
    hermes_reply_sufficient_against_pack,
    needs_hermes_supplemental,
    plan_supplemental_queries,
    prefetch_defers_hermes_draft_to_process,
    supplemental_max_queries_for_route,
)


PREFETCH_BREAKDOWN = {
    "ok": True,
    "citations": [{"doc_id": "d1"}],
    "evidence_pack": {
        "task_type": "breakdown",
        "coverage_score": 1.0,
        "retrieval_queries": ["出一份可比E销售费用明细"],
        "gaps": [],
    },
}


def test_needs_supplemental_when_hermes_zero_kb_ask():
    assert needs_hermes_supplemental(
        agent_route=AgentRoute.hermes_lite,
        prefetch_result=PREFETCH_BREAKDOWN,
        hermes_kb_ask_count=0,
        hermes_reply="",
        user_query="可比E销售费用",
    )
    assert not needs_hermes_supplemental(
        agent_route=AgentRoute.hermes_full,
        prefetch_result=PREFETCH_BREAKDOWN,
        hermes_kb_ask_count=2,
        hermes_reply="",
        user_query="可比E销售费用",
    )
    assert not needs_hermes_supplemental(
        agent_route=AgentRoute.fast,
        prefetch_result=PREFETCH_BREAKDOWN,
        hermes_kb_ask_count=0,
    )


def test_tier2_supplemental_when_hermes_estimates_and_pack_has_breakdown():
    from backend.services.evidence_reply_align import pack_has_tabular_breakdown

    pack = {
        **PREFETCH_BREAKDOWN["evidence_pack"],
        "facets": [
            {
                "label": "附注",
                "excerpt": "职工薪酬 10,802,366.11 市场及推广 2,889,547.75 合计 13,722,360.23",
            }
        ],
    }
    prefetch = {**PREFETCH_BREAKDOWN, "evidence_pack": pack}
    assert pack_has_tabular_breakdown(pack)
    bad_hermes = (
        "| 销售费用 | 13,722,360.23 | 25,081,092.51 |\n"
        "#### 2. 费用变动分析\n人员薪酬减少约 500-600 万元。\n"
    )
    assert needs_hermes_supplemental(
        agent_route=AgentRoute.hermes_full,
        prefetch_result=prefetch,
        hermes_kb_ask_count=0,
        hermes_reply=bad_hermes,
        user_query="出一份可比E25、24两年销售费用明细的对比分析报告",
    )


def test_tier2_no_supplemental_when_hermes_has_exact_line_items():
    pack = {
        **PREFETCH_BREAKDOWN["evidence_pack"],
        "facets": [
            {
                "label": "附注",
                "excerpt": "职工薪酬 10,802,366.11 市场及推广 2,889,547.75 合计 13,722,360.23",
            }
        ],
    }
    prefetch = {**PREFETCH_BREAKDOWN, "evidence_pack": pack}
    good = (
        "| 销售费用 | 13,722,360.23 | 25,081,092.51 |\n"
        "职工薪酬 10,802,366.11 市场及推广 2,889,547.75\n"
    )
    assert not needs_hermes_supplemental(
        agent_route=AgentRoute.hermes_full,
        prefetch_result=prefetch,
        hermes_kb_ask_count=0,
        hermes_reply=good,
        user_query="出一份可比E25、24两年销售费用明细的对比分析报告",
    )


def test_lite_skips_supplemental_when_pack_and_hermes_sufficient():
    pack = {
        **PREFETCH_BREAKDOWN["evidence_pack"],
        "task_type": "compare",
        "coverage_score": 1.0,
        "facets": [
            {
                "label": "附注",
                "excerpt": "职工薪酬 10,802,366.11 市场及推广 2,889,547.75 合计 13,722,360.23",
            }
        ],
    }
    prefetch = {**PREFETCH_BREAKDOWN, "evidence_pack": pack}
    good = (
        "结论：2025 年销售费用较 2024 年下降。\n"
        "| 销售费用 | 13,722,360.23 | 25,081,092.51 |\n"
        "职工薪酬 10,802,366.11 市场及推广 2,889,547.75\n"
    )
    assert hermes_reply_sufficient_against_pack(
        good, prefetch_result=prefetch, user_query="可比E25、24两年销售费用明细对比"
    )
    assert not needs_hermes_supplemental(
        agent_route=AgentRoute.hermes_lite,
        prefetch_result=prefetch,
        hermes_kb_ask_count=0,
        hermes_reply=good,
        user_query="可比E25、24两年销售费用明细对比",
    )


def test_tier2_no_supplemental_when_only_speculation():
    pack = {
        **PREFETCH_BREAKDOWN["evidence_pack"],
        "task_type": "compare",
        "coverage_score": 1.0,
        "facets": [
            {
                "label": "附注",
                "excerpt": "职工薪酬 30,678,824.83 折旧 7,624,220.17 合计 44,933,044.34",
            }
        ],
    }
    prefetch = {**PREFETCH_BREAKDOWN, "evidence_pack": pack}
    hermes = (
        "结论：2025 年管理费用较 2024 年下降。\n"
        "| 管理费用 | 44,933,044.34 | 52,950,207.05 |\n"
        "职工薪酬 30,678,824.83 折旧 7,624,220.17\n"
        "4.变动原因\n"
        "* **原因**：可能系公司减少了审计、法律或咨询等外部专业服务采购。\n"
        "5.盈利能力影响\n"
        "管理费用率下降，有利于提升净利率。\n"
    )
    assert not needs_hermes_supplemental(
        agent_route=AgentRoute.hermes_full,
        prefetch_result=prefetch,
        hermes_kb_ask_count=0,
        hermes_reply=hermes,
        user_query="出一份可比E25、24两年管理费用明细的对比分析报告",
    )


def test_choose_supplemental_keeps_hermes_when_synth_denies_reason_but_hermes_has_narrative():
    from backend.services.agent_kb_supplemental import choose_supplemental_reply

    pack = {
        "facets": [
            {"excerpt": "职工薪酬 30,678,824.83 折旧 7,624,220.17 合计 44,933,044.34"},
        ]
    }
    hermes = (
        "| 管理费用 | 44,933,044.34 | 52,950,207.05 |\n"
        "#### 变动原因\n"
        "年报指出主要是由于人员减少，职工薪酬减少。\n"
    )
    synth = (
        "| 管理费用 | 44,933,044.34 | 52,950,207.05 |\n"
        "变动原因：证据未提供管理费用变动的具体原因说明，仅列示金额与分项对比。\n"
    )
    final, adopted, reason = choose_supplemental_reply(
        hermes_reply=hermes,
        synth_reply=synth,
        prefetch_result={"evidence_pack": pack},
        agent_route=AgentRoute.hermes_lite,
    )
    assert adopted is False
    assert reason == "keep_hermes_has_narrative_reason"
    assert "人员减少" in final


def test_tier2_choose_supplemental_keeps_richer_hermes_over_thin_synth():
    from backend.services.agent_kb_supplemental import choose_supplemental_reply

    pack = {
        "facets": [
            {
                "excerpt": "职工薪酬 30,678,824.83 折旧 7,624,220.17 合计 44,933,044.34",
            }
        ]
    }
    hermes = (
        "结论：2025 年管理费用较 2024 年下降。\n"
        "| 管理费用 | 44,933,044.34 | 52,950,207.05 |\n"
        "职工薪酬 30,678,824.83 折旧 7,624,220.17\n"
        "变动原因：主要系使用权资产减少，租赁面积缩减。\n"
        "盈利能力：费比改善。\n" * 40
    )
    synth = "结论：管理费用下降。\n| 管理费用 | 44,933,044.34 | 52,950,207.05 |"
    final, adopted, reason = choose_supplemental_reply(
        hermes_reply=hermes,
        synth_reply=synth,
        prefetch_result={"evidence_pack": pack},
        agent_route=AgentRoute.hermes_full,
    )
    assert adopted is False
    assert "hermes" in reason
    assert "44,933,044.34" in final
    assert len(final) >= len(synth) * 2


def test_lite_needs_supplemental_when_hermes_has_speculation():
    pack = {
        **PREFETCH_BREAKDOWN["evidence_pack"],
        "task_type": "compare",
        "coverage_score": 1.0,
        "facets": [
            {
                "label": "附注",
                "excerpt": "职工薪酬 30,678,824.83 折旧 7,624,220.17 合计 44,933,044.34",
            }
        ],
    }
    prefetch = {**PREFETCH_BREAKDOWN, "evidence_pack": pack}
    bad = (
        "结论：管理费用下降。\n"
        "| 管理费用 | 44,933,044.34 | 52,950,207.05 |\n"
        "4.变动原因\n"
        "* **原因**：可能系公司减少了审计、法律或咨询等外部专业服务采购。\n"
    )
    assert not hermes_reply_sufficient_against_pack(
        bad, prefetch_result=prefetch, user_query="可比E25、24两年管理费用明细对比"
    )
    assert needs_hermes_supplemental(
        agent_route=AgentRoute.hermes_lite,
        prefetch_result=prefetch,
        hermes_kb_ask_count=0,
        hermes_reply=bad,
        user_query="出一份可比E25、24两年管理费用明细的对比分析报告",
    )


def test_tier2_analyst_short_but_sufficient_skips_supplemental():
    pack = {
        **PREFETCH_BREAKDOWN["evidence_pack"],
        "task_type": "compare",
        "coverage_score": 1.0,
        "facets": [
            {
                "label": "附注",
                "excerpt": "职工薪酬 10,802,366.11 市场及推广 2,889,547.75 合计 13,722,360.23",
            }
        ],
    }
    prefetch = {**PREFETCH_BREAKDOWN, "evidence_pack": pack}
    good = (
        "结论：2025 年销售费用较 2024 年下降。\n"
        "| 销售费用 | 13,722,360.23 | 25,081,092.51 |\n"
        "职工薪酬 10,802,366.11 市场及推广 2,889,547.75\n"
    )
    q = "出一份可比E25、24两年销售费用明细的对比分析报告"
    assert not needs_hermes_supplemental(
        agent_route=AgentRoute.hermes_full,
        prefetch_result=prefetch,
        hermes_kb_ask_count=0,
        hermes_reply=good,
        user_query=q,
    )


def test_supplemental_max_queries_by_route():
    assert supplemental_max_queries_for_route(AgentRoute.hermes_lite) == 5
    assert supplemental_max_queries_for_route(AgentRoute.hermes_full) == 2


def test_plan_supplemental_full_prefers_narrative_and_caps():
    pack = {
        **PREFETCH_BREAKDOWN["evidence_pack"],
        "retrieval_queries": ["出一份可比E销售费用明细"],
    }
    qs = plan_supplemental_queries(
        "可比E25、24两年销售费用明细对比分析报告",
        evidence_pack=pack,
        max_queries=2,
        prefetch_tier="full",
    )
    assert len(qs) <= 2
    if qs:
        assert any(
            kw in q for q in qs for kw in ("经营", "变动原因", "市场及推广", "主营业务")
        )


def test_plan_supplemental_finance_full_skips_narrative_filter():
    pack = {
        "task_type": "compare",
        "retrieval_queries": ["可比公司E 应收账款 2024 2025 对比"],
        "finance_meta": {"active": True, "subject_type": "balance_sheet"},
        "gaps": ["证据中缺少资产负债表科目行"],
    }
    qs = plan_supplemental_queries(
        "可比公司E 2024 2025 应收账款期末余额对比",
        evidence_pack=pack,
        max_queries=4,
        prefetch_tier="full",
        enabled_skills=["skill.finance.annual_report.v1"],
    )
    assert qs
    assert any("应收" in q or "资产负债" in q or "合并" in q for q in qs)


def test_prefetch_defers_hermes_draft_for_all_tier12():
    """Tier 1/2 不论 breakdown/compare/lookup，过程稿均 defer 到执行过程。"""
    assert prefetch_defers_hermes_draft_to_process(
        agent_route=AgentRoute.hermes_lite,
        prefetch_result=PREFETCH_BREAKDOWN,
    )
    assert prefetch_defers_hermes_draft_to_process(
        agent_route=AgentRoute.hermes_lite,
        prefetch_result={
            "ok": True,
            "evidence_pack": {"task_type": "compare"},
        },
    )
    assert prefetch_defers_hermes_draft_to_process(
        agent_route=AgentRoute.hermes_full,
        prefetch_result={"ok": False, "evidence_pack": {"task_type": "lookup"}},
    )
    assert not prefetch_defers_hermes_draft_to_process(
        agent_route=AgentRoute.fast,
        prefetch_result=PREFETCH_BREAKDOWN,
    )


def test_plan_supplemental_skips_used_queries():
    qs = plan_supplemental_queries(
        "可比E25、24两年销售费用明细对比",
        evidence_pack=PREFETCH_BREAKDOWN["evidence_pack"],
        max_queries=3,
    )
    assert qs
    assert "出一份可比E销售费用明细" not in qs
    assert any("附注" in q or "销售费用" in q for q in qs)


def test_hermes_kb_ask_count_from_stream_stats():
    assert hermes_orientg_kb_ask_count(
        hermes_payload={"hermes_stream_stats": {"orientg_kb_ask_calls": 2}}
    ) == 2


def test_hermes_kb_ask_count_from_tool_calls_fallback():
    assert hermes_orientg_kb_ask_count(
        hermes_payload={
            "tool_calls": [
                {"name": "orientg_kb_ask", "prefetch": True},
                {"name": "orientg_kb_ask", "status": "ok"},
            ]
        }
    ) == 1


def test_needs_fast_path_narrative_supplemental_on_finance_gap():
    from backend.services.agent_kb_supplemental import needs_fast_path_narrative_supplemental

    skill = ["skill.finance.annual_report.v1"]
    prefetch = {
        "ok": True,
        "evidence_pack": {
            "task_type": "compare",
            "gaps": ["未命中营业收入等科目的变动原因/重大变动说明（仅有金额不够）"],
        },
    }
    q = "可比E2025年与2024年营业收入对比及变动说明"
    assert needs_fast_path_narrative_supplemental(
        prefetch_result=prefetch, user_query=q, enabled_skills=skill
    )
    assert not needs_fast_path_narrative_supplemental(
        prefetch_result={"ok": True, "evidence_pack": {"task_type": "compare", "gaps": []}},
        user_query=q,
        enabled_skills=skill,
    )


@patch("backend.services.agent_kb_supplemental.ask_knowledge")
def test_run_supplemental_merges_citations(mock_ask):
    from backend.services.agent_kb_supplemental import run_supplemental_kb_asks

    mock_ask.return_value = {
        "ok": True,
        "citations": [{"doc_id": "d2", "chunk_id": "c2"}],
        "reply": "职工薪酬 1,000,000",
    }
    merged, tools = run_supplemental_kb_asks(
        user_token="tok",
        user_query="可比E25、24两年销售费用明细对比",
        prefetch_result=dict(PREFETCH_BREAKDOWN),
        kb_scope={"selected_folder_ids": ["f1"]},
        attached_doc_ids=None,
        fixtures={"tenant_id": "t1"},
        max_queries=1,
    )
    assert merged is not None
    assert len(tools) == 1
    assert tools[0].get("supplemental") is True
    assert any(c.get("doc_id") == "d2" for c in merged.get("citations") or [])


def test_choose_supplemental_prefers_synth_when_hermes_has_estimates():
    from backend.services.agent_kb_supplemental import choose_supplemental_reply

    hermes = (
        "| 销售费用 | 13,722,360.23 | 25,081,092.51 |\n"
        "####2.费用变动\n人员薪酬减少约 500-600万元。"
    )
    synth = "结论：证据仅含销售费用总额。\n| 销售费用 | 13,722,360.23 | 25,081,092.51 |"
    final, adopted, reason = choose_supplemental_reply(hermes_reply=hermes, synth_reply=synth)
    assert adopted is True
    assert reason == "synth_no_estimates"
    assert "500-600" not in final


def test_choose_supplemental_keeps_hermes_when_synth_missing_evidence():
    from backend.services.agent_kb_supplemental import choose_supplemental_reply

    hermes = "销售费用 8,851,536.62 与 17,783,841.20 对比"
    synth = "结论：缺少证据\n| 销售费用 | 缺少证据 | 缺少证据 |"
    final, adopted, reason = choose_supplemental_reply(hermes_reply=hermes, synth_reply=synth)
    assert adopted is False
    assert final == hermes
    assert reason == "keep_hermes_has_amounts"


def test_choose_supplemental_adopts_richer_synth():
    from backend.services.agent_kb_supplemental import choose_supplemental_reply

    hermes = "缺少证据"
    synth = "销售费用 2025: 8,851,536.62；2024: 17,783,841.20"
    final, adopted, _reason = choose_supplemental_reply(hermes_reply=hermes, synth_reply=synth)
    assert adopted is True
    assert "8,851,536.62" in final


def test_choose_supplemental_uses_pack_coverage():
    from backend.services.agent_kb_supplemental import choose_supplemental_reply

    prefetch = {
        "evidence_pack": {
            "facets": [{"excerpt": "行A 1,111,111.11 行B 2,222,222.22 合计 3,333,333.33"}],
        }
    }
    hermes = "合计 3,333,333.33"
    synth = "行A 1,111,111.11 行B 2,222,222.22 合计 3,333,333.33"
    _final, adopted, reason = choose_supplemental_reply(
        hermes_reply=hermes,
        synth_reply=synth,
        prefetch_result=prefetch,
    )
    assert adopted is True
    assert "pack_coverage" in reason or reason == "synth_more_amounts"


def test_lite_tier_answer_requirements_include_evidence_constraint():
    from backend.services.agent_hermes_tier_policy import hermes_answer_requirements

    req = hermes_answer_requirements(
        tier="lite",
        user_query="可比E25、24两年销售费用明细对比分析报告",
    )
    assert "禁止估算" in req
    assert "citations" in req or "orientg_kb_ask" in req
