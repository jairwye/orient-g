"""Hermes OpenAI / Gateway SSE 解析（TDD）。"""

from __future__ import annotations

import json

from backend.services.hermes_client import (
    HermesSseParser,
    _build_payload,
    iter_openai_stream_deltas,
    iter_openai_stream_events,
    parse_sse_data_line,
    sse_events_from_hermes_line,
)


def test_parse_sse_data_line_delta():
    line = 'data: {"choices":[{"delta":{"content":"你"}}]}'
    obj = parse_sse_data_line(line)
    assert obj is not None
    parts = list(iter_openai_stream_deltas(line))
    assert parts == ["你"]


def test_parse_sse_done_line():
    assert parse_sse_data_line("data: [DONE]") is None


def test_parse_sse_tool_call_delta():
    line = 'data: {"choices":[{"delta":{"tool_calls":[{"function":{"name":"orientg_kb_ask"}}]}}]}'
    events = list(iter_openai_stream_events(line))
    assert any(e.get("kind") == "tool_call" and e.get("name") == "orientg_kb_ask" for e in events)


def test_hermes_sse_parser_tool_progress_running():
    payload = json.dumps(
        {
            "tool": "mcp_orientg_orientg_kb_ask",
            "emoji": "📚",
            "label": "orientg_kb_ask: 华清营收",
            "toolCallId": "call_abc",
            "status": "running",
        },
        ensure_ascii=False,
    )
    parser = HermesSseParser()
    events: list[dict] = []
    events.extend(parser.feed("event: hermes.tool.progress"))
    events.extend(parser.feed(f"data: {payload}"))
    assert len(events) == 1
    assert events[0]["kind"] == "tool_progress"
    assert events[0]["tool"] == "mcp_orientg_orientg_kb_ask"
    assert events[0]["toolCallId"] == "call_abc"
    assert events[0]["status"] == "running"
    assert events[0]["emoji"] == "📚"


def test_hermes_sse_parser_tool_progress_completed():
    parser = HermesSseParser()
    events = []
    events.extend(parser.feed("event: hermes.tool.progress"))
    events.extend(
        parser.feed('data: {"tool":"terminal","toolCallId":"c1","status":"completed"}')
    )
    assert events[0]["status"] == "completed"


def test_hermes_sse_parser_openai_delta_after_event_reset():
    parser = HermesSseParser()
    events = []
    events.extend(parser.feed("event: hermes.tool.progress"))
    events.extend(parser.feed('data: {"tool":"t","toolCallId":"x","status":"running"}'))
    events.extend(
        parser.feed('data: {"choices":[{"delta":{"content":"答"}}]}')
    )
    assert events[0]["kind"] == "tool_progress"
    assert any(e.get("kind") == "delta" and e.get("content") == "答" for e in events)


def test_sse_events_from_hermes_line_maps_tool_progress_to_sse():
    parser = HermesSseParser()
    parser.feed("event: hermes.tool.progress")
    out = sse_events_from_hermes_line(
        parser,
        'data: {"tool":"orientg_kb_ask","label":"ask","toolCallId":"id1","status":"running","emoji":"🔧"}',
    )
    assert len(out) == 1
    assert out[0]["type"] == "tool_progress"
    assert out[0]["tool_call_id"] == "id1"
    assert out[0]["status"] == "running"
    assert "🔧" in out[0]["message"]


def test_build_payload_stream_tool_progress():
    payload = _build_payload(
        messages=[{"role": "user", "content": "hi"}],
        username="u1",
        kb_scope=None,
        allow_kb_write=False,
        attached_doc_ids=None,
        hermes_session_id=None,
        session_key="sk-test",
        stream=True,
    )
    assert payload["stream"] is True
    assert payload.get("stream_tool_progress") is True
