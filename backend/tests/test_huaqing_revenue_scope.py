"""华清营收：合并 vs 母公司口径 — Agent 与对话检索应一致（默认合并）。"""

from __future__ import annotations

import pytest

from backend.services.agent_kb_prefetch import _top_citations_for_llm
from backend.services.ai_interaction_llm import _load_doc_chunk_text
from backend.services.knowledge_acl import load_fixtures
from backend.services.knowledge_pipeline import (
    _score_chunk_for_retrieval,
    _tokenize_query,
    _expand_retrieval_terms,
    statement_scope_score_delta,
)
from backend.tests.test_acl_folder_shared_docs import FOLDER_JINGPIN_CAIBAO_25, _finance_token
from backend.services.kb_scope_resolve import resolve_kb_scope_for_ask
from backend.services.knowledge_pipeline import ask_knowledge

MERGED_DOC = "ud_91f55322e2594b9c9d3ba7ceb89fafb2"
PARENT_DOC = "ud_67d0f860dbbb4196861d5ab97b472584"
MERGED_REVENUE = "100,148,026.24"
PARENT_REVENUE = "56,071,477.26"


def test_statement_scope_prefers_merged_for_revenue_query():
    merged_txt = _load_doc_chunk_text(
        "tenant1", MERGED_DOC, f"{MERGED_DOC}_s0001", None
    ) or ""
    parent_txt = _load_doc_chunk_text(
        "tenant1", PARENT_DOC, f"{PARENT_DOC}_s0001", None
    ) or ""
    q = "华清25年营收是多少"
    assert MERGED_REVENUE in merged_txt
    assert PARENT_REVENUE in parent_txt
    assert statement_scope_score_delta(merged_txt, q) > statement_scope_score_delta(parent_txt, q)


def test_top_citations_revenue_query_ranks_merged_first():
    token = _finance_token()
    fixtures = load_fixtures()
    q = "华清25年营收是多少"
    resolved = resolve_kb_scope_for_ask(
        "tenant1", {"selected_folder_ids": [FOLDER_JINGPIN_CAIBAO_25]}
    )
    out = ask_knowledge(
        token,
        q,
        selected_collection_ids=resolved["collection_ids"] or None,
        attached_doc_ids=resolved["attached_doc_ids"] or None,
        limit_to_attached=bool(resolved.get("limit_to_attached")),
        fixtures=fixtures,
    )
    top = _top_citations_for_llm(
        list(out.get("citations") or []),
        q,
        limit=3,
        tenant_id="tenant1",
        fixtures=fixtures,
    )
    top_ids = [c.get("doc_id") for c in top]
    assert MERGED_DOC in top_ids[:2], f"expected merged P&L in top2, got {top_ids}"


def test_compare_query_top_includes_merged_or_states_parent():
    """对比表可含合并；若仅母公司须与对话页营收口径区分。"""
    token = _finance_token()
    fixtures = load_fixtures()
    q = "做一张华清25和24年损益对比的表，仅依据知识库证据，缺项请说明。"
    resolved = resolve_kb_scope_for_ask(
        "tenant1", {"selected_folder_ids": [FOLDER_JINGPIN_CAIBAO_25]}
    )
    out = ask_knowledge(
        token,
        q,
        selected_collection_ids=resolved["collection_ids"] or None,
        attached_doc_ids=resolved["attached_doc_ids"] or None,
        limit_to_attached=bool(resolved.get("limit_to_attached")),
        fixtures=fixtures,
    )
    top = _top_citations_for_llm(
        list(out.get("citations") or []),
        q,
        limit=5,
        tenant_id="tenant1",
        fixtures=fixtures,
    )
    top_ids = [c.get("doc_id") for c in top]
    assert MERGED_DOC in top_ids or PARENT_DOC in top_ids
    if MERGED_DOC in top_ids:
        assert top_ids.index(MERGED_DOC) <= top_ids.index(PARENT_DOC) if PARENT_DOC in top_ids else True
