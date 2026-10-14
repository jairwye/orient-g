"""Hermes 未 MCP 补检索时，Orient-G 自动补检索与修订。"""

from __future__ import annotations

import re
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


def test_needs_supplemental_when_hermes_zero_kb_ask(monkeypatch):
    from backend.config import settings

    # 与 live native skip 解耦：本测验 legacy supplemental 触发条件
    monkeypatch.setattr(settings, "hermes_native_skip_supplemental", False)
    assert needs_hermes_supplemental(
        agent_route=AgentRoute.hermes_lite,
        prefetch_result=PREFETCH_BREAKDOWN,
        hermes_kb_ask_count=0,
        hermes_reply="",
        user_query="可比E销售费用",
    )
    assert needs_hermes_supplemental(
        agent_route=AgentRoute.hermes_lite,
        prefetch_result=PREFETCH_BREAKDOWN,
        hermes_kb_ask_count=2,
        hermes_reply="",
        user_query="可比E销售费用",
    )
    assert needs_hermes_supplemental(
        agent_route=AgentRoute.hermes_full,
        prefetch_result=PREFETCH_BREAKDOWN,
        hermes_kb_ask_count=2,
        hermes_reply="",
        user_query="可比E销售费用",
    )
    assert needs_hermes_supplemental(
        agent_route=AgentRoute.hermes_full,
        prefetch_result={**PREFETCH_BREAKDOWN, "evidence_pack": {**PREFETCH_BREAKDOWN["evidence_pack"], "task_type": "compare"}},
        hermes_kb_ask_count=3,
        hermes_reply="需要通过 MCP 工具检索人员结构，Evidence Pack 不完整。",
        user_query="对比分析YYCQ和可比公司A25年的人员结构",
    )
    assert not needs_hermes_supplemental(
        agent_route=AgentRoute.fast,
        prefetch_result=PREFETCH_BREAKDOWN,
        hermes_kb_ask_count=0,
    )


def test_tier2_supplemental_when_hermes_estimates_and_pack_has_breakdown(monkeypatch):
    from backend.config import settings
    from backend.services.evidence_reply_align import pack_has_tabular_breakdown

    # legacy 补检索路径；native 全局主答见 test_hermes_authorship
    monkeypatch.setattr(settings, "hermes_native_mcp_reply", False)
    monkeypatch.setattr(settings, "hermes_native_skip_supplemental", False)

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
    q = "对比分析YYCQ和可比公司A25年的人员结构"
    assert supplemental_max_queries_for_route(AgentRoute.hermes_full, user_query=q) == 8


def test_plan_supplemental_full_uses_user_query_recovery():
    pack = {
        **PREFETCH_BREAKDOWN["evidence_pack"],
        "retrieval_queries": ["出一份可比E销售费用明细"],
    }
    q = "可比E25、24两年销售费用明细对比分析报告"
    qs = plan_supplemental_queries(
        q,
        evidence_pack=pack,
        max_queries=2,
        prefetch_tier="full",
    )
    assert len(qs) <= 2
    assert qs[0] == q


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
        hermes_payload={"hermes_stream_stats": {"hermes_orientg_kb_ask_calls": 2}}
    ) == 2
    assert (
        hermes_orientg_kb_ask_count(
            hermes_payload={"hermes_stream_stats": {"orientg_kb_ask_calls": 2, "gateway_orientg_kb_ask_calls": 2}}
        )
        == 0
    )


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


@patch("backend.services.knowledge_pipeline.ask_knowledge")
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


@patch("backend.services.knowledge_pipeline.ask_knowledge")
def test_run_supplemental_preserves_doc_folder_labels(mock_ask):
    from backend.services.agent_kb_supplemental import run_supplemental_kb_asks

    mock_ask.return_value = {
        "ok": True,
        "citations": [{"doc_id": "ud_37", "chunk_id": "c37"}],
        "reply": "研发人员数量 1,378",
    }
    prefetch = {
        **PREFETCH_BREAKDOWN,
        "evidence_pack": {
            **PREFETCH_BREAKDOWN["evidence_pack"],
            "task_type": "compare",
            "doc_folder_labels": {"ud_yycq": "25", "ud_37": "PeerA25"},
            "multi_company_scope": True,
            "scope_folders": [{"folder_id": "f1", "name": "25"}, {"folder_id": "f2", "name": "PeerA25"}],
        },
    }
    merged, _tools = run_supplemental_kb_asks(
        user_token="tok",
        user_query=PERSONNEL_QUERY,
        prefetch_result=prefetch,
        kb_scope={"selected_folder_ids": ["f_root"]},
        attached_doc_ids=None,
        fixtures={"tenant_id": "t1"},
        max_queries=1,
    )
    pack = merged.get("evidence_pack") or {}
    labels = pack.get("doc_folder_labels") or {}
    assert labels.get("ud_yycq") == "25"
    assert labels.get("ud_37") == "PeerA25"
    assert pack.get("multi_company_scope") is True


