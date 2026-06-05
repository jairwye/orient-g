"""成本/费用明细问句的检索词扩展（TDD）。"""

from __future__ import annotations

from backend.services import knowledge_pipeline as kp


def test_expand_retrieval_terms_for_cost_breakdown_query():
    terms = kp._expand_retrieval_terms(kp._tokenize_query("成本下降主要是怎么实现的，分解成明细的对比"), "成本下降主要是怎么实现的，分解成明细的对比")
    assert "营业成本" in terms
    assert any(t in terms for t in ("销售费用", "管理费用", "附注"))


def test_cost_detail_chunk_scores_above_entity_only_notes():
    from backend.services.knowledge_pipeline import is_fee_appendix_chunk

    q = "成本下降明细对比"
    terms = kp._expand_retrieval_terms(kp._tokenize_query(q), q)
    notes_only = "## 审计报告附注\n华清股份有限公司 税率说明。\n" * 5
    cost_detail = (
        "## 31 、销售费用\n"
        "华清 2025 销售费用 12,000,000.00 管理费用 8,000,000.00 营业成本 500,000,000.00\n"
        "| 职工薪酬 | 1 | 2 |\n"
    )
    appendix = (
        "## 31 、销售费用\n| 职工薪酬 | 10,802,366.11 | 23,295,127.31 |\n"
        "| 市场推广广告费 | 2,889,547.75 | 1,526,703.85 |\n"
    )
    s_notes = kp._score_chunk_for_retrieval(notes_only, terms, q)
    s_cost = kp._score_chunk_for_retrieval(cost_detail, terms, q)
    s_app = kp._score_chunk_for_retrieval(appendix, terms, q)
    assert is_fee_appendix_chunk(appendix)
    assert s_app > s_notes
    assert s_cost > s_notes


def test_entity_penalty_relaxed_when_folder_scoped():
    q = "华清25、24两年销售费用明细对比"
    terms = kp._expand_retrieval_terms(kp._tokenize_query(q), q)
    parent_pl = (
        "## 母公司利润表\n| 销售费用 | 8,851,536.62 | 17,783,841.20 |\n"
        "| 管理费用 | 35,929,638.22 | 45,594,892.28 |\n"
    )
    s_strict = kp._score_chunk_for_retrieval(parent_pl, terms, q, entity_scope_relaxed=False)
    s_relaxed = kp._score_chunk_for_retrieval(parent_pl, terms, q, entity_scope_relaxed=True)
    assert s_relaxed > s_strict
    assert kp.entity_scope_relaxed_from_kb(limit_to_attached=True)
    assert kp.entity_scope_relaxed_from_kb(folder_ids=["f_x"])
