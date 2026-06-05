"""分层策略：深度 / 标准 / 快速 规制差异。"""

from __future__ import annotations

from backend.services.agent_hermes_tier_policy import (
    discourage_repeat_kb_ask,
    hermes_answer_requirements,
    hermes_orientg_context_extras,
    prefetch_system_lead,
    prefetch_tier_for_agent_mode,
    prefetch_tier_from_route,
)


def test_deep_mode_uses_full_tier():
    assert prefetch_tier_for_agent_mode("deep") == "full"
    assert prefetch_tier_from_route("hermes_full", agent_mode="standard") == "full"


def test_standard_mode_uses_lite_prefetch_tier():
    assert prefetch_tier_for_agent_mode("standard") == "lite"


def test_deep_prefetch_lead_analyst_not_immediate():
    lead = prefetch_system_lead(via_hermes=True, evidence_pack={}, tier="full")
    assert "分析师" in lead or "深度" in lead
    assert "立即" not in lead
    assert not discourage_repeat_kb_ask("full")


def test_standard_prefetch_lead_immediate_when_no_gaps():
    lead = prefetch_system_lead(via_hermes=True, evidence_pack={"gaps": []}, tier="lite")
    assert "立即" in lead
    assert "标准" in lead or "Tier 1" in lead
    assert discourage_repeat_kb_ask("lite")


def test_standard_tier_gap_force_extras():
    pack = {"gaps": ["未命中附注"]}
    extras = hermes_orientg_context_extras(tier="lite", evidence_pack=pack, user_query="q")
    assert extras.get("orientg_kb_ask_required") is True


def test_deep_analyst_report_suggests_narrative_ask():
    extras = hermes_orientg_context_extras(
        tier="full",
        evidence_pack={"gaps": []},
        user_query="出一份华清25、24两年销售费用明细的对比分析报告",
    )
    assert extras.get("orientg_kb_ask_suggested") or extras.get("orientg_suggested_kb_queries")


def test_full_answer_requirements_analyst_structure():
    req = hermes_answer_requirements(
        tier="full",
        user_query="出一份华清25、24两年销售费用明细的对比分析报告",
    )
    assert "分析师" in req or "深度" in req
    assert "盈利" in req or "费比" in req
    assert "风险" in req


def test_lite_breakdown_includes_standard_compliance():
    req = hermes_answer_requirements(
        tier="lite",
        user_query="华清25、24两年销售费用明细对比分析报告",
    )
    assert "标准" in req or "合规" in req
    assert "立即" in req or "标准·合规" in req