USER_BROWSER_FAIL_V3 = (
    "结论：证据严重缺失，无法完成对比分析。\n"
    "完全缺失可比公司A2025年的人员结构数据。\n"
    "研发人员期末为 1,378人，占比43.91%。YYCQ总员工数仅为139人，1,378人显然不可能。\n"
    "1.1信息-人员 研发 70 人。"
)


def test_user_browser_fail_v3_misattributed_and_insufficient():
    from backend.services.kb_ask_mcp_reply import personnel_compare_reply_misattributed
    from backend.services.agent_kb_supplemental import _personnel_compare_reply_insufficient

    assert personnel_compare_reply_misattributed(USER_BROWSER_FAIL_V3, user_query=PERSONNEL_QUERY)
    assert _personnel_compare_reply_insufficient(USER_BROWSER_FAIL_V3, user_query=PERSONNEL_QUERY)


def test_pick_personnel_after_supplemental_uses_excerpt_when_labels_preserved():
    from backend.services.agent_kb_supplemental import pick_personnel_compare_final_reply

    excerpt = GOOD_EXCERPT
    synth = USER_BROWSER_FAIL_V3
    prefetch = {"ok": True, "citations": [{"doc_id": "d1"}], "evidence_pack": {"task_type": "compare"}}
    with patch(
        "backend.services.kb_ask_mcp_reply.personnel_compare_reply_from_prefetch",
        return_value=GOOD_EXCERPT,
    ):
        final, adopted, reason = pick_personnel_compare_final_reply(
            hermes_reply=USER_BROWSER_FAIL_V3,
            synth_reply=synth,
            excerpt_reply=excerpt,
            user_query=PERSONNEL_QUERY,
            agent_route=AgentRoute.hermes_full,
            prefetch_result=prefetch,
        )
    assert adopted is True
    assert reason == "personnel_structured_report"
    assert "1378" in final or "1,378" in final
    assert "完全缺失可比公司A" not in final

    from backend.services.agent_kb_supplemental import choose_supplemental_reply

    hermes = "需要通过 MCP 工具检索人员结构。Evidence Pack 不完整，需要进一步检索。"
    synth = "## 对比\n| 公司 | 人数 |\n| 可比公司A | 3,138 |\n| YYCQ | 220 |"
    final, adopted, reason = choose_supplemental_reply(
        hermes_reply=hermes,
        synth_reply=synth,
        prefetch_result=PREFETCH_BREAKDOWN,
        agent_route=AgentRoute.hermes_full,
        user_query="对比分析YYCQ和可比公司A25年的人员结构",
    )
    assert adopted is True
    assert reason == "hermes_planning"
    assert "3,138" in final


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


PERSONNEL_QUERY = "对比分析YYCQ和可比公司A25年的人员结构"

BROWSER_FAIL_HERMES = (
    "结论：证据中缺乏可比公司A2025年的人员结构数据，无法进行对比分析。\n"
    "YYCQ在职员工 139 人；1.1信息-人员 运营 61 研发 70。\n"
    "可比公司A 2025年人员结构数据 缺失证据。\n"
    "YYCQ研发人员数量存在两组数据（95人 vs 1,378人），1,378人数据疑似归属其他主体。"
)

GOOD_EXCERPT = (
    "## YYCQ vs 可比公司A · 2025 人员结构对比\n\n"
    "### 人员结构对照\n\n"
    "| 职能归属 | 可比公司A | YYCQ |\n"
    "| --- | --- | --- |\n"
    "| 研发 | 1378 人（占员工 43.91%） | 70 人 |\n"
    "| 运营 | 证据未覆盖 | 61 人 |\n"
    "| 管理 | 证据未覆盖 | 33.15 人 |\n"
    "| 支持 | 证据未覆盖 | 45.85 人 |\n\n"
    "### 对比分析\n\n"
    "- **结构差异**：YYCQ为 excel 职能四分项。\n"
)


