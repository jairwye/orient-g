"""检索计划：task_type 与子 query。"""

from __future__ import annotations

from backend.services.kb_retrieval_plan import TaskType, infer_task_type, plan_retrieval_queries


def test_infer_breakdown_from_cost_detail_query():
    assert infer_task_type("成本下降主要是怎么实现的，分解成明细的对比") == TaskType.breakdown


def test_infer_compare_from_two_year_pl():
    assert infer_task_type("做可比公司E25和24年损益对比表") == TaskType.compare


def test_infer_fact_from_revenue():
    assert infer_task_type("可比公司E25年营收是多少") == TaskType.fact


def test_infer_compare_from_personnel_structure_query():
    assert infer_task_type("对比分析YYCQ和可比公司A25年的人员结构") == TaskType.compare


def test_personnel_structure_not_breakdown():
    assert infer_task_type("YYCQ2025年人员结构") == TaskType.general


def test_plan_breakdown_includes_fee_note_queries():
    qs = plan_retrieval_queries("成本下降明细对比", TaskType.breakdown, entity="可比公司E")
    assert qs[0] == "成本下降明细对比"
    joined = " ".join(qs)
    assert "销售费用" in joined
    assert "管理费用" in joined
    assert len(qs) <= 8


def test_plan_breakdown_prefers_section_heading_subquery():
    qs = plan_retrieval_queries("成本费用明细分解", TaskType.breakdown, entity="可比公司E")
    assert any("## 销售费用" in q or "## 管理费用" in q for q in qs)


def test_plan_compare_includes_merged_pl():
    qs = plan_retrieval_queries("可比公司E25和24损益对比", TaskType.compare, entity="可比公司E")
    assert any("合并利润表" in q for q in qs)


def test_plan_compare_includes_cashflow_subject():
    q = "2025年与2024年经营活动产生的现金流量净额对比"
    qs = plan_retrieval_queries(q, TaskType.compare, entity="某公司", max_queries=8)
    joined = " ".join(qs)
    assert "现金流" in joined


def test_native_personnel_prefetch_max_queries_helper(monkeypatch):
    from backend.config import settings
    from backend.services.kb_retrieval_plan import native_personnel_prefetch_max_queries

    q = "对比分析YYCQ和可比公司A25年的人员结构"
    monkeypatch.setattr(settings, "hermes_native_mcp_reply", False)
    assert native_personnel_prefetch_max_queries(q, prefetch_tier="full") is None

    monkeypatch.setattr(settings, "hermes_native_mcp_reply", True)
    monkeypatch.setattr(settings, "hermes_native_prefetch_max_kb_asks", 1)
    assert native_personnel_prefetch_max_queries(q, prefetch_tier="full") == 1
    assert native_personnel_prefetch_max_queries(q, prefetch_tier="lite") is None
    assert native_personnel_prefetch_max_queries("可比公司E营收对比", prefetch_tier="full") is None

    monkeypatch.setattr(settings, "hermes_native_prefetch_max_kb_asks", 0)
    assert native_personnel_prefetch_max_queries(q, prefetch_tier="full") == 0


def test_personnel_retrieval_subqueries_target_kb_sections():
    from backend.services.kb_retrieval_plan import personnel_retrieval_subqueries

    qs = personnel_retrieval_subqueries("对比分析YYCQ和可比公司A25年的人员结构")
    joined = " ".join(qs)
    assert "研发人员情况" in joined
    assert "1.1信息-人员" in joined
    assert "可比公司A" in joined
    assert "YYCQ" in joined
    assert "sec-04" not in joined


def test_query_wants_personnel_compare_two_entities():
    from backend.services.kb_retrieval_plan import query_wants_personnel_compare

    assert query_wants_personnel_compare("对比分析YYCQ和可比公司A25年的人员结构")
    assert not query_wants_personnel_compare("YYCQ2025年人员结构")


def test_compare_subjects_from_query_unified():
    from backend.services.kb_retrieval_plan import compare_subjects_from_query

    assert "应收账款" in compare_subjects_from_query("2025年末应收账款余额对比")
    assert any("经营" in s for s in compare_subjects_from_query("经营活动现金流对比"))
