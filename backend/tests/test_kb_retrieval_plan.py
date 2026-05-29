"""检索计划：task_type 与子 query。"""

from __future__ import annotations

from backend.services.kb_retrieval_plan import TaskType, infer_task_type, plan_retrieval_queries


def test_infer_breakdown_from_cost_detail_query():
    assert infer_task_type("成本下降主要是怎么实现的，分解成明细的对比") == TaskType.breakdown


def test_infer_compare_from_two_year_pl():
    assert infer_task_type("做华清25和24年损益对比表") == TaskType.compare


def test_infer_fact_from_revenue():
    assert infer_task_type("华清25年营收是多少") == TaskType.fact


def test_plan_breakdown_includes_fee_note_queries():
    qs = plan_retrieval_queries("成本下降明细对比", TaskType.breakdown, entity="华清")
    assert qs[0] == "成本下降明细对比"
    joined = " ".join(qs)
    assert "销售费用" in joined
    assert "管理费用" in joined
    assert len(qs) <= 4


def test_plan_breakdown_prefers_section_heading_subquery():
    qs = plan_retrieval_queries("成本费用明细分解", TaskType.breakdown, entity="华清")
    assert any("## 销售费用" in q for q in qs)


def test_plan_compare_includes_merged_pl():
    qs = plan_retrieval_queries("华清25和24损益对比", TaskType.compare, entity="华清")
    assert any("合并利润表" in q for q in qs)