def test_personnel_compare_reply_misattributed_browser_sample():
    from backend.services.kb_ask_mcp_reply import personnel_compare_reply_misattributed

    assert personnel_compare_reply_misattributed(BROWSER_FAIL_HERMES, user_query=PERSONNEL_QUERY)
    assert not personnel_compare_reply_misattributed(GOOD_EXCERPT, user_query=PERSONNEL_QUERY)


def test_personnel_compare_insufficient_flags_excerpt_dump():
    from backend.services.agent_kb_supplemental import _personnel_compare_reply_insufficient

    dump = (
        "YYCQ vs 可比公司A · 2025 人员结构对比\n"
        "以下对比基于知识库 docling section / excel chunk 证据（非硬编码数值）。\n"
        "可比公司A 研发 1378 | YYCQ 1.1信息-人员 研发 70\n"
        "对比说明\n口径可能不同。\n"
    )
    assert _personnel_compare_reply_insufficient(dump, user_query=PERSONNEL_QUERY)


def test_personnel_compare_insufficient_flags_browser_misattribution():
    from backend.services.agent_kb_supplemental import _personnel_compare_reply_insufficient

    assert _personnel_compare_reply_insufficient(BROWSER_FAIL_HERMES, user_query=PERSONNEL_QUERY)


def test_personnel_compare_sufficient_with_chinese_entity_names(monkeypatch):
    """中文实问成稿用「YYCQ/可比公司A」不得被判 insufficient（别名归一后仍须认）。"""
    from backend.services.agent_kb_supplemental import _personnel_compare_reply_insufficient
    from backend.services.kb_compare_entities import clear_compare_entity_cache

    monkeypatch.setenv("KB_COMPARE_ENTITY_PRIMARY_ALIASES", "YYCQ")
    monkeypatch.setenv("KB_COMPARE_ENTITY_PEER_ALIASES", "可比公司A")
    monkeypatch.setenv("KB_COMPARE_ENTITY_EXTRA_MARKERS", "YYCQ,可比公司A")
    clear_compare_entity_cache()
    q = "对比分析YYCQ和可比公司A25年的人员结构"
    good = (
        "## YYCQ vs 可比公司A · 2025 人员结构\n\n"
        "### 人员结构对照\n\n"
        "| 职能归属 | 可比公司A | YYCQ |\n"
        "| --- | --- | --- |\n"
        "| 研发 | 1378 人 | 70 人 |\n"
        "| 销售 | 946 人 | 证据未覆盖 |\n"
        "| 运营 | 242 人 | 61 人 |\n\n"
        "### 对比分析\n"
        "可比公司A研发规模显著大于YYCQ；口径不同不可直接比总人数。\n"
    )
    assert not _personnel_compare_reply_insufficient(good, user_query=q)


def test_pick_personnel_rejects_core_metric_synth_for_structured():
    """Hermes 中断后本地 synth「核心指标对比+推算」不得压过结构化人员对照。"""
    from backend.services.agent_kb_supplemental import pick_personnel_compare_final_reply

    synth = (
        "### 核心指标对比表\n"
        "| 指标 | 可比公司A | YYCQ |\n"
        "| 员工总数 | 3138 | 153 |\n"
        "根据推算，YYCQ合计 153（61+33.15+70+45.85），研发占比约45.75%。\n"
    )
    prefetch = {"ok": True, "citations": [{"doc_id": "d1"}], "evidence_pack": {"task_type": "compare"}}
    with patch(
        "backend.services.kb_ask_mcp_reply.personnel_compare_reply_from_prefetch",
        return_value=GOOD_EXCERPT,
    ):
        final, adopted, reason = pick_personnel_compare_final_reply(
            hermes_reply="",
            synth_reply=synth,
            excerpt_reply=None,
            user_query=PERSONNEL_QUERY,
            agent_route=AgentRoute.hermes_full,
            prefetch_result=prefetch,
        )
    assert adopted is True
    assert reason == "personnel_structured_report"
    assert "人员结构对照" in final
    assert "核心指标对比" not in final
    assert "推算" not in final
    assert "153" not in final


