"""
Hermes Agent 内网 HTTP 客户端（方案 B）。

Hermes Gateway OpenAI 兼容 API（默认）：
  POST {HERMES_BASE_URL}/v1/chat/completions
  鉴权：Authorization: Bearer {HERMES_INTERNAL_TOKEN}  # 对应 API_SERVER_KEY
  默认端口：8642（API_SERVER_PORT）
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
import uuid
from collections.abc import Iterator
from typing import Any

import httpx

from backend.config import settings

logger = logging.getLogger(__name__)


def hermes_idle_stall_seconds(*, orientg_route: str | None, read_timeout: float) -> float:
    """MCP 工具回合可能长时间无 SSE；标准档须与页面矩阵 1200s 等待相容。"""
    route_key = (orientg_route or "").strip().lower()
    rt = float(read_timeout)
    if route_key == "hermes_full":
        return min(600.0, rt * 0.5)
    if route_key == "hermes_lite":
        return min(480.0, rt * 0.8)
    return min(120.0, rt * 0.2)


class HermesDisabledError(Exception):
    """HERMES_ENABLED=false 或未配置 base_url。"""


class HermesClientError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None, detail: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


def _hermes_api_root() -> str:
    base = (settings.hermes_base_url or "").rstrip("/")
    if base.endswith("/v1"):
        return base
    return f"{base}/v1"


def _chat_completions_url() -> str:
    return f"{_hermes_api_root()}/chat/completions"


def _capabilities_url() -> str:
    return f"{_hermes_api_root()}/capabilities"


def _runs_url() -> str:
    return f"{_hermes_api_root()}/runs"


def _build_messages(
    messages: list[dict[str, str]],
    *,
    username: str,
    kb_scope: dict[str, Any] | None,
    allow_kb_write: bool,
    attached_doc_ids: list[str] | None,
    hermes_session_id: str | None,
    orientg_hermes_session_key: str | None = None,
    orientg_route: str | None = None,
    orientg_kb_ask_budget: int | None = None,
    evidence_pack: dict[str, Any] | None = None,
    enabled_skills: list[str] | None = None,
) -> list[dict[str, str]]:
    """在 system 中注入 Orient-G 上下文（Hermes 侧 MCP 仍须在 ~/.hermes 配置 orientg）。"""
    ctx = {
        "orientg_username": username,
        "kb_scope": kb_scope or {},
        "allow_kb_write": bool(allow_kb_write),
        "attached_doc_ids": attached_doc_ids or [],
        "hermes_session_id": hermes_session_id,
        "orientg_hermes_session_key": orientg_hermes_session_key,
        "orientg_mcp_instruction": (
            "调用 orientg_kb_* 等 MCP 工具时，必须在参数 hermes_session_key 中传入 "
            "与本 JSON 字段 orientg_hermes_session_key 完全相同的值（不要省略）。"
        ),
        "hint": "知识库读写请使用已注册的 orientg MCP 工具（orientg_kb_*）。",
    }
    if orientg_route:
        ctx["orientg_route"] = orientg_route
    if orientg_route in ("hermes_lite", "hermes_full"):
        ctx["orientg_tool_policy"] = (
            "知识库类任务：仅通过 orientg_kb_* MCP 获取与引用证据；"
            "禁止用 terminal/shell/curl 探测 API 或读取本地路径；禁止编造文件内容充当 KB 答案。"
        )
    if orientg_route in ("hermes_lite", "hermes_full"):
        from backend.services.hermes_orientg_policy import KB_FORBIDDEN_TOOL_NAMES

        ctx["orientg_forbidden_tools"] = list(KB_FORBIDDEN_TOOL_NAMES)
        ctx["orientg_allowed_kb_tools"] = ["orientg_kb_ask", "orientg_kb_list", "orientg_kb_import_artifact"]
        if not allow_kb_write:
            ctx["orientg_kb_write"] = False
            ctx["orientg_allowed_kb_tools"] = ["orientg_kb_ask", "orientg_kb_list"]
    if orientg_kb_ask_budget is not None:
        ctx["orientg_kb_ask_budget"] = orientg_kb_ask_budget
    user_q = ""
    for m in reversed(messages or []):
        if m.get("role") == "user":
            user_q = str(m.get("content") or "").strip()
            break
    if user_q and orientg_route in ("hermes_lite", "hermes_full"):
        from backend.services.agent_hermes_tier_policy import (
            hermes_answer_requirements,
            hermes_orientg_context_extras,
            prefetch_tier_from_route,
        )

        tier = prefetch_tier_from_route(orientg_route)
        req = hermes_answer_requirements(tier=tier, user_query=user_q)
        if req:
            ctx["orientg_answer_requirements"] = req
        ctx.update(
            hermes_orientg_context_extras(
                tier=tier,
                evidence_pack=evidence_pack,
                user_query=user_q,
                enabled_skills=enabled_skills,
            )
        )
        ctx["orientg_stream_reasoning"] = bool(settings.hermes_stream_reasoning)
        if tier == "full":
            ctx["orientg_deep_orchestration"] = True
    system = {
        "role": "system",
        "content": "Orient-G 网关上下文（JSON）：\n" + json.dumps(ctx, ensure_ascii=False),
    }
    out: list[dict[str, str]] = [system]
    for m in messages or []:
        role = str(m.get("role") or "user")
        if role not in {"user", "assistant", "system"}:
            role = "user"
        out.append({"role": role, "content": str(m.get("content") or "")})
    return out


def _register_session(
    user_token: str,
    hermes_session_id: str | None,
    *,
    username: str | None = None,
    orientg_chat_session_id: str | None = None,
    orientg_kb_ask_budget: int | None = None,
    allow_kb_write: bool = False,
    kb_scope: dict[str, Any] | None = None,
    orientg_route: str | None = None,
) -> str:
    from backend.services.hermes_session_resolve import resolve_hermes_session_key
    from backend.services.hermes_session_context import register as register_session_context
    from backend.services.hermes_token_bridge import register as register_hermes_token
    from backend.services.kb_ask_budget import register_session_kb_budget

    session_key = resolve_hermes_session_key(
        username=username or "",
        hermes_session_id=hermes_session_id,
        orientg_chat_session_id=orientg_chat_session_id,
    )
    register_hermes_token(session_key, user_token)
    register_session_kb_budget(session_key, orientg_kb_ask_budget)
    register_session_context(
        session_key,
        allow_kb_write=allow_kb_write,
        kb_scope=kb_scope,
        orientg_route=orientg_route,
    )
    return session_key


def _apply_stream_content_policy(mapped: dict[str, Any], *, accumulated: list[str]) -> dict[str, Any] | None:
    """将 Hermes 误写入 content 的推理/脚本分流为 thinking，并维护仅用户可见的 accumulated。"""
    from backend.services.hermes_stream_sanitize import classify_hermes_stream_chunk

    if mapped.get("type") != "delta" or not mapped.get("content"):
        return mapped
    content = str(mapped["content"])
    kind = classify_hermes_stream_chunk(content)
    if kind == "skip":
        return None
    if kind == "thinking":
        return {"type": "thinking", "content": content}
    accumulated.append(content)
    return mapped


def _track_hermes_stream_chunk(
    mapped: dict[str, Any],
    remapped: dict[str, Any] | None,
    *,
    raw_parts: list[str],
    thinking_parts: list[str],
) -> None:
    """记录 SSE 原文，供终稿 sanitize 为空时从过程稿/原始 delta 恢复。"""
    if mapped.get("type") == "delta" and mapped.get("content"):
        raw_parts.append(str(mapped["content"]))
    elif mapped.get("type") == "thinking" and mapped.get("content"):
        thinking_parts.append(str(mapped["content"]))
    if (
        remapped
        and mapped.get("type") == "delta"
        and remapped.get("type") == "thinking"
        and remapped.get("content")
    ):
        thinking_parts.append(str(remapped["content"]))


def _finalize_hermes_chat_reply(
    *,
    accumulated_parts: list[str],
    raw_parts: list[str],
    thinking_parts: list[str],
    user_query: str,
) -> str:
    """Hermes chat/completions 终稿：优先 accumulated，其次 raw/thinking 中提取用户可见报告。"""
    from backend.services.hermes_stream_sanitize import (
        extract_user_facing_reply,
        sanitize_hermes_accumulated_reply,
        strip_hermes_orchestration_preamble,
    )

    candidates = (
        "".join(accumulated_parts),
        extract_user_facing_reply("".join(raw_parts)),
        extract_user_facing_reply("".join(thinking_parts)),
        strip_hermes_orchestration_preamble("".join(raw_parts)),
        strip_hermes_orchestration_preamble("".join(thinking_parts)),
    )
    seen: set[str] = set()
    for raw in candidates:
        blob = (raw or "").strip()
        if not blob or blob in seen:
            continue
        seen.add(blob)
        reply = sanitize_hermes_accumulated_reply(blob, user_query=user_query).strip()
        if reply:
            return reply
    return ""


def _request_headers(session_key: str) -> dict[str, str]:
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "X-Hermes-Session-Key": session_key,
    }
    api_key = (settings.hermes_internal_token or "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _build_payload(
    *,
    messages: list[dict[str, str]],
    username: str,
    kb_scope: dict[str, Any] | None,
    allow_kb_write: bool,
    attached_doc_ids: list[str] | None,
    hermes_session_id: str | None,
    session_key: str,
    stream: bool,
    orientg_route: str | None = None,
    orientg_kb_ask_budget: int | None = None,
    evidence_pack: dict[str, Any] | None = None,
    enabled_skills: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "model": (settings.hermes_model or "hermes-agent").strip() or "hermes-agent",
        "messages": _build_messages(
            messages,
            username=username,
            kb_scope=kb_scope,
            allow_kb_write=allow_kb_write,
            attached_doc_ids=attached_doc_ids,
            hermes_session_id=hermes_session_id,
            orientg_hermes_session_key=session_key,
            orientg_route=orientg_route,
            orientg_kb_ask_budget=orientg_kb_ask_budget,
            evidence_pack=evidence_pack,
            enabled_skills=enabled_skills,
        ),
        "stream": stream,
        # Hermes Gateway：显式开启 hermes.tool.progress SSE（见官方 API Server 文档）
        "stream_tool_progress": True if stream else False,
    }


def _last_user_query_from_messages(messages: list[dict[str, str]] | None) -> str:
    for m in reversed(messages or []):
        if str(m.get("role") or "") == "user":
            return str(m.get("content") or "").strip()
    return ""


def parse_openai_chat_response(
    data: dict[str, Any],
    *,
    session_key: str,
    user_query: str = "",
) -> dict[str, Any]:
    from backend.services.hermes_stream_sanitize import sanitize_hermes_accumulated_reply

    reply = ""
    tool_calls: list[Any] = []
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0] if isinstance(choices[0], dict) else {}
        msg = first.get("message") if isinstance(first.get("message"), dict) else {}
        reply = str(msg.get("content") or "")
        tc = msg.get("tool_calls")
        if isinstance(tc, list):
            tool_calls = tc

    return {
        "reply": sanitize_hermes_accumulated_reply(
            reply or data.get("reply") or data.get("content") or "",
            user_query=user_query,
        ),
        "tool_calls": tool_calls or data.get("tool_calls") or [],
        "hermes_session_id": data.get("hermes_session_id") or data.get("session_id") or session_key,
        "orientg_hermes_session_key": session_key,
        "artifacts": data.get("artifacts") or [],
        "raw": data,
    }


def parse_sse_data_line(line: str) -> dict[str, Any] | None:
    s = (line or "").strip()
    if not s.startswith("data:"):
        return None
    payload = s[5:].strip()
    if not payload or payload == "[DONE]":
        return None
    try:
        obj = json.loads(payload)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def iter_openai_stream_events(raw_line: bytes | str) -> Iterator[dict[str, str]]:
    """从 OpenAI 兼容 SSE 行解析 content delta / tool_call 片段。"""
    obj = parse_sse_data_line(raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line)
    if not obj:
        return
    choices = obj.get("choices")
    if not isinstance(choices, list) or not choices:
        return
    first = choices[0] if isinstance(choices[0], dict) else {}
    delta = first.get("delta") if isinstance(first.get("delta"), dict) else {}
    content = delta.get("content")
    if content:
        yield {"kind": "delta", "content": str(content)}
    reasoning = delta.get("reasoning_content") or delta.get("reasoning")
    if reasoning:
        yield {"kind": "thinking", "content": str(reasoning)}
    tool_calls = delta.get("tool_calls")
    if isinstance(tool_calls, list):
        for tc in tool_calls:
            if not isinstance(tc, dict):
                continue
            fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
            name = str(fn.get("name") or "").strip()
            if name:
                yield {"kind": "tool_call", "name": name}


def iter_openai_stream_deltas(raw_line: bytes | str) -> Iterator[str]:
    for ev in iter_openai_stream_events(raw_line):
        if ev.get("kind") == "delta" and ev.get("content"):
            yield ev["content"]


class HermesSseParser:
    """解析 Hermes Gateway SSE：`data:` OpenAI chunk + `event: hermes.tool.progress`。"""

    def __init__(self) -> None:
        self._pending_event: str | None = None

    def feed(self, line: bytes | str) -> list[dict[str, Any]]:
        s = (line.decode("utf-8") if isinstance(line, bytes) else line).strip()
        if not s or s.startswith(":"):
            return []
        if s.startswith("event:"):
            self._pending_event = s[6:].strip()
            return []
        if not s.startswith("data:"):
            return []
        payload = s[5:].strip()
        if not payload or payload == "[DONE]":
            self._pending_event = None
            return []
        event_type = self._pending_event
        self._pending_event = None
        return list(_parse_sse_data_payload(event_type, payload))


def _parse_sse_data_payload(event_type: str | None, payload: str) -> Iterator[dict[str, Any]]:
    if event_type == "hermes.tool.progress":
        try:
            obj = json.loads(payload)
        except json.JSONDecodeError:
            return
        if isinstance(obj, dict):
            yield {"kind": "tool_progress", **obj}
        return
    yield from iter_openai_stream_events(f"data: {payload}")


def _format_tool_progress_message(obj: dict[str, Any]) -> str:
    emoji = str(obj.get("emoji") or "").strip()
    label = str(obj.get("label") or obj.get("tool") or "工具").strip()
    if emoji and not label.startswith(emoji):
        return f"{emoji} {label}".strip()
    return label or emoji or "工具执行中"


def enrich_tool_progress_with_labels(
    events: list[dict[str, Any]],
    tool_label_by_id: dict[str, str],
) -> list[dict[str, Any]]:
    """completed 的 tool_progress 常无 label，用 running 阶段缓存的命令预览。"""
    out: list[dict[str, Any]] = []
    for m in events:
        if m.get("type") != "tool_progress":
            out.append(m)
            continue
        tid = str(m.get("tool_call_id") or "").strip()
        status = str(m.get("status") or "")
        tool = str(m.get("tool") or "").strip()
        msg = str(m.get("message") or "").strip()
        if status == "running" and tid and msg:
            tool_label_by_id[tid] = msg
            out.append(m)
            continue
        if status == "completed" and tid:
            prev = tool_label_by_id.get(tid, "").strip()
            if prev and (not msg or msg == tool):
                m = {**m, "message": prev}
            out.append(m)
            continue
        out.append(m)
    return out


def guard_kb_forbidden_tool_sse(
    mapped: dict[str, Any],
    *,
    orientg_route: str | None,
    on_block: Any | None = None,
) -> dict[str, Any] | None:
    """KB 路由执行层：拦截 terminal/shell/loopback 工具步。"""
    from backend.services.hermes_orientg_policy import (
        is_forbidden_kb_tool,
        orientg_route_is_kb_task,
        tool_progress_looks_like_shell,
    )

    if not orientg_route_is_kb_task(orientg_route):
        return None
    if mapped.get("type") != "tool_progress" or mapped.get("status") != "running":
        return None
    tool = str(mapped.get("tool") or "")
    msg = str(mapped.get("message") or mapped.get("label") or "")
    if not is_forbidden_kb_tool(tool) and not tool_progress_looks_like_shell(msg):
        return None
    if on_block:
        try:
            on_block()
        except Exception:
            logger.debug("forbidden tool on_block failed", exc_info=True)
    return {
        "type": "tool_progress",
        "tool": tool or "forbidden",
        "status": "failed",
        "message": "KB 任务禁止 terminal/shell/loopback/execute_code；请使用 orientg_kb_* MCP 取证与写库。",
    }


def hermes_internal_event_to_sse(ev: dict[str, Any], *, seen_tool_ids: set[str]) -> list[dict[str, Any]]:
    """将 HermesSseParser 产出的事件转为 Orient-G Agent SSE dict。"""
    out: list[dict[str, Any]] = []
    kind = ev.get("kind")
    if kind == "delta" and ev.get("content"):
        out.append({"type": "delta", "content": ev["content"]})
    elif kind == "thinking" and ev.get("content"):
        out.append({"type": "thinking", "content": ev["content"]})
    elif kind == "tool_progress":
        tool_call_id = str(ev.get("toolCallId") or ev.get("tool_call_id") or "").strip()
        status = str(ev.get("status") or "running").strip()
        message = _format_tool_progress_message(ev)
        if tool_call_id:
            seen_tool_ids.add(tool_call_id)
        out.append(
            {
                "type": "tool_progress",
                "tool": ev.get("tool"),
                "emoji": ev.get("emoji"),
                "label": ev.get("label"),
                "tool_call_id": tool_call_id or None,
                "status": status,
                "message": message,
            }
        )
    elif kind == "tool_call" and ev.get("name"):
        name = str(ev["name"])
        if name not in seen_tool_ids:
            seen_tool_ids.add(name)
            out.append(
                {
                    "type": "tool_call",
                    "name": name,
                    "status": "running",
                    "message": f"调用工具 {name}",
                }
            )
    return out


def sse_events_from_hermes_line(
    parser: HermesSseParser,
    line: bytes | str,
    *,
    seen_tool_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """单行 feed + 映射（供单测）。"""
    seen = seen_tool_ids if seen_tool_ids is not None else set()
    out: list[dict[str, Any]] = []
    for ev in parser.feed(line):
        out.extend(hermes_internal_event_to_sse(ev, seen_tool_ids=seen))
    return out


_capabilities_cache: dict[str, Any] | None = None
_capabilities_cache_at: float = 0.0
_CAPABILITIES_TTL_S = 120.0


def invalidate_hermes_capabilities_cache() -> None:
    global _capabilities_cache, _capabilities_cache_at
    _capabilities_cache = None
    _capabilities_cache_at = 0.0


def parse_hermes_capabilities(raw: dict[str, Any]) -> dict[str, Any]:
    features = raw.get("features") if isinstance(raw.get("features"), dict) else {}
    return {
        "chat_completions_streaming": bool(features.get("chat_completions_streaming")),
        "run_events_sse": bool(features.get("run_events_sse")),
        "run_stop": bool(features.get("run_stop")),
        "run_submission": bool(features.get("run_submission")),
        "tool_progress_events": bool(features.get("tool_progress_events")),
        "raw": raw,
    }


def hermes_capabilities_support_runs(caps: dict[str, Any]) -> bool:
    return bool(
        caps.get("run_events_sse")
        and caps.get("run_stop")
        and caps.get("run_submission")
    )


def _prefer_hermes_runs_api(orientg_route: str | None) -> bool:
    """深度 Tier 2 在 Gateway 支持时优先 Runs API（多轮工具 + 事件流）。"""
    if settings.hermes_agent_use_runs_api:
        return True
    if (orientg_route or "").strip().lower() == "hermes_full":
        caps = fetch_hermes_capabilities()
        return hermes_capabilities_support_runs(caps)
    return False


def _empty_stream_stats() -> dict[str, Any]:
    return {
        "thinking_chars": 0,
        "delta_chars": 0,
        "tool_progress_events": 0,
        "tool_call_events": 0,
        "orientg_kb_ask_calls": 0,
    }


def _record_stream_tool(
    tools: list[dict[str, Any]],
    *,
    name: str,
    status: str = "ok",
    message: str = "",
) -> None:
    n = (name or "").strip()
    if not n:
        return
    for t in tools:
        if str(t.get("name") or "") == n and t.get("status") == status:
            return
    tools.append({"name": n, "status": status, "message": message[:200] if message else ""})


def _bump_stream_stats(stats: dict[str, Any], mapped: dict[str, Any], tools: list[dict[str, Any]]) -> None:
    t = mapped.get("type")
    if t == "thinking" and mapped.get("content"):
        stats["thinking_chars"] = int(stats.get("thinking_chars") or 0) + len(str(mapped["content"]))
    elif t == "delta" and mapped.get("content"):
        stats["delta_chars"] = int(stats.get("delta_chars") or 0) + len(str(mapped["content"]))
    elif t == "tool_progress":
        stats["tool_progress_events"] = int(stats.get("tool_progress_events") or 0) + 1
        tool = str(mapped.get("tool") or "")
        msg = str(mapped.get("message") or "")
        if "orientg_kb_ask" in tool or "orientg_kb_ask" in msg or "kb_ask" in tool.lower():
            stats["orientg_kb_ask_calls"] = int(stats.get("orientg_kb_ask_calls") or 0) + 1
        _record_stream_tool(tools, name=tool or msg[:40], status=str(mapped.get("status") or "running"), message=msg)
    elif t == "tool_call" and mapped.get("name"):
        stats["tool_call_events"] = int(stats.get("tool_call_events") or 0) + 1
        name = str(mapped["name"])
        if "orientg_kb" in name:
            stats["orientg_kb_ask_calls"] = int(stats.get("orientg_kb_ask_calls") or 0) + 1
        _record_stream_tool(tools, name=name, status="running", message=str(mapped.get("message") or ""))


def fetch_hermes_capabilities(*, force: bool = False) -> dict[str, Any]:
    """GET /v1/capabilities（带内存缓存）。"""
    global _capabilities_cache, _capabilities_cache_at
    if not settings.hermes_configured:
        return {}
    now = time.monotonic()
    if (
        not force
        and _capabilities_cache is not None
        and now - _capabilities_cache_at < _CAPABILITIES_TTL_S
    ):
        return _capabilities_cache
    url = _capabilities_url()
    headers: dict[str, str] = {}
    token = (settings.hermes_internal_token or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url, headers=headers)
        if resp.status_code >= 400:
            logger.warning("Hermes capabilities HTTP %s", resp.status_code)
            return _capabilities_cache or {}
        data = resp.json()
        if not isinstance(data, dict):
            return _capabilities_cache or {}
        parsed = parse_hermes_capabilities(data)
        _capabilities_cache = parsed
        _capabilities_cache_at = now
        return parsed
    except Exception as e:
        logger.warning("Hermes capabilities fetch failed: %s", e)
        return _capabilities_cache or {}


def messages_to_hermes_runs_body(
    messages: list[dict[str, str]],
    *,
    model: str,
    session_id: str,
) -> dict[str, Any]:
    """将 Orient-G messages 转为 POST /v1/runs 请求体。"""
    system_lines: list[str] = []
    dialog: list[dict[str, str]] = []
    for m in messages or []:
        role = str(m.get("role") or "user")
        content = str(m.get("content") or "")
        if role == "system":
            system_lines.append(content)
        elif role in {"user", "assistant"}:
            dialog.append({"role": role, "content": content})
    user_message = ""
    history: list[dict[str, str]] = []
    for i, m in enumerate(dialog):
        if m["role"] == "user":
            user_message = m["content"]
            history = dialog[:i]
    if not user_message and dialog:
        last = dialog[-1]
        user_message = last["content"]
        history = dialog[:-1]
    body: dict[str, Any] = {
        "model": model,
        "input": user_message,
        "session_id": session_id,
    }
    if system_lines:
        body["instructions"] = "\n\n".join(system_lines)
    if history:
        body["conversation_history"] = history
    return body


def _hermes_run_tool_key(run_id: str, tool: str) -> str:
    return f"{run_id}:{tool}"


def hermes_run_event_to_sse(
    obj: dict[str, Any],
    *,
    seen_tool_keys: set[str],
) -> list[dict[str, Any]]:
    """Hermes Runs API SSE JSON → Orient-G Agent SSE。"""
    ev = str(obj.get("event") or "")
    run_id = str(obj.get("run_id") or "")
    out: list[dict[str, Any]] = []
    if ev == "message.delta":
        delta = obj.get("delta")
        if delta:
            out.append({"type": "delta", "content": str(delta)})
    elif ev == "reasoning.available":
        text = str(obj.get("text") or obj.get("preview") or "")
        if text:
            out.append({"type": "thinking", "content": text})
    elif ev == "reasoning.delta":
        delta = str(obj.get("delta") or obj.get("text") or "")
        if delta:
            out.append({"type": "thinking", "content": delta})
    elif ev == "tool.started":
        tool = str(obj.get("tool") or "tool")
        key = _hermes_run_tool_key(run_id, tool)
        seen_tool_keys.add(key)
        preview = str(obj.get("preview") or tool)
        out.append(
            {
                "type": "tool_progress",
                "tool": tool,
                "tool_call_id": key,
                "status": "running",
                "message": preview,
            }
        )
    elif ev == "tool.completed":
        tool = str(obj.get("tool") or "tool")
        key = _hermes_run_tool_key(run_id, tool)
        if key not in seen_tool_keys:
            return []
        preview = str(obj.get("preview") or "").strip()
        out.append(
            {
                "type": "tool_progress",
                "tool": tool,
                "tool_call_id": key,
                "status": "completed",
                "label": preview or None,
                "message": preview or tool,
            }
        )
    elif ev == "run.completed":
        output = str(obj.get("output") or "")
        out.append({"type": "run_completed", "output": output, "hermes_run_id": run_id})
    elif ev == "run.failed":
        out.append(
            {
                "type": "error",
                "message": str(obj.get("error") or "Hermes run 失败"),
                "code": "hermes_run_failed",
            }
        )
    return out


def create_hermes_run(
    *,
    body: dict[str, Any],
    session_key: str,
) -> str:
    """POST /v1/runs，返回 run_id。"""
    headers = _request_headers(session_key)
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(_runs_url(), json=body, headers=headers)
    if resp.status_code >= 400:
        raise HermesClientError(
            f"Hermes runs HTTP {resp.status_code}",
            status_code=resp.status_code,
            detail=resp.text[:500],
        )
    data = resp.json()
    if not isinstance(data, dict):
        raise HermesClientError("Hermes runs 响应无效", detail=data)
    run_id = str(data.get("run_id") or "").strip()
    if not run_id:
        raise HermesClientError("Hermes runs 未返回 run_id", detail=data)
    return run_id


def stop_hermes_run(hermes_run_id: str) -> bool:
    """POST /v1/runs/{id}/stop。"""
    hid = (hermes_run_id or "").strip()
    if not hid or not settings.hermes_configured:
        return False
    url = f"{_runs_url()}/{hid}/stop"
    headers: dict[str, str] = {}
    token = (settings.hermes_internal_token or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, headers=headers, json={})
        return resp.status_code < 400
    except Exception as e:
        logger.warning("Hermes stop run %s failed: %s", hid, e)
        return False


def _parse_hermes_run_sse_data_line(line: bytes | str) -> dict[str, Any] | None:
    s = (line.decode("utf-8") if isinstance(line, bytes) else line).strip()
    if not s.startswith("data:"):
        return None
    payload = s[5:].strip()
    if not payload:
        return None
    try:
        obj = json.loads(payload)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def run_agent_chat(
    *,
    messages: list[dict[str, str]],
    username: str,
    user_token: str,
    kb_scope: dict[str, Any] | None = None,
    allow_kb_write: bool = True,
    hermes_session_id: str | None = None,
    orientg_chat_session_id: str | None = None,
    attached_doc_ids: list[str] | None = None,
    orientg_route: str | None = None,
    orientg_kb_ask_budget: int | None = None,
    evidence_pack: dict[str, Any] | None = None,
    enabled_skills: list[str] | None = None,
) -> dict[str, Any]:
    if not settings.hermes_configured:
        raise HermesDisabledError("Hermes Agent 未启用（HERMES_ENABLED / HERMES_BASE_URL）")

    session_key = _register_session(
        user_token,
        hermes_session_id,
        username=username,
        orientg_chat_session_id=orientg_chat_session_id,
        orientg_kb_ask_budget=orientg_kb_ask_budget,
        allow_kb_write=allow_kb_write,
        kb_scope=kb_scope,
        orientg_route=orientg_route,
    )
    url = _chat_completions_url()
    headers = _request_headers(session_key)
    payload = _build_payload(
        messages=messages,
        username=username,
        kb_scope=kb_scope,
        allow_kb_write=allow_kb_write,
        attached_doc_ids=attached_doc_ids,
        hermes_session_id=hermes_session_id,
        session_key=session_key,
        stream=False,
        orientg_route=orientg_route,
        orientg_kb_ask_budget=orientg_kb_ask_budget,
        evidence_pack=evidence_pack,
        enabled_skills=enabled_skills,
    )

    timeout = max(30, int(settings.hermes_request_timeout_s or 300))
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, json=payload, headers=headers)
    except httpx.TimeoutException as e:
        raise HermesClientError("Hermes 请求超时", detail=str(e)) from e
    except httpx.RequestError as e:
        raise HermesClientError("无法连接 Hermes Agent", detail=str(e)) from e

    if resp.status_code >= 400:
        detail: Any
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text[:500]
        raise HermesClientError(
            f"Hermes 返回错误 HTTP {resp.status_code}",
            status_code=resp.status_code,
            detail=detail,
        )

    try:
        data = resp.json()
    except Exception as e:
        raise HermesClientError("Hermes 响应非 JSON", detail=resp.text[:500]) from e

    if not isinstance(data, dict):
        raise HermesClientError("Hermes 响应格式无效", detail=data)

    return parse_openai_chat_response(data, session_key=session_key, user_query=_last_user_query_from_messages(messages))


def stream_agent_chat_runs(
    *,
    messages: list[dict[str, str]],
    username: str,
    user_token: str,
    kb_scope: dict[str, Any] | None = None,
    allow_kb_write: bool = True,
    hermes_session_id: str | None = None,
    orientg_chat_session_id: str | None = None,
    attached_doc_ids: list[str] | None = None,
    run_id: str | None = None,
    heartbeat_s: float = 12.0,
    orientg_route: str | None = None,
    orientg_kb_ask_budget: int | None = None,
    evidence_pack: dict[str, Any] | None = None,
    enabled_skills: list[str] | None = None,
) -> Iterator[dict[str, Any]]:
    """经 POST /v1/runs + GET .../events 流式（路线第三步）。"""
    from backend.services.agent_run_registry import bind_hermes_run, is_cancelled

    if not settings.hermes_configured:
        yield {"type": "error", "message": "Hermes Agent 未启用"}
        return

    yield {"type": "status", "message": "正在连接 Hermes Agent（Runs API）…", "step": "connect"}

    session_key = _register_session(
        user_token,
        hermes_session_id,
        username=username,
        orientg_chat_session_id=orientg_chat_session_id,
        orientg_kb_ask_budget=orientg_kb_ask_budget,
        allow_kb_write=allow_kb_write,
        kb_scope=kb_scope,
        orientg_route=orientg_route,
    )
    built = _build_messages(
        messages,
        username=username,
        kb_scope=kb_scope,
        allow_kb_write=allow_kb_write,
        attached_doc_ids=attached_doc_ids,
        hermes_session_id=hermes_session_id,
        orientg_hermes_session_key=session_key,
        orientg_route=orientg_route,
        orientg_kb_ask_budget=orientg_kb_ask_budget,
        evidence_pack=evidence_pack,
        enabled_skills=enabled_skills,
    )
    model = (settings.hermes_model or "hermes-agent").strip() or "hermes-agent"
    runs_body = messages_to_hermes_runs_body(built, model=model, session_id=session_key)
    from backend.services.hermes_orientg_policy import kb_route_allowed_toolsets

    allowed_toolsets = kb_route_allowed_toolsets(orientg_route)
    if allowed_toolsets:
        runs_body["toolsets"] = allowed_toolsets

    from backend.services.hermes_runs_loop_guard import HermesRunsLoopGuard, runs_read_timeout_s

    read_timeout = runs_read_timeout_s(
        orientg_route=orientg_route,
        configured=int(settings.hermes_request_timeout_s or 600),
    )
    timeout = httpx.Timeout(30.0, read=float(read_timeout))
    idle_stall_s = hermes_idle_stall_seconds(
        orientg_route=orientg_route,
        read_timeout=float(read_timeout),
    )
    loop_guard = HermesRunsLoopGuard(orientg_route=orientg_route)
    abort_runs = False
    accumulated_parts: list[str] = []
    final_output = ""
    seen_tool_keys: set[str] = set()
    tool_label_by_id: dict[str, str] = {}
    stream_stats = _empty_stream_stats()
    stream_tools: list[dict[str, Any]] = []
    q: queue.Queue[tuple[str, Any]] = queue.Queue()
    stop_reader = threading.Event()
    reader_done = threading.Event()
    last_data_at = time.monotonic()
    connected = False
    hermes_run_id = ""

    def _reader() -> None:
        nonlocal hermes_run_id
        try:
            hermes_run_id = create_hermes_run(body=runs_body, session_key=session_key)
            if run_id:
                bind_hermes_run(run_id, hermes_run_id)
            events_url = f"{_runs_url()}/{hermes_run_id}/events"
            headers = _request_headers(session_key)
            with httpx.Client(timeout=timeout) as client:
                with client.stream("GET", events_url, headers=headers) as resp:
                    if resp.status_code >= 400:
                        detail = resp.read().decode("utf-8", errors="replace")[:500]
                        q.put(("err", {"message": f"Hermes runs events HTTP {resp.status_code}", "detail": detail}))
                        return
                    q.put(("status", "Hermes Runs 已连接，编排中…"))
                    for line in resp.iter_lines():
                        if stop_reader.is_set():
                            if hermes_run_id:
                                stop_hermes_run(hermes_run_id)
                            return
                        if line:
                            q.put(("line", line))
        except HermesClientError as e:
            q.put(("err", {"message": str(e), "detail": e.detail}))
        except httpx.TimeoutException:
            q.put(("err", {"message": "Hermes Runs 请求超时"}))
        except httpx.RequestError as e:
            q.put(("err", {"message": f"无法连接 Hermes Runs: {e}"}))
        finally:
            reader_done.set()
            q.put(("end", None))

    def _dispatch(kind: str, payload: Any) -> list[dict[str, Any]]:
        nonlocal final_output, last_beat, last_data_at, connected
        out: list[dict[str, Any]] = []
        if kind == "status":
            connected = True
            out.append({"type": "status", "message": str(payload), "step": "hermes_runs"})
            last_beat = time.monotonic()
            return out
        if kind == "err":
            err = payload if isinstance(payload, dict) else {"message": str(payload)}
            out.append({"type": "error", **err})
            return out
        if kind == "line":
            last_data_at = time.monotonic()
            obj = _parse_hermes_run_sse_data_line(payload)
            if not obj:
                return out
            mapped_batch = hermes_run_event_to_sse(obj, seen_tool_keys=seen_tool_keys)
            mapped_batch = enrich_tool_progress_with_labels(mapped_batch, tool_label_by_id)
            for mapped in mapped_batch:
                if mapped.get("type") == "run_completed":
                    final_output = str(mapped.get("output") or "")
                    continue
                remapped = _apply_stream_content_policy(mapped, accumulated=accumulated_parts)
                if remapped is None:
                    continue
                blocked = guard_kb_forbidden_tool_sse(
                    remapped,
                    orientg_route=orientg_route,
                    on_block=loop_guard.on_forbidden_block,
                )
                if blocked:
                    out.append(blocked)
                    loop_guard.on_stream_evt(blocked)
                    continue
                _bump_stream_stats(stream_stats, remapped, stream_tools)
                loop_guard.on_stream_evt(remapped)
                out.append(remapped)
                last_beat = time.monotonic()
        return out

    threading.Thread(target=_reader, daemon=True).start()
    last_beat = time.monotonic()
    try:
        while True:
            if is_cancelled(run_id):
                stop_reader.set()
                if hermes_run_id:
                    stop_hermes_run(hermes_run_id)
                yield {"type": "error", "message": "已停止", "code": "cancelled"}
                return
            try:
                kind, payload = q.get(timeout=1.0)
            except queue.Empty:
                if reader_done.is_set():
                    while True:
                        try:
                            kind2, payload2 = q.get_nowait()
                        except queue.Empty:
                            break
                        if kind2 == "end":
                            continue
                        for evt in _dispatch(kind2, payload2):
                            if evt.get("type") == "error":
                                yield evt
                                return
                            yield evt
                    break
                if connected and time.monotonic() - last_data_at >= idle_stall_s:
                    stop_reader.set()
                    if hermes_run_id:
                        stop_hermes_run(hermes_run_id)
                    yield {
                        "type": "error",
                        "message": f"Hermes Runs 已超过 {int(idle_stall_s)} 秒无数据。",
                        "code": "hermes_stall",
                    }
                    return
                if time.monotonic() - last_beat >= heartbeat_s:
                    last_beat = time.monotonic()
                    yield {
                        "type": "status",
                        "message": "Hermes 仍在执行（MCP 工具 / 推理），请稍候…",
                        "step": "heartbeat",
                    }
                continue
            if kind == "end":
                break
            for evt in _dispatch(kind, payload):
                if evt.get("type") == "error":
                    yield evt
                    return
                if evt.get("type") == "run_completed":
                    continue
                yield evt
                if not abort_runs:
                    should_abort, code, msg = loop_guard.should_abort()
                    if should_abort:
                        abort_runs = True
                        stop_reader.set()
                        if hermes_run_id:
                            stop_hermes_run(hermes_run_id)
                        yield {
                            "type": "status",
                            "message": msg,
                            "step": "hermes_run_abort",
                            "code": code,
                        }
                        break
            if abort_runs:
                break
    finally:
        stop_reader.set()

    uq = _last_user_query_from_messages(messages)
    from backend.services.hermes_stream_sanitize import pick_best_hermes_runs_raw

    raw = pick_best_hermes_runs_raw("".join(accumulated_parts), final_output)
    from backend.services.hermes_stream_sanitize import sanitize_hermes_accumulated_reply

    reply = sanitize_hermes_accumulated_reply(raw, user_query=uq).strip()
    if not reply:
        yield {
            "type": "error",
            "message": "Hermes Runs 已完成，但未生成可展示的正文。",
            "code": "hermes_empty",
        }
        return

    yield {
        "type": "done",
        "reply": reply,
        "hermes_session_id": session_key,
        "orientg_hermes_session_key": session_key,
        "hermes_run_id": hermes_run_id,
        "tool_calls": stream_tools,
        "artifacts": [],
        "hermes_used": True,
        "synthesis": "hermes_stream_runs",
        "hermes_stream_mode": "runs",
        "hermes_stream_stats": stream_stats,
    }


def stream_agent_chat(
    *,
    messages: list[dict[str, str]],
    username: str,
    user_token: str,
    kb_scope: dict[str, Any] | None = None,
    allow_kb_write: bool = True,
    hermes_session_id: str | None = None,
    orientg_chat_session_id: str | None = None,
    attached_doc_ids: list[str] | None = None,
    run_id: str | None = None,
    heartbeat_s: float = 12.0,
    orientg_route: str | None = None,
    orientg_kb_ask_budget: int | None = None,
    evidence_pack: dict[str, Any] | None = None,
    enabled_skills: list[str] | None = None,
) -> Iterator[dict[str, Any]]:
    """
    产出 SSE 事件 dict：
      {"type":"delta","content":"..."}
      {"type":"done","reply":"...","hermes_session_id":"...","tool_calls":[...]}
      {"type":"error","message":"..."}
    """
    from backend.services.agent_run_registry import is_cancelled

    if not settings.hermes_configured:
        yield {"type": "error", "message": "Hermes Agent 未启用"}
        return

    if _prefer_hermes_runs_api(orientg_route):
        caps = fetch_hermes_capabilities()
        if hermes_capabilities_support_runs(caps):
            if (orientg_route or "").strip().lower() == "hermes_full":
                yield {
                    "type": "status",
                    "message": "深度编排：Hermes Runs API（多轮工具与事件流）…",
                    "step": "hermes_runs_mode",
                }
            yield from stream_agent_chat_runs(
                messages=messages,
                username=username,
                user_token=user_token,
                kb_scope=kb_scope,
                allow_kb_write=allow_kb_write,
                hermes_session_id=hermes_session_id,
                orientg_chat_session_id=orientg_chat_session_id,
                attached_doc_ids=attached_doc_ids,
                run_id=run_id,
                heartbeat_s=heartbeat_s,
                orientg_route=orientg_route,
                orientg_kb_ask_budget=orientg_kb_ask_budget,
                evidence_pack=evidence_pack,
                enabled_skills=enabled_skills,
            )
            return
        if (orientg_route or "").strip().lower() == "hermes_full":
            yield {
                "type": "status",
                "message": "Gateway 未启用 Runs API，回退 chat/completions（工具步可能不可见）",
                "step": "hermes_mode_fallback",
            }

    yield {"type": "status", "message": "正在连接 Hermes Agent…", "step": "connect"}

    session_key = _register_session(
        user_token,
        hermes_session_id,
        username=username,
        orientg_chat_session_id=orientg_chat_session_id,
        orientg_kb_ask_budget=orientg_kb_ask_budget,
        allow_kb_write=allow_kb_write,
        kb_scope=kb_scope,
        orientg_route=orientg_route,
    )
    url = _chat_completions_url()
    headers = _request_headers(session_key)
    payload = _build_payload(
        messages=messages,
        username=username,
        kb_scope=kb_scope,
        allow_kb_write=allow_kb_write,
        attached_doc_ids=attached_doc_ids,
        hermes_session_id=hermes_session_id,
        session_key=session_key,
        stream=True,
        orientg_route=orientg_route,
        orientg_kb_ask_budget=orientg_kb_ask_budget,
        evidence_pack=evidence_pack,
        enabled_skills=enabled_skills,
    )

    read_timeout = max(60, int(settings.hermes_request_timeout_s or 600))
    timeout = httpx.Timeout(30.0, read=float(read_timeout))
    accumulated_parts: list[str] = []
    raw_stream_parts: list[str] = []
    thinking_stream_parts: list[str] = []
    seen_tool_ids: set[str] = set()
    tool_label_by_id: dict[str, str] = {}
    stream_stats = _empty_stream_stats()
    stream_tools: list[dict[str, Any]] = []
    sse_parser = HermesSseParser()
    q: queue.Queue[tuple[str, Any]] = queue.Queue()
    stop_reader = threading.Event()
    reader_done = threading.Event()
    last_data_at = time.monotonic()
    idle_stall_s = hermes_idle_stall_seconds(
        orientg_route=orientg_route,
        read_timeout=float(read_timeout),
    )
    connected = False
    from backend.services.hermes_runs_loop_guard import HermesRunsLoopGuard

    loop_guard = HermesRunsLoopGuard(orientg_route=orientg_route)
    abort_chat = False

    def _reader() -> None:
        try:
            with httpx.Client(timeout=timeout) as client:
                with client.stream("POST", url, json=payload, headers=headers) as resp:
                    if resp.status_code >= 400:
                        detail = resp.read().decode("utf-8", errors="replace")[:500]
                        q.put(("err", {"message": f"Hermes HTTP {resp.status_code}", "detail": detail}))
                        return
                    q.put(("status", "Hermes 已连接，编排中…"))
                    for line in resp.iter_lines():
                        if stop_reader.is_set():
                            return
                        if line:
                            q.put(("line", line))
        except httpx.TimeoutException:
            q.put(("err", {"message": "Hermes 请求超时"}))
        except httpx.RequestError as e:
            q.put(("err", {"message": f"无法连接 Hermes: {e}"}))
        finally:
            reader_done.set()
            q.put(("end", None))

    def _dispatch(kind: str, payload: Any) -> list[dict[str, Any]]:
        nonlocal last_beat, last_data_at, connected
        out: list[dict[str, Any]] = []
        if kind == "status":
            connected = True
            out.append({"type": "status", "message": str(payload), "step": "hermes"})
            last_beat = time.monotonic()
            return out
        if kind == "err":
            err = payload if isinstance(payload, dict) else {"message": str(payload)}
            out.append({"type": "error", **err})
            return out
        if kind == "line":
            last_data_at = time.monotonic()
            for ev in sse_parser.feed(payload):
                batch = hermes_internal_event_to_sse(ev, seen_tool_ids=seen_tool_ids)
                batch = enrich_tool_progress_with_labels(batch, tool_label_by_id)
                for mapped in batch:
                    remapped = _apply_stream_content_policy(mapped, accumulated=accumulated_parts)
                    _track_hermes_stream_chunk(
                        mapped,
                        remapped,
                        raw_parts=raw_stream_parts,
                        thinking_parts=thinking_stream_parts,
                    )
                    if remapped is None:
                        continue
                    blocked = guard_kb_forbidden_tool_sse(
                        remapped,
                        orientg_route=orientg_route,
                        on_block=loop_guard.on_forbidden_block,
                    )
                    if blocked:
                        out.append(blocked)
                        loop_guard.on_stream_evt(blocked)
                        continue
                    _bump_stream_stats(stream_stats, remapped, stream_tools)
                    loop_guard.on_stream_evt(remapped)
                    out.append(remapped)
                    last_beat = time.monotonic()
        return out

    def _stream_reply() -> str:
        return _finalize_hermes_chat_reply(
            accumulated_parts=accumulated_parts,
            raw_parts=raw_stream_parts,
            thinking_parts=thinking_stream_parts,
            user_query=_last_user_query_from_messages(messages),
        )

    threading.Thread(target=_reader, daemon=True).start()
    last_beat = time.monotonic()
    try:
        while True:
            if is_cancelled(run_id):
                stop_reader.set()
                yield {"type": "error", "message": "已停止", "code": "cancelled"}
                return
            try:
                kind, payload = q.get(timeout=1.0)
            except queue.Empty:
                if reader_done.is_set():
                    while True:
                        try:
                            kind2, payload2 = q.get_nowait()
                        except queue.Empty:
                            break
                        if kind2 == "end":
                            continue
                        for evt in _dispatch(kind2, payload2):
                            if evt.get("type") == "error":
                                yield evt
                                return
                            yield evt
                            if not abort_chat:
                                should_abort, code, msg = loop_guard.should_abort()
                                if should_abort:
                                    abort_chat = True
                                    stop_reader.set()
                                    yield {"type": "error", "message": msg, "code": code}
                                    return
                    if not _stream_reply():
                        yield {
                            "type": "error",
                            "message": (
                                "Hermes 连接已结束，但未返回正文。"
                                "请检查 Hermes Gateway / 本地 LLM 是否仍在运行，然后重试。"
                            ),
                            "code": "hermes_empty",
                        }
                        return
                    break
                if connected and time.monotonic() - last_data_at >= idle_stall_s:
                    stop_reader.set()
                    yield {
                        "type": "error",
                        "message": (
                            f"Hermes 已超过 {int(idle_stall_s)} 秒无数据（可能 LLM/Gateway 已停止）。"
                            "请检查进程后重试。"
                        ),
                        "code": "hermes_stall",
                    }
                    return
                if time.monotonic() - last_beat >= heartbeat_s:
                    last_beat = time.monotonic()
                    yield {
                        "type": "status",
                        "message": "Hermes 仍在执行（MCP 工具 / 推理），请稍候…",
                        "step": "heartbeat",
                    }
                continue
            if kind == "end":
                break
            for evt in _dispatch(kind, payload):
                if evt.get("type") == "error":
                    yield evt
                    return
                yield evt
                if not abort_chat:
                    should_abort, code, msg = loop_guard.should_abort()
                    if should_abort:
                        abort_chat = True
                        stop_reader.set()
                        yield {"type": "error", "message": msg, "code": code}
                        return
    finally:
        stop_reader.set()

    uq = _last_user_query_from_messages(messages)
    reply = _finalize_hermes_chat_reply(
        accumulated_parts=accumulated_parts,
        raw_parts=raw_stream_parts,
        thinking_parts=thinking_stream_parts,
        user_query=uq,
    )
    if not reply:
        yield {
            "type": "error",
            "message": "Hermes 已完成编排，但未生成可展示的正文。",
            "code": "hermes_empty",
        }
        return

    yield {
        "type": "done",
        "reply": reply,
        "hermes_session_id": session_key,
        "orientg_hermes_session_key": session_key,
        "tool_calls": stream_tools,
        "artifacts": [],
        "hermes_used": True,
        "synthesis": "hermes_stream",
        "hermes_stream_mode": "chat_completions",
        "hermes_stream_stats": stream_stats,
    }
