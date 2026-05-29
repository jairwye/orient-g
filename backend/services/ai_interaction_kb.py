"""AI 互动知识库检索：与 Agent 共用 Evidence Pack + 多 query。"""

from __future__ import annotations

from typing import Any

from backend.services.evidence_pack import pack_summary_for_sse
from backend.services.kb_retrieve_answer import kb_multi_query_enabled, retrieve_and_answer
from backend.services.knowledge_acl import load_fixtures


def retrieve_kb_for_chat(
    user_token: str,
    query: str,
    *,
    selected_collection_ids: list[str] | None,
    selected_table_ids: list[str] | None,
    attached_doc_ids: list[str] | None,
    limit_to_attached: bool,
    fixtures: dict[str, Any] | None = None,
    multi_query: bool | None = None,
) -> dict[str, Any]:
    """
    对话页 RAG：多 query 检索并返回 pack 兼容结构（ok、citations、reply、evidence_pack）。
    """
    fixtures = fixtures or load_fixtures()
    use_multi = bool(multi_query) if multi_query is not None else kb_multi_query_enabled()
    result, _tools = retrieve_and_answer(
        user_token,
        query,
        {},
        fixtures=fixtures,
        attached_doc_ids=list(attached_doc_ids or []) or None,
        limit_to_attached=limit_to_attached,
        multi_query=use_multi,
        resolved_scope={
            "collection_ids": list(selected_collection_ids or []),
            "table_ids": list(selected_table_ids or []),
            "attached_doc_ids": list(attached_doc_ids or []),
            "limit_to_attached": bool(limit_to_attached),
        },
    )
    return result


def citations_for_chat_llm(
    prefetch_result: dict[str, Any],
    user_query: str,
    *,
    tenant_id: str,
    fixtures: dict[str, Any],
) -> list[dict[str, Any]]:
    """与 Agent synthesize 相同的 citation 重排，保证两页证据一致。"""
    from backend.services.agent_kb_prefetch import _top_citations_for_llm

    pack = prefetch_result.get("evidence_pack") or {}
    task_type = str(pack.get("task_type") or prefetch_result.get("task_type") or "")
    max_per_doc = 2 if task_type == "breakdown" else 1
    cite_limit = 8 if task_type in ("breakdown", "compare") else 6
    return _top_citations_for_llm(
        list(prefetch_result.get("citations") or []),
        user_query,
        limit=cite_limit,
        tenant_id=tenant_id,
        fixtures=fixtures,
        max_chunks_per_doc=max_per_doc,
    )


def attach_pack_to_chat_response(res: dict[str, Any]) -> dict[str, Any]:
    """向 API 响应附加精简 evidence_pack 摘要。"""
    pack = res.get("evidence_pack")
    if isinstance(pack, dict):
        res["evidence_pack"] = pack_summary_for_sse(pack)
    return res