def test_tier2_error_recovery_personnel_skips_llm_synth_when_structured_ok(monkeypatch):
    """stall/error recovery：native 深度无 Hermes 稿时禁止 OG 节选/本地推算顶替。"""
    from backend.config import settings
    from backend.services.agent_kb_supplemental import (
        HERMES_INCOMPLETE_REPLY,
        iter_tier2_hermes_error_recovery_events,
    )

    monkeypatch.setattr(settings, "hermes_native_mcp_reply", True)
    monkeypatch.setattr(settings, "hermes_native_skip_supplemental", True)
    prefetch = {
        "ok": True,
        "citations": [{"doc_id": "d1", "excerpt": "研发人员 1,378"}],
        "evidence_pack": {"task_type": "compare", "coverage_score": 0.9},
        "reply": "",
    }
    synth_calls: list[str] = []

    def _fake_synth(**kwargs):
        synth_calls.append("called")
        return {
            "reply": "### 核心指标对比\n根据推算合计153人。\n",
            "citations": [],
            "llm_model": "qwen3.6-35b-apex",
            "synthesis": "local_llm",
        }

    with (
        patch(
            "backend.services.agent_kb_supplemental.run_supplemental_kb_asks",
            return_value=(prefetch, []),
        ),
        patch(
            "backend.services.kb_ask_mcp_reply.personnel_compare_reply_from_prefetch",
            return_value=GOOD_EXCERPT,
        ),
        patch(
            "backend.services.agent_kb_prefetch.synthesize_kb_reply",
            side_effect=_fake_synth,
        ),
    ):
        evts = list(
            iter_tier2_hermes_error_recovery_events(
                user_token="tok",
                tenant_id="tenant1",
                user_query=PERSONNEL_QUERY,
                prefetch_result=prefetch,
                prefetch_tool_calls=[],
                kb_scope={"selected_folder_ids": ["f1"]},
                attached_doc_ids=None,
                fixtures={"tenant_id": "tenant1"},
                agent_route=AgentRoute.hermes_full,
                enabled_skills=None,
                model=None,
                error_code="hermes_stall",
            )
        )
    done = [e for e in evts if e.get("type") == "done"][-1]
    assert done.get("reply") == HERMES_INCOMPLETE_REPLY
    assert done.get("reply_source") in (
        "hermes",
        "hermes_incomplete",
        "orientg_mcp_coerce",
    )
    assert "推算" not in (done.get("reply") or "")
    assert "核心指标对比" not in (done.get("reply") or "")
    assert synth_calls == []
    assert GOOD_EXCERPT not in (done.get("reply") or "")


def test_needs_supplemental_on_browser_misattributed_hermes(monkeypatch):
    from backend.config import settings

    monkeypatch.setattr(settings, "hermes_native_skip_supplemental", False)
    assert needs_hermes_supplemental(
        agent_route=AgentRoute.hermes_full,
        prefetch_result={
            "ok": True,
            "evidence_pack": {"task_type": "compare"},
        },
        hermes_kb_ask_count=3,
        hermes_reply=BROWSER_FAIL_HERMES,
        user_query=PERSONNEL_QUERY,
    )


def test_pick_personnel_tier2_drops_hermes_without_core_table():
    from backend.services.agent_kb_supplemental import pick_personnel_compare_final_reply

    hermes_analysis_no_table = (
        "基于证据对YYCQ与可比公司A2025年人员结构对比分析如下。\n"
        "可比公司A：研发人员约1378人，占比43.91%。\n"
        "YYCQ：excel分项研发约70人。\n"
        "对比分析：两家口径不同。\n"
    )
    prefetch = {"ok": True, "citations": [{"doc_id": "d1"}], "evidence_pack": {"task_type": "compare"}}
    with patch(
        "backend.services.kb_ask_mcp_reply.personnel_compare_reply_from_prefetch",
        return_value=GOOD_EXCERPT,
    ):
        final, adopted, reason = pick_personnel_compare_final_reply(
            hermes_reply=hermes_analysis_no_table,
            synth_reply="",
            excerpt_reply=GOOD_EXCERPT,
            user_query=PERSONNEL_QUERY,
            agent_route=AgentRoute.hermes_full,
            prefetch_result=prefetch,
        )
    assert adopted is True
    assert reason == "personnel_structured_report"
    assert "人员结构对照" in final


