"""多 query 知识库检索并构建 Evidence Pack。"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

from backend.config import settings
from backend.services.evidence_pack import build_evidence_pack, merge_citations
from backend.services.kb_retrieval_plan import (
    TaskType,
    detect_entity,
    infer_task_type,
    plan_retrieval_queries,
)
from backend.services.kb_scope_resolve import resolve_kb_scope_for_ask
from backend.services.knowledge_acl import load_fixtures
from backend.services.kb_scope_context import build_scope_folder_context
from backend.services.knowledge_pipeline import ask_knowledge, entity_scope_relaxed_from_kb


def retrieve_kb_evidence_pack(
    user_token: str,
    user_query: str,
    kb_scope: dict[str, list[str]],
    *,
    fixtures: dict[str, Any] | None = None,
    attached_doc_ids: list[str] | None = None,
    limit_to_attached: bool | None = None,
    multi_query: bool | None = None,
    resolved_scope: dict[str, Any] | None = None,
    prefetch_tier: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """
    返回 (prefetch 兼容结果, tool_calls)。
    结果含 ok、citations、reply、evidence_pack。
    """
    fixtures = fixtures or load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    q = (user_query or "").strip()
    if not q:
        return {"ok": False, "denied": True, "reason": "empty query", "citations": []}, []

    if resolved_scope is None:
        resolved_scope = resolve_kb_scope_for_ask(
            tenant_id,
            kb_scope,
            attached_doc_ids=attached_doc_ids,
        )
    cols = list(resolved_scope.get("collection_ids") or [])
    tables = list(resolved_scope.get("table_ids") or [])
    attached = list(resolved_scope.get("attached_doc_ids") or [])
    lim = resolved_scope.get("limit_to_attached") if limit_to_attached is None else limit_to_attached
    relax_entity = entity_scope_relaxed_from_kb(
        limit_to_attached=bool(lim),
        folder_ids=list(resolved_scope.get("folder_ids") or []),
    )
    scope_ctx = build_scope_folder_context(
        tenant_id,
        selected_folder_ids=list(resolved_scope.get("folder_ids") or []),
    )
    doc_labels = scope_ctx.get("doc_folder_labels") if isinstance(scope_ctx.get("doc_folder_labels"), dict) else {}
    multi_co = bool(scope_ctx.get("multi_company_scope"))

    use_multi = bool(multi_query) if multi_query is not None else bool(
        settings.effective_kb_multi_query
    )
    task_type = infer_task_type(q)
    entity = detect_entity(q)
    queries = (
        plan_retrieval_queries(q, task_type, entity=entity, prefetch_tier=prefetch_tier)
        if use_multi
        else [q]
    )

    tool_calls: list[dict[str, Any]] = []
    cite_lists: list[list[dict[str, Any]]] = []
    reply_parts: list[str] = []
    deny_reasons: list[str] = []

    for sub_q in queries:
        res = ask_knowledge(
            user_token,
            sub_q,
            selected_collection_ids=cols or None,
            selected_table_ids=tables or None,
            fixtures=fixtures,
            attached_doc_ids=attached or None,
            limit_to_attached=bool(lim),
            entity_scope_relaxed=relax_entity,
        )
        if res.get("denied"):
            reason = str(res.get("deny_reason") or res.get("reason") or "denied")
            deny_reasons.append(f"{sub_q[:40]}: {reason}")
            tool_calls.append(
                {
                    "name": "orientg_kb_ask",
                    "status": "denied",
                    "prefetch": True,
                    "query": sub_q,
                    "result": res,
                }
            )
            continue
        cites = list(res.get("citations") or [])
        cite_lists.append(cites)
        if res.get("reply"):
            reply_parts.append(str(res.get("reply")))
        tool_calls.append(
            {
                "name": "orientg_kb_ask",
                "status": "ok",
                "prefetch": True,
                "query": sub_q,
                "result": {"ok": True, "citation_count": len(cites), "reply": res.get("reply")},
            }
        )

    if deny_reasons and not cite_lists:
        return {
            "ok": False,
            "denied": True,
            "reason": "; ".join(deny_reasons),
            "citations": [],
        }, tool_calls

    merged = merge_citations(cite_lists)
    if tables:
        from backend.services.kb_tables import retrieve_table_evidence

        try:
            tr = retrieve_table_evidence(
                tenant_id,
                selected_table_ids=set(tables),
                query=q,
            )
            ev = tr.get("evidence")
            if isinstance(ev, dict) and ev.get("table_id"):
                merged = merge_citations([merged, [ev]])
                av = tr.get("answer_value")
                if av is not None:
                    reply_parts.append(f"表格证据已匹配：{av}。")
        except Exception as exc:
            logger.warning("retrieve_table_evidence failed: %s", exc, exc_info=True)
            reply_parts.append("表格证据检索暂不可用。")

    pack = build_evidence_pack(
        user_query=q,
        task_type=task_type.value,
        retrieval_queries=queries,
        citations=merged,
        reply_parts=reply_parts,
        tenant_id=tenant_id,
        fixtures=fixtures,
        doc_folder_labels=doc_labels,
        multi_company_scope=multi_co,
    )
    if relax_entity:
        pack = {**pack, "entity_scope_relaxed": True}
    if scope_ctx.get("doc_folder_labels"):
        pack = {
            **pack,
            "doc_folder_labels": scope_ctx.get("doc_folder_labels"),
            "scope_folders": scope_ctx.get("scope_folders") or [],
            "multi_company_scope": bool(scope_ctx.get("multi_company_scope")),
        }

    if deny_reasons:
        extra_gaps = list(pack.get("gaps") or [])
        extra_gaps.append(f"部分子检索无权限（{len(deny_reasons)} 条）")
        pack = {**pack, "gaps": extra_gaps, "partial_subquery_denied": True}

    return {
        "ok": True,
        "citations": merged,
        "reply": pack.get("reply") or "",
        "evidence_pack": pack,
        "task_type": task_type.value,
        "partial_denied": bool(deny_reasons),
    }, tool_calls
