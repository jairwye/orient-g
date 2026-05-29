"""tool_progress completed 保留 running 时的 label（terminal 命令预览）。"""

from __future__ import annotations

from backend.services.hermes_client import enrich_tool_progress_with_labels


def test_enrich_completed_keeps_running_label():
    cache: dict[str, str] = {}
    running = [
        {
            "type": "tool_progress",
            "tool": "terminal",
            "tool_call_id": "c1",
            "status": "running",
            "message": "🔧 terminal: cat references/partial_pnl_data.md",
        },
    ]
    out1 = enrich_tool_progress_with_labels(running, cache)
    assert cache["c1"].startswith("🔧")
    completed = [
        {
            "type": "tool_progress",
            "tool": "terminal",
            "tool_call_id": "c1",
            "status": "completed",
            "message": "terminal",
        },
    ]
    out2 = enrich_tool_progress_with_labels(completed, cache)
    assert "partial_pnl" in out2[0]["message"]