def test_pick_personnel_compare_prefers_excerpt_over_browser_hermes():
    from backend.services.agent_kb_supplemental import pick_personnel_compare_final_reply

    prefetch = {"ok": True, "citations": [{"doc_id": "d1"}], "evidence_pack": {"task_type": "compare"}}
    with patch(
        "backend.services.kb_ask_mcp_reply.personnel_compare_reply_from_prefetch",
        return_value=GOOD_EXCERPT,
    ):
        final, adopted, reason = pick_personnel_compare_final_reply(
            hermes_reply=BROWSER_FAIL_HERMES,
            synth_reply="结论：缺少证据，无法对比可比公司A与YYCQ人员结构。",
            excerpt_reply=GOOD_EXCERPT,
            user_query=PERSONNEL_QUERY,
            agent_route=AgentRoute.hermes_full,
            prefetch_result=prefetch,
        )
    assert adopted is True
    assert reason == "personnel_structured_report"
    assert "1378" in final or "1,378" in final
    assert "缺乏可比公司A" not in final
    assert "95人 vs 1,378" not in final


def test_personnel_misattribution_gate_replaces_browser_fail(monkeypatch):
    from backend.config import settings
    from backend.services.agent_kb_supplemental import apply_personnel_misattribution_gate

    # native skip 路径故意禁用 structured 模板替换；本测锁定 legacy gate
    monkeypatch.setattr(settings, "hermes_native_mcp_reply", False)
    monkeypatch.setattr(settings, "hermes_native_skip_supplemental", False)
    prefetch = {
        "ok": True,
        "citations": [
            {"doc_id": "ud_a", "chunk_id": "c1"},
            {"doc_id": "ud_b", "chunk_id": "c2"},
        ],
        "evidence_pack": {
            "task_type": "compare",
            "doc_folder_labels": {"ud_a": "PeerA25 · 公司研发人员情况", "ud_b": "25 · 1.1信息-人员"},
        },
    }
    with patch(
        "backend.services.kb_ask_mcp_reply.personnel_compare_reply_from_prefetch",
        return_value=GOOD_EXCERPT,
    ):
        out, applied = apply_personnel_misattribution_gate(
            BROWSER_FAIL_HERMES,
            prefetch_result=prefetch,
            user_query=PERSONNEL_QUERY,
            tenant_id="tenant1",
        )
    assert applied is True
    assert "### 人员结构对照" in out
    assert "缺乏可比公司A" not in out


PERSONNEL_DUMP_REPLY = (
    "YYCQ vs 可比公司A · 2025 人员结构对比\n"
    "以下对比基于知识库 docling section / excel chunk 证据（非硬编码数值）。\n"
    "可比公司A\n公司研发人员情况\n研发人员数量（人） | 1,378 |\n"
    "YYCQ\n1.1信息-人员\n研发 | 70.00 |\n"
    "对比说明\n两家主体人员结构口径可能不同；勿将研发人数与全员人数直接相加混比。\n"
    "citations（12）"
)

STRUCTURED_REPLY = (
    "## YYCQ vs 可比公司A · 2025 人员结构对比\n\n"
    "### 人员结构对照\n\n"
    "| 主体 | 数据来源 | 研发/分项人数 | 研发占比或说明 |\n"
    "| 可比公司A | 年报·研发人员情况 | 1378 | 43.91% |\n"
    "| YYCQ | excel·1.1信息-人员 | 70 | 分项 |\n\n"
    "### 对比分析\n\n"
    "- **口径差异**：可比公司A为年报研发人员情况；YYCQ为 excel 分项。\n"
)


def test_apply_personnel_structured_final_gate_replaces_excerpt_dump(monkeypatch):
    from backend.config import settings
    from backend.services.agent_kb_supplemental import apply_personnel_structured_final_gate

    monkeypatch.setattr(settings, "hermes_native_mcp_reply", False)
    monkeypatch.setattr(settings, "hermes_native_skip_supplemental", False)
    prefetch = {"ok": True, "evidence_pack": {"task_type": "compare"}}
    with patch(
        "backend.services.kb_ask_mcp_reply.personnel_compare_reply_from_prefetch",
        return_value=STRUCTURED_REPLY,
    ):
        out, applied = apply_personnel_structured_final_gate(
            PERSONNEL_DUMP_REPLY,
            prefetch_result=prefetch,
            user_query=PERSONNEL_QUERY,
            tenant_id="tenant1",
        )
    assert applied is True
    assert "### 人员结构对照" in out
    assert "### 对比分析" in out
    assert "非硬编码数值" not in out


