"""
Agent 页 API：网关 → Hermes 内网 HTTP（HERMES_ENABLED 时）。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Literal

from fastapi.responses import StreamingResponse

from backend.services.agent_kb_fast_path import (
    comparison_answer_addon,
    fast_path_answer_addon,
    finalize_fast_path_reply,
    stream_kb_fast_path_events,
)
from backend.services.agent_hermes_tier_policy import patch_prefetch_system_message
from backend.services.agent_kb_router import (
    AgentRoute,
    kb_ask_budget_for_route,
    resolve_agent_route,
    route_to_agent_tier,
)
from backend.services.evidence_pack import pack_summary_for_sse
from backend.services.agent_kb_prefetch import (
    last_user_query,
    prefetch_kb_context,
    should_prefetch_kb,
    synthesize_kb_reply,
)

import jwt
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.config import settings
from backend.services import orientg_mcp_tools as mcp_tools
from backend.services.agent_run_registry import cancel as cancel_agent_run
from backend.services.agent_run_registry import pop_hermes_run_id
from backend.services.agent_run_registry import register as register_agent_run
from backend.services.agent_run_registry import unregister as unregister_agent_run
from backend.services.hermes_client import (
    HermesClientError,
    HermesDisabledError,
    run_agent_chat,
    stop_hermes_run,
    stream_agent_chat,
)
from backend.services.hermes_settings import diagnose_hermes
from backend.services.knowledge_acl import load_fixtures

router = APIRouter()
_logger = logging.getLogger("agent")


def _skill_addon_for_route(user_query: str, route: AgentRoute) -> str:
    """Hermes 失败回退本地综合时，按路由套用对应 tier 规制。"""
    if route == AgentRoute.fast:
        return fast_path_answer_addon(user_query)
    if route == AgentRoute.hermes_full:
        return comparison_answer_addon(user_query, tier="full")
    return comparison_answer_addon(user_query, tier="lite")
ALGORITHM = "HS256"


def _route_response_meta(route: AgentRoute, prefetch_result: dict[str, Any] | None) -> dict[str, Any]:
    pack = (prefetch_result or {}).get("evidence_pack") if prefetch_result else None
    return {
        "agent_route": route.value,
        "agent_tier": route_to_agent_tier(route),
        "evidence_pack": pack_summary_for_sse(pack if isinstance(pack, dict) else None),
    }


def _get_token_from_request(request: Request) -> str | None:
    auth = request.headers.get("Authorization") or ""
    if auth.startswith("Bearer "):
        t = auth[7:].strip()
        if t:
            return t
    return request.headers.get("X-Auth-Token") or None


def _get_username_from_request(request: Request) -> str | None:
    token = _get_token_from_request(request)
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.auth_secret, algorithms=[ALGORITHM])
        return (payload.get("sub") or "").strip() or None
    except Exception:
        return None


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class KbScope(BaseModel):
    selected_collection_ids: list[str] | None = None
    selected_table_ids: list[str] | None = None
    selected_folder_ids: list[str] | None = None


class AgentChatBody(BaseModel):
    messages: list[ChatMessage]
    kb_scope: KbScope | None = None
    attached_doc_ids: list[str] | None = None
    allow_kb_write: bool = False
    hermes_session_id: str | None = None
    orientg_chat_session_id: str | None = Field(
        default=None,
        description="Orient-G 智能体侧栏会话 id；用于稳定绑定 Hermes session（按用户隔离）",
    )
    enabled_skills: list[str] | None = None
    model: str | None = None
    agent_mode: Literal["auto", "fast", "standard", "deep"] | None = "standard"


class AgentCancelBody(BaseModel):
    run_id: str = Field(..., min_length=1, max_length=128)


def _normalized_agent_mode(body: AgentChatBody) -> str:
    mode = (body.agent_mode or "standard").strip().lower()
    if mode not in ("auto", "fast", "standard", "deep"):
        return "standard"
    return mode


def _effective_allow_kb_write(body: AgentChatBody) -> bool:
    """写库仅深度模式且用户显式开启 allow_kb_write。"""
    if not body.allow_kb_write:
        return False
    return _normalized_agent_mode(body) == "deep"


def _assert_agent_stream_client(request: Request, *, has_kb_scope: bool) -> None:
    if not has_kb_scope or not getattr(settings, "agent_require_run_id", False):
        return
    run_id = (request.headers.get("X-Agent-Run-Id") or "").strip()
    if not run_id:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "agent_run_id_required",
                "message": "带知识库范围的 Agent 流式请求须携带 X-Agent-Run-Id",
            },
        )


def _resolve_route_for_body(
    *,
    body: AgentChatBody,
    messages: list[dict[str, str]],
    kb_scope_payload: dict[str, list[str]],
    attached: list[str],
    prefetch_result: dict[str, Any] | None,
) -> tuple[AgentRoute, int | None]:
    has_kb = should_prefetch_kb(kb_scope_payload, attached_doc_ids=attached)
    route = resolve_agent_route(
        user_query=last_user_query(messages),
        agent_mode=_normalized_agent_mode(body),
        allow_kb_write=_effective_allow_kb_write(body),
        has_kb_scope=has_kb,
        prefetch_result=prefetch_result,
        hermes_configured=settings.hermes_configured,
    )
    return route, kb_ask_budget_for_route(route)


def _dev_mock_agent_chat(
    *,
    user_token: str,
    messages: list[dict[str, str]],
    kb_scope_payload: dict[str, list[str]],
    attached_doc_ids: list[str],
    hermes_session_id: str | None,
) -> dict[str, Any]:
    """
    开发机（无 Docker/Hermes）：直接调用 orientg MCP 工具，模拟 Agent 一次 tool 回合。
    不替代生产 Hermes 编排，仅用于 Windows 本地验 MCP + /agent UI。
    """
    query = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            query = (m.get("content") or "").strip()
            break
    cols = list(kb_scope_payload.get("selected_collection_ids") or [])
    if not cols and not attached_doc_ids:
        cols = ["c_finance_public_1"]
    ask_res = mcp_tools.orientg_kb_ask(
        user_token,
        query,
        selected_collection_ids=cols or None,
        selected_table_ids=kb_scope_payload.get("selected_table_ids") or None,
        attached_doc_ids=attached_doc_ids or None,
    )
    list_res = mcp_tools.orientg_kb_list_docs(user_token, limit=5)
    tool_calls = [
        {"name": "orientg_kb_ask", "status": "ok" if ask_res.get("ok") else "denied", "result": ask_res},
        {"name": "orientg_kb_list_docs", "status": "ok", "result": {"count": len(list_res.get("items") or [])}},
    ]
    if ask_res.get("ok"):
        reply = (ask_res.get("reply") or "").strip() or "（检索无摘要文本）"
        cites = ask_res.get("citations") or []
        if cites:
            reply += f"\n\n（共 {len(cites)} 条引用，见 tool_calls）"
    else:
        reply = f"[开发 mock] MCP 检索未通过：{ask_res.get('reason') or 'unknown'}"
    sid = hermes_session_id or "dev_mock_session"
    return {
        "reply": reply,
        "tool_calls": tool_calls,
        "hermes_session_id": sid,
        "artifacts": [],
        "dev_mock": True,
    }


@router.get("/status")
def agent_status():
    diag = diagnose_hermes()
    return {
        **diag,
        "searxng_enabled": bool(settings.hermes_searxng_enabled),
        "lark_cli_enabled": bool(settings.hermes_lark_cli_enabled),
    }


@router.post("/chat")
def agent_chat(request: Request, body: AgentChatBody):
    token = _get_token_from_request(request)
    if not token:
        raise HTTPException(status_code=401, detail="not authenticated")

    uname = _get_username_from_request(request)
    if not uname:
        raise HTTPException(status_code=401, detail="invalid token")

    messages = [{"role": m.role, "content": (m.content or "").strip()} for m in (body.messages or [])]
    if not any(m["role"] == "user" and m["content"] for m in messages):
        raise HTTPException(status_code=400, detail="empty user message")

    scope = body.kb_scope or KbScope()
    kb_scope_payload = {
        "selected_collection_ids": [str(x).strip() for x in (scope.selected_collection_ids or []) if str(x).strip()],
        "selected_table_ids": [str(x).strip() for x in (scope.selected_table_ids or []) if str(x).strip()],
        "selected_folder_ids": [str(x).strip() for x in (scope.selected_folder_ids or []) if str(x).strip()],
    }

    fixtures = load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    attached = [str(x).strip() for x in (body.attached_doc_ids or []) if str(x).strip()]

    if settings.hermes_dev_mock and not settings.hermes_configured:
        result = _dev_mock_agent_chat(
            user_token=token,
            messages=messages,
            kb_scope_payload=kb_scope_payload,
            attached_doc_ids=attached,
            hermes_session_id=body.hermes_session_id,
        )
        return {
            "ok": True,
            "tenant_id": tenant_id,
            "reply": result.get("reply") or "",
            "tool_calls": result.get("tool_calls") or [],
            "hermes_session_id": result.get("hermes_session_id"),
            "artifacts": result.get("artifacts") or [],
            "dev_mock": True,
        }

    has_kb_scope = should_prefetch_kb(kb_scope_payload, attached_doc_ids=attached)
    prefetch_tool_calls: list[dict[str, Any]] = []
    prefetch_result: dict[str, Any] | None = None
    hermes_messages = messages

    if settings.hermes_agent_kb_prefetch and has_kb_scope and not settings.hermes_agent_kb_synthesize:
        from backend.services.agent_kb_local import run_agent_kb_local_answer

        query = last_user_query(messages)
        synth = run_agent_kb_local_answer(
            user_token=token,
            tenant_id=tenant_id,
            username=uname,
            user_query=query,
            kb_scope_payload=kb_scope_payload,
            attached_doc_ids=attached,
            fixtures=fixtures,
            enabled_skills=body.enabled_skills,
            model=body.model,
        )
        if not synth.get("ok"):
            raise HTTPException(status_code=403, detail=synth.get("reply") or "denied")
        return {
            "ok": True,
            "tenant_id": tenant_id,
            "reply": synth.get("reply") or "",
            "citations": synth.get("citations") or [],
            "tool_calls": list(synth.get("tool_calls") or []),
            "hermes_session_id": body.hermes_session_id,
            "artifacts": [],
            "kb_prefetch": True,
            "hermes_used": False,
            "synthesis": synth.get("synthesis"),
            "llm_model": synth.get("llm_model"),
        }

    if settings.hermes_agent_kb_prefetch and has_kb_scope:
        hermes_messages, prefetch_result, prefetch_tool_calls = prefetch_kb_context(
            token,
            messages,
            kb_scope_payload,
            attached_doc_ids=attached,
            agent_mode=(body.agent_mode or "standard"),
            enabled_skills=body.enabled_skills,
        )
        if prefetch_result and prefetch_result.get("denied"):
            raise HTTPException(
                status_code=403,
                detail=prefetch_result.get("reason") or prefetch_result.get("deny_reason") or "denied",
            )

    agent_route, kb_ask_budget = _resolve_route_for_body(
        body=body,
        messages=messages,
        kb_scope_payload=kb_scope_payload,
        attached=attached,
        prefetch_result=prefetch_result,
    )
    if has_kb_scope and prefetch_result is not None:
        hermes_messages = patch_prefetch_system_message(
            hermes_messages,
            orientg_route=agent_route.value,
            evidence_pack=(prefetch_result or {}).get("evidence_pack"),
            agent_mode=(body.agent_mode or "standard"),
        )
    user_query = last_user_query(messages)
    if agent_route == AgentRoute.fast and prefetch_result:
        synth = synthesize_kb_reply(
            tenant_id=tenant_id,
            user_query=user_query,
            prefetch_result=prefetch_result,
            fixtures=fixtures,
            enabled_skills=body.enabled_skills,
            model=body.model,
            skill_addon_extra=fast_path_answer_addon(user_query) or None,
        )
        return {
            "ok": True,
            "tenant_id": tenant_id,
            "reply": finalize_fast_path_reply(synth.get("reply") or "", user_query=user_query),
            "citations": synth.get("citations") or [],
            "tool_calls": prefetch_tool_calls,
            "hermes_session_id": body.hermes_session_id,
            "artifacts": [],
            "kb_prefetch": True,
            "kb_fast_path": True,
            "hermes_used": False,
            "synthesis": synth.get("synthesis"),
            "llm_model": synth.get("llm_model"),
            **_route_response_meta(agent_route, prefetch_result),
        }

    if has_kb_scope and not settings.hermes_configured and agent_route != AgentRoute.fast:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "hermes_disabled",
                "message": "已选择知识库范围，但 Hermes 未启用且无法完成 KB 问答",
                "hint": "配置 HERMES_ENABLED 或 LLM_BASE_URL+LLM_MODEL（与 AI 互动相同）",
            },
        )

    if not has_kb_scope and not settings.hermes_configured:
        if settings.chat_llm_available:
            from backend.services.agent_skills_loader import build_system_addon_for_enabled_skills
            from backend.services.ai_interaction_llm import generate_chat_reply

            skill_addon = build_system_addon_for_enabled_skills(body.enabled_skills or [])
            use_model = (body.model or "").strip() or (
                (settings.llm_model or "").strip() if settings.llm_chat_configured else (settings.ollama_model or "").strip()
            ) or settings.ollama_model
            reply = generate_chat_reply(
                model=use_model,
                messages=messages,
                skill_addon=skill_addon or None,
            )
            return {
                "ok": True,
                "tenant_id": tenant_id,
                "reply": reply,
                "tool_calls": [],
                "hermes_session_id": body.hermes_session_id,
                "artifacts": [],
                "hermes_used": False,
                "synthesis": "local_llm",
                "llm_model": use_model,
            }
        raise HTTPException(
            status_code=503,
            detail={
                "code": "hermes_disabled",
                "message": "智能体需要 Hermes 或未选 KB 时配置对话 LLM",
                "hint": "见 docs/hermes.md §2",
            },
        )

    try:
        result = run_agent_chat(
            messages=hermes_messages,
            username=uname,
            user_token=token,
            kb_scope=kb_scope_payload,
            allow_kb_write=_effective_allow_kb_write(body),
            hermes_session_id=body.hermes_session_id,
            orientg_chat_session_id=body.orientg_chat_session_id,
            attached_doc_ids=attached,
            orientg_route=agent_route.value,
            orientg_kb_ask_budget=kb_ask_budget,
            evidence_pack=(prefetch_result or {}).get("evidence_pack"),
            enabled_skills=body.enabled_skills,
        )
    except HermesDisabledError as e:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "hermes_disabled",
                "message": str(e),
                "hint": "见 docs/hermes.md：开发 §2（Hermes CLI + 本机 MCP），生产 §3（Docker）",
            },
        ) from e
    except HermesClientError as e:
        _logger.warning("hermes chat failed: %s", e, exc_info=True)
        if prefetch_result and prefetch_result.get("ok"):
            uq = last_user_query(messages)
            synth = synthesize_kb_reply(
                tenant_id=tenant_id,
                user_query=uq,
                prefetch_result=prefetch_result,
                fixtures=fixtures,
                enabled_skills=body.enabled_skills,
                model=body.model,
                skill_addon_extra=_skill_addon_for_route(uq, agent_route) or None,
            )
            reply = finalize_fast_path_reply((synth.get("reply") or "").strip(), user_query=uq)
            if reply:
                reply += "\n\n（Hermes 调用失败，已由本地 LLM 基于检索证据作答）"
            return {
                "ok": True,
                "tenant_id": tenant_id,
                "reply": reply,
                "citations": synth.get("citations") or [],
                "tool_calls": prefetch_tool_calls,
                "hermes_session_id": body.hermes_session_id,
                "artifacts": [],
                "kb_prefetch": True,
                "hermes_used": False,
                "hermes_fallback": True,
                "synthesis": synth.get("synthesis"),
                **_route_response_meta(agent_route, prefetch_result),
            }
        raise HTTPException(
            status_code=502,
            detail={"code": "hermes_error", "message": str(e), "status_code": e.status_code, "detail": e.detail},
        ) from e

    merged_tools = [*prefetch_tool_calls, *(result.get("tool_calls") or [])]
    reply = result.get("reply") or ""
    citations = result.get("citations")
    synthesis = "hermes"
    kb_supplemental = False
    from backend.services.agent_kb_supplemental import (
        apply_supplemental_to_done,
        hermes_orientg_kb_ask_count,
        iter_supplemental_revision_events,
        needs_hermes_supplemental,
    )

    uq = last_user_query(messages)
    if needs_hermes_supplemental(
        agent_route=agent_route,
        prefetch_result=prefetch_result,
        hermes_kb_ask_count=hermes_orientg_kb_ask_count(hermes_payload=result),
        hermes_reply=reply,
        user_query=uq,
    ):
        sup_meta: dict[str, Any] | None = None
        for sup_evt in iter_supplemental_revision_events(
            user_token=token,
            tenant_id=tenant_id,
            user_query=uq,
            prefetch_result=prefetch_result or {},
            prefetch_tool_calls=prefetch_tool_calls,
            kb_scope=kb_scope_payload,
            attached_doc_ids=attached,
            fixtures=fixtures,
            agent_route=agent_route,
            enabled_skills=body.enabled_skills,
            model=body.model,
            hermes_reply=reply,
        ):
            if sup_evt.get("type") == "supplemental_meta":
                sup_meta = sup_evt
        if sup_meta:
            done_like = apply_supplemental_to_done(
                {"reply": reply, "tool_calls": merged_tools, "citations": citations},
                supplemental_meta=sup_meta,
                prefetch_tool_calls=prefetch_tool_calls,
            )
            reply = done_like.get("reply") or reply
            merged_tools = done_like.get("tool_calls") or merged_tools
            citations = done_like.get("citations")
            synthesis = sup_meta.get("synthesis") or "hermes_supplemental_revise"
            kb_supplemental = True
            if sup_meta.get("supplemental_adopted") is False:
                synthesis = "hermes_kept_after_supplemental"
            prefetch_result = sup_meta.get("prefetch_result") or prefetch_result

    from backend.services.hermes_stream_sanitize import finalize_agent_reply

    reply = finalize_agent_reply(
        reply,
        user_query=uq,
        tier2_native=(agent_route == AgentRoute.hermes_full),
    )

    return {
        "ok": True,
        "tenant_id": tenant_id,
        "reply": reply,
        "citations": citations,
        "tool_calls": merged_tools,
        "hermes_session_id": result.get("hermes_session_id"),
        "artifacts": result.get("artifacts") or [],
        "kb_prefetch": bool(prefetch_tool_calls),
        "kb_supplemental": kb_supplemental,
        "hermes_used": True,
        "synthesis": synthesis,
        **_route_response_meta(agent_route, prefetch_result),
    }


def _yield_local_llm_stream_fallback(
    *,
    messages: list[dict[str, str]],
    body: AgentChatBody,
    tenant_id: str,
    agent_route: AgentRoute,
    prefetch_tool_calls: list[dict[str, Any]],
    prefetch_result: dict[str, Any] | None,
    status_message: str,
) -> Any:
    """无 KB 范围时 Hermes 失败：回退本地对话 LLM（与非流式 /agent 无 scope 路径一致）。"""
    from backend.services.agent_skills_loader import build_system_addon_for_enabled_skills
    from backend.services.ai_interaction_llm import generate_chat_reply

    yield f"data: {json.dumps({'type': 'status', 'message': status_message, 'step': 'hermes_fallback'}, ensure_ascii=False)}\n\n"
    skill_addon = build_system_addon_for_enabled_skills(body.enabled_skills or [])
    use_model = (body.model or "").strip() or (
        (settings.llm_model or "").strip() if settings.llm_chat_configured else (settings.ollama_model or "").strip()
    ) or settings.ollama_model
    reply = generate_chat_reply(
        model=use_model,
        messages=messages,
        skill_addon=skill_addon or None,
    )
    yield f"data: {json.dumps({'type': 'delta', 'content': reply}, ensure_ascii=False)}\n\n"
    yield f"data: {json.dumps({'type': 'done', 'ok': True, 'reply': reply, 'tenant_id': tenant_id, 'kb_prefetch': bool(prefetch_tool_calls), 'hermes_fallback': True, 'hermes_used': False, 'synthesis': 'local_llm', 'llm_model': use_model, 'tool_calls': prefetch_tool_calls, 'citations': (prefetch_result or {}).get('citations') or [], 'agent_route': agent_route.value, 'agent_tier': route_to_agent_tier(agent_route)}, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"


def _agent_chat_stream_events(
    *,
    token: str,
    uname: str,
    tenant_id: str,
    messages: list[dict[str, str]],
    kb_scope_payload: dict[str, list[str]],
    attached: list[str],
    body: AgentChatBody,
    prefetch_tool_calls: list[dict[str, Any]],
    prefetch_result: dict[str, Any] | None,
    fixtures: dict[str, Any],
    run_id: str | None = None,
    agent_route: AgentRoute = AgentRoute.hermes_lite,
    kb_ask_budget: int | None = None,
) -> Any:
    """SSE：Hermes 流式；失败且已有预检索时回退本地 LLM 综合；无 KB 时 Hermes 失败亦回退本地对话 LLM。"""
    from backend.services.agent_kb_router import hermes_prefetch_status_message

    has_kb_scope = should_prefetch_kb(kb_scope_payload, attached_doc_ids=attached)

    if prefetch_tool_calls:
        msg = hermes_prefetch_status_message(agent_route)
        pack_sse = pack_summary_for_sse((prefetch_result or {}).get("evidence_pack"))
        yield f"data: {json.dumps({'type': 'status', 'message': msg, 'step': 'prefetch_done', 'agent_route': agent_route.value, 'agent_tier': route_to_agent_tier(agent_route), 'evidence_pack': pack_sse}, ensure_ascii=False)}\n\n"
        for tc in prefetch_tool_calls:
            name = str(tc.get("name") or "orientg_kb")
            yield f"data: {json.dumps({'type': 'tool_call', 'name': name, 'status': tc.get('status') or 'ok', 'message': f'预检索：{name}'}, ensure_ascii=False)}\n\n"

    from backend.services.agent_kb_supplemental import (
        needs_hermes_supplemental,
        prefetch_defers_hermes_draft_to_process,
    )

    defer_hermes_draft = prefetch_defers_hermes_draft_to_process(
        agent_route=agent_route,
        prefetch_result=prefetch_result,
    )
    if defer_hermes_draft:
        yield f"data: {json.dumps({'type': 'status', 'message': 'Hermes 编排过程稿将写入执行过程（非最终答案）…', 'step': 'hermes_draft_begin'}, ensure_ascii=False)}\n\n"

    from backend.services.hermes_stream_sanitize import HermesDraftTraceAccumulator

    hermes_draft_acc = (
        HermesDraftTraceAccumulator()
        if agent_route in (AgentRoute.hermes_lite, AgentRoute.hermes_full)
        else None
    )

    try:
        for evt in stream_agent_chat(
            messages=messages,
            username=uname,
            user_token=token,
            kb_scope=kb_scope_payload,
            allow_kb_write=_effective_allow_kb_write(body),
            hermes_session_id=body.hermes_session_id,
            orientg_chat_session_id=body.orientg_chat_session_id,
            attached_doc_ids=attached,
            run_id=run_id,
            orientg_route=agent_route.value,
            orientg_kb_ask_budget=kb_ask_budget,
            evidence_pack=(prefetch_result or {}).get("evidence_pack"),
            enabled_skills=body.enabled_skills,
        ):
            if evt.get("type") == "error" and evt.get("code") == "cancelled":
                yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
                return
            if evt.get("type") == "error" and not has_kb_scope and settings.chat_llm_available:
                if evt.get("code") == "hermes_empty":
                    fb_msg = "Hermes 未返回正文，Orient-G 改用本地 LLM 作答（未选知识库）。"
                else:
                    fb_msg = str(evt.get("message") or "Hermes 调用异常") + "；Orient-G 改用本地 LLM 作答（未选知识库）。"
                yield from _yield_local_llm_stream_fallback(
                    messages=messages,
                    body=body,
                    tenant_id=tenant_id,
                    agent_route=agent_route,
                    prefetch_tool_calls=prefetch_tool_calls,
                    prefetch_result=prefetch_result,
                    status_message=fb_msg,
                )
                return
            if evt.get("type") == "error" and prefetch_result and prefetch_result.get("ok"):
                if agent_route == AgentRoute.hermes_full:
                    err_payload = {
                        "type": "error",
                        "message": str(evt.get("message") or "Hermes 深度编排失败"),
                        "code": evt.get("code") or "hermes_error",
                        "hermes_fallback": False,
                    }
                    yield f"data: {json.dumps(err_payload, ensure_ascii=False)}\n\n"
                    yield "data: [DONE]\n\n"
                    return
                yield f"data: {json.dumps({'type': 'status', 'message': 'Hermes 异常结束，Orient-G 改用本地 LLM 基于预检索证据综合…', 'step': 'hermes_fallback'}, ensure_ascii=False)}\n\n"
                uq = last_user_query(messages)
                synth = synthesize_kb_reply(
                    tenant_id=tenant_id,
                    user_query=uq,
                    prefetch_result=prefetch_result,
                    fixtures=fixtures,
                    enabled_skills=body.enabled_skills,
                    model=body.model,
                    skill_addon_extra=_skill_addon_for_route(uq, agent_route) or None,
                )
                from backend.services.agent_kb_supplemental import pick_hermes_error_fallback_reply

                reply, synthesis_mode = pick_hermes_error_fallback_reply(
                    draft_acc=hermes_draft_acc,
                    synth_reply=str(synth.get("reply") or ""),
                    prefetch_result=prefetch_result,
                    user_query=uq,
                )
                if reply and synthesis_mode == "hermes_salvaged":
                    yield f"data: {json.dumps({'type': 'status', 'message': '（Hermes 已中断，终稿沿用已生成的 Hermes 过程稿）', 'step': 'hermes_salvage_note'}, ensure_ascii=False)}\n\n"
                elif reply:
                    yield f"data: {json.dumps({'type': 'status', 'message': '（Hermes 流式超时或失败，已由本地 LLM 基于预检索证据作答）', 'step': 'hermes_fallback_note'}, ensure_ascii=False)}\n\n"
                if reply:
                    yield f"data: {json.dumps({'type': 'delta', 'content': reply}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'done', 'ok': True, 'reply': reply, 'tenant_id': tenant_id, 'kb_prefetch': True, 'hermes_fallback': synthesis_mode == 'local_fallback', 'hermes_salvaged': synthesis_mode == 'hermes_salvaged', 'synthesis': synthesis_mode if synthesis_mode == 'hermes_salvaged' else synth.get('synthesis'), 'citations': synth.get('citations') or [], 'tool_calls': prefetch_tool_calls, **_route_response_meta(agent_route, prefetch_result)}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
                return
            if defer_hermes_draft and evt.get("type") == "delta" and evt.get("content"):
                draft = hermes_draft_acc.push(str(evt["content"])) if hermes_draft_acc else None
                if draft:
                    yield f"data: {json.dumps({'type': 'thinking', 'content': draft, 'step': 'hermes_draft'}, ensure_ascii=False)}\n\n"
                continue
            if (
                not defer_hermes_draft
                and hermes_draft_acc
                and evt.get("type") == "delta"
                and evt.get("content")
            ):
                hermes_draft_acc.push(str(evt["content"]))
            if defer_hermes_draft and evt.get("type") == "thinking" and evt.get("content"):
                yield f"data: {json.dumps({'type': 'thinking', 'content': str(evt['content']), 'step': 'hermes_reasoning'}, ensure_ascii=False)}\n\n"
                continue
            if evt.get("type") == "done":
                if hermes_draft_acc:
                    final_draft = hermes_draft_acc.flush()
                    if final_draft:
                        yield f"data: {json.dumps({'type': 'thinking', 'content': final_draft, 'step': 'hermes_draft'}, ensure_ascii=False)}\n\n"
                uq = last_user_query(messages)
                from backend.services.hermes_stream_sanitize import resolve_hermes_effective_reply

                hermes_raw_reply = resolve_hermes_effective_reply(
                    evt_reply=str(evt.get("reply") or ""),
                    draft_acc=hermes_draft_acc,
                )
                if hermes_raw_reply and len(hermes_raw_reply) > len(
                    str(evt.get("reply") or "").strip()
                ):
                    evt = {**evt, "reply": hermes_raw_reply}
                from backend.services.agent_kb_supplemental import (
                    apply_supplemental_to_done,
                    hermes_orientg_kb_ask_count,
                    iter_supplemental_revision_events,
                    needs_hermes_supplemental,
                )

                hermes_kb_ask_n = hermes_orientg_kb_ask_count(hermes_payload=evt)
                supplemental_ran = needs_hermes_supplemental(
                    agent_route=agent_route,
                    prefetch_result=prefetch_result,
                    hermes_kb_ask_count=hermes_kb_ask_n,
                    hermes_reply=hermes_raw_reply,
                    user_query=uq,
                )
                if supplemental_ran:
                    sup_meta: dict[str, Any] | None = None
                    for sup_evt in iter_supplemental_revision_events(
                        user_token=token,
                        tenant_id=tenant_id,
                        user_query=uq,
                        prefetch_result=prefetch_result or {},
                        prefetch_tool_calls=prefetch_tool_calls,
                        kb_scope=kb_scope_payload,
                        attached_doc_ids=attached,
                        fixtures=fixtures,
                        agent_route=agent_route,
                        enabled_skills=body.enabled_skills,
                        model=body.model,
                        hermes_reply=hermes_raw_reply,
                        run_id=run_id,
                    ):
                        if sup_evt.get("type") == "supplemental_meta":
                            sup_meta = sup_evt
                            continue
                        if sup_evt.get("type") == "error" and sup_evt.get("code") == "cancelled":
                            yield f"data: {json.dumps(sup_evt, ensure_ascii=False)}\n\n"
                            yield "data: [DONE]\n\n"
                            return
                        yield f"data: {json.dumps(sup_evt, ensure_ascii=False)}\n\n"
                    if sup_meta:
                        evt = apply_supplemental_to_done(
                            evt,
                            supplemental_meta=sup_meta,
                            prefetch_tool_calls=prefetch_tool_calls,
                        )
                        if prefetch_result is not None and sup_meta.get("prefetch_result"):
                            prefetch_result = sup_meta["prefetch_result"]

                from backend.services.hermes_stream_sanitize import finalize_agent_reply

                if evt.get("reply"):
                    evt = {
                        **evt,
                        "reply": finalize_agent_reply(
                            str(evt.get("reply") or ""),
                            user_query=uq,
                            tier2_native=(agent_route == AgentRoute.hermes_full),
                        ),
                    }

                final_body = str(evt.get("reply") or "").strip()
                if final_body and (defer_hermes_draft or supplemental_ran):
                    yield f"data: {json.dumps({'type': 'replace_reply', 'content': final_body}, ensure_ascii=False)}\n\n"

                evt = {
                    **evt,
                    "ok": True,
                    "tenant_id": tenant_id,
                    "kb_prefetch": bool(prefetch_tool_calls),
                    "kb_supplemental": supplemental_ran or bool(evt.get("kb_supplemental")),
                    "agent_route": agent_route.value,
                    "agent_tier": route_to_agent_tier(agent_route),
                    "evidence_pack": pack_summary_for_sse((prefetch_result or {}).get("evidence_pack")),
                    "tool_calls": [*prefetch_tool_calls, *(evt.get("tool_calls") or [])],
                }
            yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
    finally:
        unregister_agent_run(run_id)


@router.post("/cancel")
def agent_cancel(body: AgentCancelBody):
    """停止进行中的 Agent 流式任务（前端「停止」按钮）。"""
    rid = (body.run_id or "").strip()
    hermes_rid = pop_hermes_run_id(rid) if rid else None
    ok = cancel_agent_run(rid)
    hermes_stopping = False
    if hermes_rid and settings.hermes_configured:
        hermes_stopping = stop_hermes_run(hermes_rid)
    return {
        "ok": True,
        "cancelled": ok,
        "run_id": rid,
        "hermes_run_stopping": hermes_stopping,
    }


@router.post("/chat/stream")
def agent_chat_stream(request: Request, body: AgentChatBody):
    """Agent 流式回复（Hermes SSE 透传）。"""
    token = _get_token_from_request(request)
    if not token:
        raise HTTPException(status_code=401, detail="not authenticated")
    uname = _get_username_from_request(request)
    if not uname:
        raise HTTPException(status_code=401, detail="invalid token")

    messages = [{"role": m.role, "content": (m.content or "").strip()} for m in (body.messages or [])]
    if not any(m["role"] == "user" and m["content"] for m in messages):
        raise HTTPException(status_code=400, detail="empty user message")

    scope = body.kb_scope or KbScope()
    kb_scope_payload = {
        "selected_collection_ids": [str(x).strip() for x in (scope.selected_collection_ids or []) if str(x).strip()],
        "selected_table_ids": [str(x).strip() for x in (scope.selected_table_ids or []) if str(x).strip()],
        "selected_folder_ids": [str(x).strip() for x in (scope.selected_folder_ids or []) if str(x).strip()],
    }
    fixtures = load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    attached = [str(x).strip() for x in (body.attached_doc_ids or []) if str(x).strip()]

    if settings.hermes_dev_mock and not settings.hermes_configured:
        result = _dev_mock_agent_chat(
            user_token=token,
            messages=messages,
            kb_scope_payload=kb_scope_payload,
            attached_doc_ids=attached,
            hermes_session_id=body.hermes_session_id,
        )

        def mock_gen():
            reply = result.get("reply") or ""
            yield f"data: {json.dumps({'type': 'delta', 'content': reply}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'ok': True, 'reply': reply, 'hermes_session_id': result.get('hermes_session_id'), 'dev_mock': True, 'tool_calls': result.get('tool_calls') or []}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(mock_gen(), media_type="text/event-stream")

    prefetch_tool_calls: list[dict[str, Any]] = []
    prefetch_result: dict[str, Any] | None = None
    hermes_messages = messages
    user_query = last_user_query(messages)
    has_kb_scope = should_prefetch_kb(kb_scope_payload, attached_doc_ids=attached)
    _assert_agent_stream_client(request, has_kb_scope=has_kb_scope)

    if settings.hermes_agent_kb_prefetch and has_kb_scope:
        hermes_messages, prefetch_result, prefetch_tool_calls = prefetch_kb_context(
            token,
            messages,
            kb_scope_payload,
            attached_doc_ids=attached,
            agent_mode=(body.agent_mode or "standard"),
            enabled_skills=body.enabled_skills,
        )
        if prefetch_result and prefetch_result.get("denied"):
            raise HTTPException(status_code=403, detail=prefetch_result.get("reason") or "denied")

    agent_route, kb_ask_budget = _resolve_route_for_body(
        body=body,
        messages=messages,
        kb_scope_payload=kb_scope_payload,
        attached=attached,
        prefetch_result=prefetch_result,
    )
    if has_kb_scope and prefetch_result is not None:
        hermes_messages = patch_prefetch_system_message(
            hermes_messages,
            orientg_route=agent_route.value,
            evidence_pack=(prefetch_result or {}).get("evidence_pack"),
            agent_mode=(body.agent_mode or "standard"),
        )

    run_id = (request.headers.get("X-Agent-Run-Id") or "").strip() or None
    if run_id:
        register_agent_run(run_id)

    if agent_route == AgentRoute.fast and prefetch_result:

        def fast_gen():
            try:
                for evt in stream_kb_fast_path_events(
                    tenant_id=tenant_id,
                    user_query=user_query,
                    prefetch_result=prefetch_result or {},
                    prefetch_tool_calls=prefetch_tool_calls,
                    fixtures=fixtures,
                    enabled_skills=body.enabled_skills,
                    model=body.model,
                    hermes_session_id=body.hermes_session_id,
                    run_id=run_id,
                    user_token=token,
                    kb_scope=kb_scope_payload,
                    attached_doc_ids=attached,
                ):
                    yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
            finally:
                unregister_agent_run(run_id)

        return StreamingResponse(
            fast_gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    if not settings.hermes_configured:
        raise HTTPException(
            status_code=503,
            detail={"code": "hermes_disabled", "message": "流式智能体需要 Hermes", "hint": "见 docs/hermes.md"},
        )

    return StreamingResponse(
        _agent_chat_stream_events(
            token=token,
            uname=uname,
            tenant_id=tenant_id,
            messages=hermes_messages,
            kb_scope_payload=kb_scope_payload,
            attached=attached,
            body=body,
            prefetch_tool_calls=prefetch_tool_calls,
            prefetch_result=prefetch_result,
            fixtures=fixtures,
            run_id=run_id,
            agent_route=agent_route,
            kb_ask_budget=kb_ask_budget,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
