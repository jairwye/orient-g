"""Hermes 流式 stats：Hermes MCP vs 网关 KB 分列。"""

from backend.services.hermes_stream_stats import (
    bump_gateway_kb_ask,
    bump_stream_event_stats,
    empty_stream_stats,
    enrich_done_stream_stats,
    hermes_native_kb_ask_count,
)


def test_empty_stats_has_split_fields():
    s = empty_stream_stats()
    assert s["hermes_orientg_kb_ask_calls"] == 0
    assert s["gateway_orientg_kb_ask_calls"] == 0
    assert s["orientg_kb_ask_calls"] == 0
    assert s.get("hermes_mcp_retry_count", 0) == 0


def test_bump_hermes_mcp_retry_count():
    from backend.services.hermes_stream_stats import bump_hermes_mcp_retry

    s = empty_stream_stats()
    bump_hermes_mcp_retry(s)
    assert s["hermes_mcp_retry_count"] == 1
    bump_hermes_mcp_retry(s)
    assert s["hermes_mcp_retry_count"] == 2


def test_gateway_primer_counts_gateway_only_once_on_completed():
    s = empty_stream_stats()
    bump_stream_event_stats(
        s,
        {
            "type": "tool_progress",
            "tool": "orientg_kb_ask",
            "status": "running",
            "message": "网关引导：orientg_kb_ask（q）",
            "source": "orientg_gateway_primer",
        },
    )
    assert s["gateway_orientg_kb_ask_calls"] == 0
    bump_stream_event_stats(
        s,
        {
            "type": "tool_progress",
            "tool": "orientg_kb_ask",
            "status": "completed",
            "message": "网关引导：orientg_kb_ask 完成（q）",
            "source": "orientg_gateway_primer",
        },
    )
    assert s["gateway_orientg_kb_ask_calls"] == 1
    assert s["hermes_orientg_kb_ask_calls"] == 0
    assert s["orientg_kb_ask_calls"] == 1


def test_hermes_tool_progress_counts_hermes_native():
    s = empty_stream_stats()
    bump_stream_event_stats(
        s,
        {
            "type": "tool_progress",
            "tool": "mcp__orientg__orientg_kb_ask",
            "status": "completed",
            "message": "kb query",
        },
    )
    assert s["hermes_orientg_kb_ask_calls"] == 1
    assert s["gateway_orientg_kb_ask_calls"] == 0


def test_enrich_done_merges_prefetch_and_supplemental():
    s = empty_stream_stats()
    bump_gateway_kb_ask(s)
    out = enrich_done_stream_stats(
        s,
        prefetch_tool_calls=[{"name": "orientg_kb_ask", "prefetch": True, "status": "ok"}],
    )
    assert out["gateway_orientg_kb_ask_calls"] == 2  # primer + prefetch
    assert out["orientg_kb_ask_calls"] == 2


def test_hermes_native_kb_ask_count_helper():
    assert hermes_native_kb_ask_count({"hermes_orientg_kb_ask_calls": 2}) == 2
