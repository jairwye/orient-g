"""finance_annual_report_profile：披露制度与七家竞品实体映射。"""

from __future__ import annotations

import pytest

from backend.services.finance_annual_report_profile import (
    clear_profile_cache,
    detect_regime_from_text,
    finance_annual_report_skill_enabled,
    load_disclosure_regimes,
    resolve_regime_for_entity,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_profile_cache()
    yield
    clear_profile_cache()


def test_manifest_skill_loads_disclosure_regimes():
    pack = load_disclosure_regimes()
    assert pack.get("version") == 1
    assert "cn_sz_main" in (pack.get("regimes") or {})
    assert "cn_neeq" in (pack.get("regimes") or {})
    assert "hk_main" in (pack.get("regimes") or {})
    assert "sec_us" in (pack.get("regimes") or {})
    assert len(pack.get("entities") or {}) == 7


@pytest.mark.parametrize(
    "entity,expected",
    [
        ("可比E", "cn_neeq"),
        ("可比公司E", "cn_neeq"),
        ("可比A", "cn_sz_main"),
        ("可比公司A", "cn_sz_main"),
        ("可比C", "cn_sz_main"),
        ("可比公司F", "cn_neeq"),
        ("可比D", "cn_neeq"),
        ("可比G", "cn_neeq"),
        ("可比公司B", "cn_sz_main"),
    ],
)
def test_resolve_regime_competitor_pool(entity, expected):
    assert resolve_regime_for_entity(entity) == expected


def test_detect_hk_and_sec_from_text():
    assert detect_regime_from_text("Consolidated Statement of Financial Position") == "hk_main"
    assert detect_regime_from_text("Item 8 Consolidated Balance Sheets") == "sec_us"


def test_finance_skill_enabled_flag():
    assert finance_annual_report_skill_enabled(["skill.finance.annual_report.v1"])
    assert not finance_annual_report_skill_enabled(["skill.data_parse.interpret.v1"])


def test_finance_chunk_score_demotes_other_receivable_for_ar_query():
    from backend.services.finance_annual_report_profile import (
        build_finance_retrieval_context,
        finance_chunk_score_delta,
    )

    q = "可比公司E2025年末与2024年末应收账款余额对比"
    ctx = build_finance_retrieval_context(["skill.finance.annual_report.v1"], q)
    assert ctx and ctx.get("subject_type") == "balance_sheet"
    wrong = "其他应收款 2025年12月31日 781,351.15 2024年12月31日 4,346,082.12"
    right = "合并资产负债表 应收账款 2025年12月31日 12,345,678.90 2024年12月31日 9,876,543.21"
    assert finance_chunk_score_delta(wrong, q, ctx) < finance_chunk_score_delta(right, q, ctx)


def test_plan_retrieval_queries_finance_bs_drops_pnl_noise():
    from backend.services.finance_annual_report_profile import plan_retrieval_queries_finance
    from backend.services.kb_retrieval_plan import TaskType

    q = "可比公司E2025年末与2024年末应收账款余额对比"
    qs = plan_retrieval_queries_finance(q, TaskType.compare, entity="可比E", max_queries=8, prefetch_tier="lite")
    assert any("应收账款" in x and "资产负债表" in x for x in qs)
    assert not any("营业收入" in x or "销售费用" in x for x in qs)


def test_plan_retrieval_queries_finance_revenue_adds_narrative():
    from backend.services.finance_annual_report_profile import plan_retrieval_queries_finance
    from backend.services.kb_retrieval_plan import TaskType

    q = "可比公司E2025年与2024年营业收入对比及变动说明"
    qs = plan_retrieval_queries_finance(q, TaskType.compare, entity="可比E", max_queries=10, prefetch_tier="lite")
    assert any("重大变动" in x or "经营情况讨论" in x for x in qs)