def test_apply_personnel_structured_final_gate_refreshes_incomplete_sanqi_table(monkeypatch):
    """legacy（非 native）：incomplete 表仍可由 prefetch 模板刷新。"""
    from backend.config import settings
    from backend.services.agent_kb_supplemental import apply_personnel_structured_final_gate

    monkeypatch.setattr(settings, "hermes_native_mcp_reply", False)
    monkeypatch.setattr(settings, "hermes_native_skip_supplemental", False)
    incomplete = (
        "## YYCQ vs 可比公司A · 2025 人员结构对比\n\n"
        "### 人员结构对照\n\n"
        "| 职能归属 | 可比公司A | YYCQ |\n"
        "| 研发 | 1378 人 | 70 人 |\n"
        "| 销售 | 证据未覆盖（节选无该分项） | 证据未覆盖 |\n\n"
        "### 对比分析\n\n- 对比\n"
    )
    complete = (
        "## YYCQ vs 可比公司A · 2025 人员结构对比\n\n"
        "### 人员结构对照\n\n"
        "| 职能归属 | 可比公司A | YYCQ |\n"
        "| 销售 | 946 人 | 证据未覆盖 |\n"
        "| 运营 | 242 人 | 61 人 |\n\n"
        "### 对比分析\n\n- 对比\n"
    )
    prefetch = {"ok": True, "evidence_pack": {"task_type": "compare"}}
    with patch(
        "backend.services.kb_ask_mcp_reply.personnel_compare_reply_from_prefetch",
        return_value=complete,
    ):
        out, applied = apply_personnel_structured_final_gate(
            incomplete,
            prefetch_result=prefetch,
            user_query=PERSONNEL_QUERY,
            tenant_id="tenant1",
        )
    assert applied is True
    assert "946" in out


def test_apply_personnel_structured_final_gate_skips_already_structured():
    from backend.services.agent_kb_supplemental import apply_personnel_structured_final_gate

    out, applied = apply_personnel_structured_final_gate(
        STRUCTURED_REPLY,
        prefetch_result={"ok": True},
        user_query=PERSONNEL_QUERY,
        tenant_id="tenant1",
    )
    assert applied is False
    assert out == STRUCTURED_REPLY


def test_structured_gate_does_not_keep_139_misattr_core_hermes(monkeypatch):
    """有 1378/70 锚点也不得因 hermes_has_core 放行 139/22.6 倍误归因稿。"""
    from backend.config import settings
    from backend.services.agent_kb_supplemental import apply_personnel_structured_final_gate
    from backend.services.kb_ask_mcp_reply import personnel_compare_reply_misattributed

    monkeypatch.setattr(settings, "hermes_native_mcp_reply", True)
    monkeypatch.setattr(settings, "hermes_native_skip_supplemental", True)
    bad = (
        "### 人员结构对照\n"
        "| 职能归属 | 可比公司A | YYCQ |\n"
        "| 研发 | 1,378 | 70 |\n"
        "| 销售 | 946 | 10 |\n"
        "| 运营 | 242 | 61 |\n"
        "| 合计 | 3,138 | 139 |\n"
        "### 对比分析\n"
        "可比公司A3,138人，YYCQ139人，约为22.6倍。\n"
    )
    assert personnel_compare_reply_misattributed(bad, user_query=PERSONNEL_QUERY)
    out, applied = apply_personnel_structured_final_gate(
        bad,
        prefetch_result={
            "ok": True,
            "citations": [{"doc_id": "d1"}],
            "evidence_excerpts": [
                {
                    "entity": "可比公司A",
                    "excerpt": (
                        "研发人员数量 1,378\n销售人员 946\n运营人员 242\n"
                        "在职员工的数量合计 3,138"
                    ),
                },
                {
                    "entity": "YYCQ",
                    "excerpt": "研发 70.00 运营 61.00 管理 33.15 支持 45.85",
                },
            ],
            "evidence_pack": {"task_type": "personnel_compare", "coverage_score": 0.9},
        },
        user_query=PERSONNEL_QUERY,
        tenant_id="tenant1",
        fixtures={"tenant_id": "tenant1"},
    )
    assert "22.6" not in out
    assert not re.search(r"YYCQ[^\n]{0,40}139", out)
    assert "139" not in out or "分项" in out
    # 纠偏后不得仍是误归因；A3 优先 coerce（applied=False）而非门禁整页
    assert not personnel_compare_reply_misattributed(out, user_query=PERSONNEL_QUERY)


