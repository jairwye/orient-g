"""Tier 规制分层：快速=严证据短表；标准=原深度合规报告；深度=分析师级 A~E。"""

from __future__ import annotations

from backend.services.agent_hermes_tier_policy import (
    discourage_repeat_kb_ask,
    hermes_answer_requirements,
    hermes_orientg_context_extras,
    prefetch_excerpt_limits,
    prefetch_system_lead,
    prefetch_tier_for_agent_mode,
)
from backend.services.agent_kb_fast_path import comparison_answer_addon
from backend.services.kb_retrieval_plan import (
    plan_retrieval_queries,
    query_wants_analyst_report,
)
from backend.services.kb_retrieval_plan import TaskType

SALES_FEE_REPORT = "出一份华清25、24两年销售费用明细的对比分析报告"


def test_prefetch_tier_maps_agent_mode_to_local_lite_full():
    assert prefetch_tier_for_agent_mode("fast") == "local"
    assert prefetch_tier_for_agent_mode("auto") == "local"
    assert prefetch_tier_for_agent_mode("standard") == "lite"
    assert prefetch_tier_for_agent_mode("deep") == "full"


def test_excerpt_limits_local_lite_full_increase():
    assert prefetch_excerpt_limits("local", "breakdown") == (4, 4000, 1)
    assert prefetch_excerpt_limits("lite", "breakdown") == (6, 6000, 2)
    assert prefetch_excerpt_limits("full", "breakdown") == (8, 8000, 3)


def test_fast_comparison_addon_strict_no_analyst_sections():
    addon = comparison_answer_addon(SALES_FEE_REPORT, tier="local")
    assert "禁止把模型推断" in addon or "缺少证据" in addon
    assert "盈利能力" not in addon
    assert "风险提示" not in addon


def test_standard_comparison_addon_has_five_section_compliance():
    addon = comparison_answer_addon(SALES_FEE_REPORT, tier="lite")
    assert "销售费用率" in addon
    assert "口径" in addon or "合并利润表" in addon
    assert "立即" in addon or "禁止向用户复述 Evidence Pack" in addon


def test_deep_comparison_addon_has_analyst_report_sections():
    addon = comparison_answer_addon(SALES_FEE_REPORT, tier="full")
    assert "分项驱动" in addon or "分项" in addon
    assert "盈利" in addon or "费比" in addon
    assert "风险" in addon
    assert "总结" in addon


def test_standard_hermes_requirements_use_lite_evidence_not_analyst():
    req = hermes_answer_requirements(tier="lite", user_query=SALES_FEE_REPORT)
    assert "标准" in req or "合规" in req
    assert "盈利能力影响" not in req
    assert "分析师" not in req


def test_deep_hermes_requirements_analyst_orchestration():
    req = hermes_answer_requirements(tier="full", user_query=SALES_FEE_REPORT)
    assert "深度" in req or "分析师" in req
    assert "orientg_kb_ask" in req or "补检索" in req
    assert "盈利能力" in req or "费比" in req
    assert "立即成稿" not in req


def test_standard_prefetch_lead_immediate_when_no_gaps():
    lead = prefetch_system_lead(via_hermes=True, evidence_pack={"gaps": []}, tier="lite")
    assert "立即" in lead or "无缺项" in lead
    assert "Tier 1" in lead or "标准" in lead


def test_deep_prefetch_lead_encourages_narrative_kb_ask():
    lead = prefetch_system_lead(via_hermes=True, evidence_pack={"gaps": []}, tier="full")
    assert "经营" in lead or "叙事" in lead or "分析" in lead
    assert "立即" not in lead


def test_deep_breakdown_extras_force_kb_ask_even_without_gaps():
    extras = hermes_orientg_context_extras(
        tier="full",
        evidence_pack={"gaps": [], "task_type": "breakdown"},
        user_query=SALES_FEE_REPORT,
    )
    assert extras.get("orientg_kb_ask_required") is True
    assert int(extras.get("orientg_kb_ask_min_calls_before_final_answer") or 0) >= 1
    assert extras.get("orientg_suggested_kb_queries")
    assert "销售费用" in str(extras.get("orientg_suggested_kb_queries") or "") or "附注" in str(
        extras.get("orientg_suggested_kb_queries") or ""
    )


def test_standard_gap_extras_force_kb_ask():
    pack = {"gaps": ["未命中附注"]}
    extras = hermes_orientg_context_extras(tier="lite", evidence_pack=pack, user_query=SALES_FEE_REPORT)
    assert extras.get("orientg_kb_ask_required") is True


def test_discourage_repeat_kb_ask_local_and_lite_only():
    assert discourage_repeat_kb_ask("local")
    assert discourage_repeat_kb_ask("lite")
    assert not discourage_repeat_kb_ask("full")


def test_query_wants_analyst_report_for_sales_fee_report():
    assert query_wants_analyst_report(SALES_FEE_REPORT) is True
    assert query_wants_analyst_report("华清25和24损益对比表") is False


def test_deep_retrieval_includes_narrative_subqueries():
    qs = plan_retrieval_queries(
        SALES_FEE_REPORT,
        TaskType.breakdown,
        entity="华清",
        prefetch_tier="full",
    )
    joined = " ".join(qs)
    assert "经营情况讨论" in joined or "管理层讨论" in joined
    assert "市场及推广" in joined or "主营业务" in joined
