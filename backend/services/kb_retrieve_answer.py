"""统一 KB 检索入口：Agent 预检索、AI 互动 RAG、冒烟/单测共用。"""

from __future__ import annotations

from typing import Any

from backend.config import settings
from backend.services.kb_retrieve_pack import retrieve_kb_evidence_pack


def kb_multi_query_enabled() -> bool:
    """多 query 开关：优先 `KB_MULTI_QUERY`，否则 `HERMES_AGENT_KB_MULTI_QUERY`。"""
    return bool(getattr(settings, "effective_kb_multi_query", True))


def retrieve_and_answer(
    user_token: str,
    user_query: str,
    kb_scope: dict[str, list[str]],
    *,
    fixtures: dict[str, Any] | None = None,
    attached_doc_ids: list[str] | None = None,
    limit_to_attached: bool | None = None,
    multi_query: bool | None = None,
    resolved_scope: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """
    返回 (检索结果, tool_calls)。
    结果含 ok、citations、reply、evidence_pack（与 `retrieve_kb_evidence_pack` 相同）。
    """
    use_multi = kb_multi_query_enabled() if multi_query is None else bool(multi_query)
    return retrieve_kb_evidence_pack(
        user_token,
        user_query,
        kb_scope,
        fixtures=fixtures,
        attached_doc_ids=attached_doc_ids,
        limit_to_attached=limit_to_attached,
        multi_query=use_multi,
        resolved_scope=resolved_scope,
    )
