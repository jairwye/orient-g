"""Agent 流式事件：执行过程字段与 fast 路径状态（TDD）。"""

from __future__ import annotations

from backend.services.agent_kb_fast_path import stream_kb_fast_path_events


def test_fast_path_stream_includes_trace_status_and_meta(monkeypatch):
    monkeypatch.setattr(
        "backend.services.agent_kb_prefetch.synthesize_kb_reply",
        lambda **kwargs: {
            "ok": True,
            "reply": "成本分析摘要",
            "citations": [],
            "synthesis": "local_llm",
            "llm_model": "test-model",
        },
    )
    events = list(
        stream_kb_fast_path_events(
            tenant_id="tenant1",
            user_query="成本下降原因",
            prefetch_result={"ok": True, "citations": [{"doc_id": "d1"}]},
            prefetch_tool_calls=[{"name": "orientg_kb_ask", "status": "ok"}],
            fixtures={},
        )
    )
    steps = [e.get("step") for e in events if e.get("type") == "status"]
    assert "prefetch_done" in steps
    assert "local_llm_synth" in steps
    assert "local_llm_done" in steps
    done = [e for e in events if e.get("type") == "done"][-1]
    assert done.get("agent_route") == "fast"
    assert done.get("kb_fast_path") is True
    assert done.get("hermes_used") is False
    assert "成本" in (done.get("reply") or "")
