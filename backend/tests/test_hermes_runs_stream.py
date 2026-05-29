"""Hermes Runs API 事件映射与停止（路线第三步）。"""

from __future__ import annotations

from backend.services.hermes_client import (
    hermes_run_event_to_sse,
    messages_to_hermes_runs_body,
    stop_hermes_run,
)
from unittest.mock import MagicMock, patch


def test_messages_to_hermes_runs_body_splits_system():
    msgs = [
        {"role": "system", "content": "ctx json"},
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "hi"},
        {"role": "user", "content": "second"},
    ]
    body = messages_to_hermes_runs_body(msgs, model="hermes-agent", session_id="sk1")
    assert body["input"] == "second"
    assert body["session_id"] == "sk1"
    assert body["instructions"] == "ctx json"
    assert len(body["conversation_history"]) == 2
    assert body["conversation_history"][0]["content"] == "first"


def test_hermes_run_event_message_delta():
    out = hermes_run_event_to_sse(
        {"event": "message.delta", "delta": "你好", "run_id": "run_1"},
        seen_tool_keys=set(),
    )
    assert out == [{"type": "delta", "content": "你好"}]


def test_hermes_run_event_tool_lifecycle():
    seen: set[str] = set()
    start = hermes_run_event_to_sse(
        {
            "event": "tool.started",
            "tool": "orientg_kb_ask",
            "preview": "kb: 华清",
            "run_id": "run_1",
            "timestamp": 1.0,
        },
        seen_tool_keys=seen,
    )
    assert start[0]["type"] == "tool_progress"
    assert start[0]["status"] == "running"
    key = start[0]["tool_call_id"]
    done = hermes_run_event_to_sse(
        {
            "event": "tool.completed",
            "tool": "orientg_kb_ask",
            "run_id": "run_1",
            "timestamp": 2.0,
        },
        seen_tool_keys=seen,
    )
    assert done[0]["status"] == "completed"
    assert done[0]["tool_call_id"] == key


def test_hermes_run_event_completed():
    out = hermes_run_event_to_sse(
        {
            "event": "run.completed",
            "output": "最终答案",
            "run_id": "run_1",
        },
        seen_tool_keys=set(),
    )
    assert out[0]["type"] == "run_completed"
    assert out[0]["output"] == "最终答案"


@patch("backend.services.hermes_client.settings")
@patch("backend.services.hermes_client.httpx.Client")
def test_stop_hermes_run_posts(mock_client_cls, mock_settings):
    mock_settings.hermes_configured = True
    mock_settings.hermes_base_url = "http://127.0.0.1:8642"
    mock_settings.hermes_internal_token = "tok"
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"status": "stopping"}
    mock_client_cls.return_value.__enter__.return_value.post.return_value = resp
    assert stop_hermes_run("run_abc") is True