REVENUE_QUERY = "可比公司E2025年与2024年营业收入对比及变动说明"

PREFETCH_REVENUE = {
    "ok": True,
    "citations": [{"doc_id": "d_hq", "chunk_id": "c1"}],
    "evidence_pack": {
        "task_type": "compare",
        "coverage_score": 0.9,
        "retrieval_queries": [REVENUE_QUERY],
        "gaps": [],
        "facets": [
            {
                "label": "合并利润表",
                "excerpt": (
                    "可比公司E 合并利润表\n"
                    "| 营业收入 | 100,148,026.24 | 138,539,446.45 |\n"
                    "| 销售费用 | 13,722,360.23 | 25,081,092.51 |\n"
                    "项目重大变动原因 销售费用减少主要系人员减少"
                ),
            }
        ],
    },
}

BLOCKED_REVENUE_HERMES = (
    "结论证据未覆盖可比公司E2025年与2024年合并利润表中营业收入的两期金额。\n"
    "| 营业收入 | 缺少证据 | 缺少证据 | 缺少证据 |\n"
    "变动原因：销售费用减少主要系人员减少。"
)


def test_reply_denies_primary_compare_subject_revenue():
    from backend.services.evidence_reply_align import reply_denies_primary_compare_subject

    assert reply_denies_primary_compare_subject(BLOCKED_REVENUE_HERMES, user_query=REVENUE_QUERY)
    good = "营业收入 100,148,026.24 138,539,446.45 同比 -27.71%"
    assert not reply_denies_primary_compare_subject(good, user_query=REVENUE_QUERY)


INVENTORY_QUERY = "可比公司E2025年末与2024年末存货对比"

BLOCKED_INVENTORY_HONEST = (
    "不确定/缺少证据。\n"
    "原因说明：证据主体不匹配，可比公司E25的证据包中未包含资产负债表中「存货」科目的具体金额数据。"
)


def test_reply_denies_honest_missing_inventory_compare():
    from backend.services.evidence_reply_align import reply_denies_primary_compare_subject

    assert reply_denies_primary_compare_subject(BLOCKED_INVENTORY_HONEST, user_query=INVENTORY_QUERY)


def test_needs_supplemental_when_kb_ask_but_denies_revenue_subject():
    assert needs_hermes_supplemental(
        agent_route=AgentRoute.hermes_lite,
        prefetch_result=PREFETCH_REVENUE,
        hermes_kb_ask_count=2,
        hermes_reply=BLOCKED_REVENUE_HERMES,
        user_query=REVENUE_QUERY,
    )
    good = (
        "可比公司E2025年与2024年营业收入对比：\n"
        "| 科目 | 2025年 | 2024年 |\n"
        "| 营业收入 | 100,148,026.24 | 138,539,446.45 |\n"
        "变动原因：主要系境外收入下滑及业务收缩。"
    )
    assert not needs_hermes_supplemental(
        agent_route=AgentRoute.hermes_lite,
        prefetch_result=PREFETCH_REVENUE,
        hermes_kb_ask_count=2,
        hermes_reply=good,
        user_query=REVENUE_QUERY,
    )


def test_build_compare_subject_reply_from_prefetch():
    from backend.services.evidence_reply_align import build_compare_subject_reply_from_prefetch

    out = build_compare_subject_reply_from_prefetch(REVENUE_QUERY, PREFETCH_REVENUE)
    assert out
    assert "100,148,026.24" in out
    assert "138,539,446.45" in out
    assert "营业收入" in out


def test_apply_compare_subject_denial_gate():
    from backend.services.agent_kb_supplemental import apply_compare_subject_denial_gate

    out, applied = apply_compare_subject_denial_gate(
        BLOCKED_REVENUE_HERMES,
        prefetch_result=PREFETCH_REVENUE,
        user_query=REVENUE_QUERY,
    )
    assert applied is True
    assert "100,148,026.24" in out
    assert "缺少证据" not in out
