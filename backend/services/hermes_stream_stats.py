"""Hermes 流式编排观测：区分 Hermes 进程内 MCP 与 Orient-G 网关 KB 调用。"""

from __future__ import annotations

from typing import Any

GATEWAY_KB_ASK_SOURCE = "orientg_gateway_primer"


def empty_stream_stats() -> dict[str, Any]:
    return {
        "thinking_chars": 0,
        "delta_chars": 0,
        "tool_progress_events": 0,
        "tool_call_events": 0,
        "hermes_orientg_kb_ask_calls": 0,
        "gateway_orientg_kb_ask_calls": 0,
        "orientg_kb_ask_calls": 0,
        "orientg_kb_supplemental_calls": 0,
        "hermes_mcp_retry_count": 0,
    }


def bump_hermes_mcp_retry(stats: dict[str, Any], *, count: int = 1) -> None:
    """首轮未调 MCP 后的强制重试次数（宽尺子 B：验收常态应为 0）。"""
    stats["hermes_mcp_retry_count"] = int(stats.get("hermes_mcp_retry_count") or 0) + int(count)

def _sync_total_kb_ask(stats: dict[str, Any]) -> None:
    h = int(stats.get("hermes_orientg_kb_ask_calls") or 0)
    g = int(stats.get("gateway_orientg_kb_ask_calls") or 0)
    stats["orientg_kb_ask_calls"] = h + g


def bump_gateway_kb_ask(stats: dict[str, Any], *, count: int = 1) -> None:
    stats["gateway_orientg_kb_ask_calls"] = int(stats.get("gateway_orientg_kb_ask_calls") or 0) + count
    _sync_total_kb_ask(stats)


def count_prefetch_kb_asks(tool_calls: list[dict[str, Any]] | None) -> int:
    n = 0
    for tc in tool_calls or []:
        if not isinstance(tc, dict):
            continue
        if tc.get("prefetch") and "orientg_kb" in str(tc.get("name") or ""):
            n += 1
    return n


def enrich_done_stream_stats(
    stats: dict[str, Any] | None,
    *,
    prefetch_tool_calls: list[dict[str, Any]] | None = None,
    supplemental_tool_count: int | None = None,
) -> dict[str, Any]:
    """合并预检索/补检索到 gateway 计数；orientg_kb_ask_calls = hermes + gateway。"""
    out = dict(stats or empty_stream_stats())
    prefetch_n = count_prefetch_kb_asks(prefetch_tool_calls)
    # stream 内 primer 已计入 gateway_orientg_kb_ask_calls；prefetch 单独加
    base_gateway = int(out.get("gateway_orientg_kb_ask_calls") or 0)
    supplemental = int(
        supplemental_tool_count
        if supplemental_tool_count is not None
        else out.get("orientg_kb_supplemental_calls") or 0
    )
    out["gateway_orientg_kb_ask_calls"] = base_gateway + prefetch_n + supplemental
    out["orientg_kb_supplemental_calls"] = supplemental
    _sync_total_kb_ask(out)
    return out


def hermes_native_kb_ask_count(stats: dict[str, Any] | None) -> int:
    return int((stats or {}).get("hermes_orientg_kb_ask_calls") or 0)


def is_gateway_tool_event(mapped: dict[str, Any]) -> bool:
    src = str(mapped.get("source") or "")
    # 网关 primer / 验证补检索 orchestration 均不计「Hermes 自调 MCP」
    if src in (GATEWAY_KB_ASK_SOURCE, "hermes_native_orchestration"):
        return True
    msg = str(mapped.get("message") or "")
    return (
        msg.startswith("预检索：")
        or msg.startswith("补检索：")
        or msg.startswith("网关引导：")
        or msg.startswith("Hermes 验证补检索")
    )


def bump_stream_event_stats(
    stats: dict[str, Any],
    mapped: dict[str, Any],
) -> None:
    """更新 thinking/delta/tool 计数；kb_ask 分 Hermes / 网关。"""
    t = mapped.get("type")
    if t == "thinking" and mapped.get("content"):
        stats["thinking_chars"] = int(stats.get("thinking_chars") or 0) + len(str(mapped["content"]))
    elif t == "delta" and mapped.get("content"):
        stats["delta_chars"] = int(stats.get("delta_chars") or 0) + len(str(mapped["content"]))
    elif t == "tool_progress":
        stats["tool_progress_events"] = int(stats.get("tool_progress_events") or 0) + 1
        if str(mapped.get("status") or "") != "completed":
            return
        tool = str(mapped.get("tool") or "")
        msg = str(mapped.get("message") or "")
        is_kb = "orientg_kb_ask" in tool or "orientg_kb_ask" in msg or "kb_ask" in tool.lower()
        if not is_kb:
            return
        if is_gateway_tool_event(mapped):
            bump_gateway_kb_ask(stats)
        else:
            stats["hermes_orientg_kb_ask_calls"] = int(stats.get("hermes_orientg_kb_ask_calls") or 0) + 1
            _sync_total_kb_ask(stats)
    elif t == "tool_call" and mapped.get("name"):
        stats["tool_call_events"] = int(stats.get("tool_call_events") or 0) + 1
        name = str(mapped["name"])
        if "orientg_kb" in name and not is_gateway_tool_event(mapped):
            stats["hermes_orientg_kb_ask_calls"] = int(stats.get("hermes_orientg_kb_ask_calls") or 0) + 1
            _sync_total_kb_ask(stats)
