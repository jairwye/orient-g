"""Agent 知识库问答（本地 LLM）：与 AI 互动对齐——文件夹解析、直接读文档、检索综合。"""

from __future__ import annotations

from typing import Any

from backend.config import settings
from backend.services.agent_kb_prefetch import prefetch_kb_context, synthesize_kb_reply
from backend.services.kb_scope_resolve import resolve_kb_scope_for_ask
from backend.services.knowledge_acl import compute_acl_scope


def run_agent_kb_local_answer(
    *,
    user_token: str,
    tenant_id: str,
    username: str,
    user_query: str,
    kb_scope_payload: dict[str, list[str]],
    attached_doc_ids: list[str],
    fixtures: dict[str, Any],
    enabled_skills: list[str] | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """
    有 kb_scope 且 HERMES_AGENT_KB_SYNTHESIZE=false 时的完整路径。
    """
    resolved = resolve_kb_scope_for_ask(
        tenant_id,
        kb_scope_payload,
        attached_doc_ids=attached_doc_ids,
    )
    raw_folder_ids = list(resolved.get("folder_ids") or [])
    raw_attached = list(attached_doc_ids or [])
    folder_doc_ids = list(resolved.get("folder_doc_ids") or [])

    use_model = (model or "").strip() or (
        (settings.llm_model or "").strip() if settings.llm_chat_configured else (settings.ollama_model or "").strip()
    ) or settings.ollama_model

    has_explicit_docs = bool(raw_attached or raw_folder_ids)
    skip_direct_for_large_folder = bool(raw_folder_ids) and len(folder_doc_ids) > 20

    if has_explicit_docs and settings.chat_llm_available and not skip_direct_for_large_folder:
        try:
            from backend.services.agent_skills_loader import build_system_addon_for_enabled_skills
            from backend.services.ai_interaction_llm import generate_answer_with_documents
            from backend.services.kb_direct_read import assemble_document_context, resolve_doc_ids_from_context

            doc_ids = resolve_doc_ids_from_context(
                tenant_id,
                attached_doc_ids=raw_attached if raw_attached else None,
                folder_ids=raw_folder_ids if raw_folder_ids else None,
            )
            acl_scope = compute_acl_scope(user_token, fixtures=fixtures)
            allowed = set(acl_scope.get("allowed_doc_ids") or [])
            doc_ids = [d for d in doc_ids if d in allowed]
            if doc_ids:
                doc_context, skipped = assemble_document_context(tenant_id, doc_ids)
                if doc_context:
                    skill_addon = build_system_addon_for_enabled_skills(enabled_skills or [])
                    reply = generate_answer_with_documents(
                        model=use_model,
                        user_query=user_query,
                        document_context=doc_context,
                        skill_addon=skill_addon or None,
                    )
                    if skipped:
                        reply += "\n\n（以下文档未纳入上下文：" + "；".join(skipped[:8]) + "）"
                    return {
                        "ok": True,
                        "reply": reply,
                        "citations": [{"evidence_type": "doc_chunk", "doc_id": d} for d in doc_ids[:12]],
                        "synthesis": "direct_read",
                        "llm_model": use_model,
                        "tool_calls": [{"name": "kb_direct_read", "status": "ok", "doc_count": len(doc_ids)}],
                    }
                if skipped:
                    return {
                        "ok": True,
                        "reply": (
                            "已选中知识库文档，但均无法读取正文（常见原因：仍为 uploaded 状态、Docling 未产出 "
                            "kb/sections 或 archive/full.md）。请在「知识库」确认文档已解析为 active，或重新上传/解析后再问。"
                            f"\n\n详情：{'；'.join(skipped[:6])}"
                        ),
                        "citations": [],
                        "synthesis": "direct_read_empty",
                        "llm_model": use_model,
                        "tool_calls": [{"name": "kb_direct_read", "status": "empty", "skipped": skipped}],
                    }
        except Exception:
            pass

    scope_for_ask = {
        "selected_collection_ids": resolved.get("collection_ids") or [],
        "selected_table_ids": resolved.get("table_ids") or [],
        "selected_folder_ids": [],
    }
    merged_attached = list(resolved.get("attached_doc_ids") or [])
    _msgs, prefetch_result, prefetch_tool_calls = prefetch_kb_context(
        user_token,
        [{"role": "user", "content": user_query}],
        scope_for_ask,
        attached_doc_ids=merged_attached or None,
        limit_to_attached=bool(resolved.get("limit_to_attached")),
    )
    if not prefetch_result:
        return {
            "ok": False,
            "reply": "知识库预检索失败",
            "citations": [],
            "synthesis": "error",
            "tool_calls": prefetch_tool_calls,
        }
    if prefetch_result.get("denied"):
        return {
            "ok": False,
            "reply": prefetch_result.get("deny_reason") or prefetch_result.get("reason") or "denied",
            "citations": list(prefetch_result.get("citations") or []),
            "synthesis": "denied",
            "tool_calls": prefetch_tool_calls,
        }

    synth = synthesize_kb_reply(
        tenant_id=tenant_id,
        user_query=user_query,
        prefetch_result=prefetch_result,
        fixtures=fixtures,
        enabled_skills=enabled_skills,
        model=use_model,
    )
    synth["tool_calls"] = prefetch_tool_calls
    return synth
