"""变动原因检索：有证据才写原因（B 方向）。"""

from __future__ import annotations

from backend.services import knowledge_pipeline as kp
from backend.services.agent_kb_fast_path import comparison_answer_addon
from backend.services.agent_kb_supplemental import evidence_constraint_addon, plan_supplemental_queries
from backend.services.kb_retrieval_plan import (
    TaskType,
    infer_task_type,
    plan_retrieval_queries,
    query_wants_change_reasons,
)

SALES_FEE_REPORT = "出一份华清25、24两年销售费用明细的对比分析报告"


def test_query_wants_change_reasons_for_sales_fee_report():
    assert query_wants_change_reasons(SALES_FEE_REPORT) is True
    assert infer_task_type(SALES_FEE_REPORT) == TaskType.breakdown


def test_plan_retrieval_includes_reason_subqueries():
    qs = plan_retrieval_queries(SALES_FEE_REPORT, TaskType.breakdown, entity="华清")
    joined = " ".join(qs)
    assert "变动原因" in joined or "经营情况讨论" in joined
    assert len(qs) >= 6


def test_plan_supplemental_prioritizes_reason_queries():
    qs = plan_supplemental_queries(
        SALES_FEE_REPORT,
        evidence_pack={
            "task_type": "breakdown",
            "retrieval_queries": [SALES_FEE_REPORT],
        },
        max_queries=5,
    )
    assert any("变动原因" in q or "经营情况讨论" in q for q in qs)


def test_comparison_addon_requires_evidence_backed_reason_or_disclaimer():
    addon = comparison_answer_addon(SALES_FEE_REPORT, tier="local")
    assert "变动原因" in addon
    assert "证据未提供变动原因说明" in addon


def test_evidence_constraint_allows_quoted_reasons_only():
    addon = evidence_constraint_addon(tier="lite")
    assert "主要系" in addon or "是由于" in addon
    assert "证据未提供变动原因说明" in addon


def test_reason_narrative_chunk_scores_above_pure_table():
    q = SALES_FEE_REPORT
    terms = kp._expand_retrieval_terms(kp._tokenize_query(q), q)
    table = (
        "## 31 、销售费用\n| 职工薪酬 | 10,802,366.11 | 23,295,127.31 |\n"
        "| 市场及推广费用 | 2,889,547.75 | 1,526,703.85 |\n"
    )
    narrative = (
        "## 经营情况讨论\n"
        "2025年销售费用较2024年减少，主要系公司优化销售团队结构，职工薪酬支出相应下降；"
        "市场及推广费用因加大线上投放而有所增加。\n"
    )
    assert kp.is_fee_change_reason_chunk(narrative)
    assert not kp.is_fee_change_reason_chunk(table)
    s_narr_plain = kp._score_chunk_for_retrieval(narrative, terms, "华清营收是多少")
    s_narr_reason = kp._score_chunk_for_retrieval(narrative, terms, q)
    assert s_narr_reason > s_narr_plain
