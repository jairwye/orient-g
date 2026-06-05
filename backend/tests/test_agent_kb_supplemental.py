"""Hermes 未 MCP 补检索时，Orient-G 自动补检索与修订。"""

from __future__ import annotations

from unittest.mock import patch

from backend.services.agent_kb_router import AgentRoute
from backend.services.agent_kb_supplemental import (
    hermes_orientg_kb_ask_count,
    needs_hermes_supplemental,
    plan_supplemental_queries,
    prefetch_defers_hermes_draft_to_process,
)


PREFETCH_BREAKDOWN = {
    "ok": True,
    "citations": [{"doc_id": "d1"}],
    "evidence_pack": {
        "task_type": "breakdown",
        "coverage_score": 1.0,
        "retrieval_queries": ["出一份华清销售费用明细"],
        "gaps": [],
    },
}


def test_needs_supplemental_when_hermes_zero_kb_ask():
    assert needs_hermes_supplemental(
        agent_route=AgentRoute.hermes_lite,
        prefetch_result=PREFETCH_BREAKDOWN,
        hermes_kb_ask_count=0,
        hermes_reply="",
        user_query="华清销售费用",
    )
    assert not needs_hermes_supplemental(
        agent_route=AgentRoute.hermes_full,
        prefetch_result=PREFETCH_BREAKDOWN,
        hermes_kb_ask_count=2,
        hermes_reply="",
        user_query="华清销售费用",
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
        user_query="出一份华清25、24两年销售费用明细的对比分析报告",
    )


def test_tier2_no_supplemental_when_hermes_has_exact_line_items():
    pack = {
        **PREFETCH_BREAKDOWN["evidence_pack"],
        "facets": [{"label": "附注", "excerpt": "职工薪酬 10,802,366.11 市场及推广 2,889,547.75"}],
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
        user_query="出一份华清25、24两年销售费用明细的对比分析报告",
    )


def test_prefetch_defers_hermes_draft_for_breakdown_only():
    assert prefetch_defers_hermes_draft_to_process(
        agent_route=AgentRoute.hermes_lite,
        prefetch_result=PREFETCH_BREAKDOWN,
    )
    assert not prefetch_defers_hermes_draft_to_process(
        agent_route=AgentRoute.hermes_lite,
        prefetch_result={
            "ok": True,
            "evidence_pack": {"task_type": "compare"},
        },
    )
    assert not prefetch_defers_hermes_draft_to_process(
        agent_route=AgentRoute.fast,
        prefetch_result=PREFETCH_BREAKDOWN,
    )
    assert not prefetch_defers_hermes_draft_to_process(
        agent_route=AgentRoute.hermes_lite,
        prefetch_result={"ok": True, "evidence_pack": {"task_type": "lookup"}},
    )


def test_plan_supplemental_skips_used_queries():
    qs = plan_supplemental_queries(
        "华清25、24两年销售费用明细对比",
        evidence_pack=PREFETCH_BREAKDOWN["evidence_pack"],
        max_queries=3,
    )
    assert qs
    assert "出一份华清销售费用明细" not in qs
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
        user_query="华清25、24两年销售费用明细对比",
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
        user_query="华清25、24两年销售费用明细对比分析报告",
    )
    assert "禁止估算" in req
    assert "citations" in req or "orientg_kb_ask" in req
