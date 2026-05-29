"""成本/费用明细问句的检索词扩展（TDD）。"""

from __future__ import annotations

from backend.services import knowledge_pipeline as kp


def test_expand_retrieval_terms_for_cost_breakdown_query():
    terms = kp._expand_retrieval_terms(kp._tokenize_query("成本下降主要是怎么实现的，分解成明细的对比"), "成本下降主要是怎么实现的，分解成明细的对比")
    assert "营业成本" in terms
    assert any(t in terms for t in ("销售费用", "管理费用", "附注"))


def test_cost_detail_chunk_scores_above_entity_only_notes():
    q = "成本下降明细对比"
    terms = kp._expand_retrieval_terms(kp._tokenize_query(q), q)
    notes_only = "## 审计报告附注\n华清股份有限公司 税率说明。\n" * 5
    cost_detail = (
        "## 合并利润表\n"
        "华清 2025 销售费用 12,000,000.00 管理费用 8,000,000.00 营业成本 500,000,000.00\n"
    )
    s_notes = kp._score_chunk_for_retrieval(notes_only, terms, q)
    s_cost = kp._score_chunk_for_retrieval(cost_detail, terms, q)
    assert s_cost > s_notes
