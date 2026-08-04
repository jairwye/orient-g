"""Hermes Tier2：进程内须真调 orientg_kb_ask（TDD）。"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from backend.services.hermes_kb_mcp_bridge import (
    build_mcp_retry_runs_body,
    format_kb_ask_primer_for_instructions,
    primer_reply_belongs_in_hermes_instructions,
)
from backend.services.hermes_stream_stats import bump_stream_event_stats, empty_stream_stats


def test_primer_reply_must_not_be_injected_into_hermes_instructions():
    assert primer_reply_belongs_in_hermes_instructions() is False


def test_format_primer_for_instructions_metadata_only_not_full_reply():
    long_reply = "YYCQ 研发 70 人；" + "可比公司A薪酬减少 " * 50
    text = format_kb_ask_primer_for_instructions(
        query="人员结构",
        reply=long_reply,
        citations=[{"doc_id": "ud_sec04", "title": "sec-04-4"}],
    )
    assert "mcp_orientg_orientg_kb_ask" in text
    assert "不得" in text or "不可" in text
    assert long_reply not in text
    assert "ud_sec04" in text


def test_build_mcp_retry_runs_body_orientg_toolset():
    body = build_mcp_retry_runs_body(
        user_query="对比人员结构",
        session_key="sk-retry-1",
        model="hermes-agent",
        suggested_queries=["可比公司A2025人员结构", "YYCQ2025员工人数"],
    )
    assert body["toolsets"] == ["orientg"]
    assert body["session_id"] == "sk-retry-1"
    assert "sk-retry-1" in body["instructions"]
    assert "mcp_orientg_orientg_kb_ask" in body["instructions"]
    assert "可比公司A2025人员结构" in body["instructions"]


def test_build_mcp_verify_continue_runs_body():
    from backend.services.hermes_kb_mcp_bridge import build_mcp_verify_continue_runs_body

    body = build_mcp_verify_continue_runs_body(
        user_query="对比分析YYCQ和可比公司A25年的人员结构",
        session_key="sk-verify-1",
        model="hermes-agent",
        verification_queries=["YYCQ 2025 1.1信息-人员"],
    )
    assert body["toolsets"] == ["orientg"]
    assert "核证" in body["instructions"]
    assert "YYCQ 2025 1.1信息-人员" in body["instructions"]
    assert "hermes_mcp_retry" not in body["instructions"]


def test_hermes_native_tool_progress_increments_stats():
    stats = empty_stream_stats()
    bump_stream_event_stats(
        stats,
        {
            "type": "tool_progress",
            "tool": "mcp_orientg_orientg_kb_ask",
            "status": "completed",
            "message": "kb: 人员结构",
        },
    )
    assert stats["hermes_orientg_kb_ask_calls"] == 1
    assert stats["gateway_orientg_kb_ask_calls"] == 0


@patch("backend.services.hermes_client.create_hermes_run")
@patch("backend.services.hermes_client.stop_hermes_run")
@patch("backend.services.knowledge_pipeline.ask_knowledge")
@patch("backend.services.kb_scope_resolve.resolve_kb_scope_for_ask")
@patch("backend.services.hermes_client.settings")
def test_stream_runs_mcp_retry_when_first_run_zero_tools(
    mock_settings,
    mock_scope,
    mock_ask,
    _mock_stop,
    mock_create_run,
):
    """首 run 无 MCP 时须发起 MCP 优先重试 run。"""
    mock_settings.hermes_configured = True
    mock_settings.hermes_model = "hermes-agent"
    mock_settings.hermes_request_timeout_s = 300
    mock_settings.hermes_stream_reasoning = False
    mock_scope.return_value = {
        "collection_ids": [],
        "table_ids": [],
        "attached_doc_ids": [],
        "limit_to_attached": False,
    }
    mock_ask.return_value = {
        "reply": "仅网关摘要，不应让 Hermes 跳过 MCP",
        "citations": [{"doc_id": "ud_1"}],
        "denied": False,
    }
    mock_create_run.side_effect = ["run_first", "run_retry"]

    runs_sse = {
        "run_first": [
            'data: {"event":"message.delta","delta":"## 拒答","run_id":"run_first"}',
            'data: {"event":"run.completed","output":"## 拒答","run_id":"run_first"}',
        ],
        "run_retry": [
            'data: {"event":"tool.started","tool":"mcp_orientg_orientg_kb_ask","preview":"kb","run_id":"run_retry"}',
            'data: {"event":"tool.completed","tool":"mcp_orientg_orientg_kb_ask","preview":"ok","run_id":"run_retry"}',
            'data: {"event":"run.completed","output":"## 人员对比\\n有 MCP","run_id":"run_retry"}',
        ],
    }

    class _FakeResp:
        def __init__(self, lines):
            self.status_code = 200
            self._lines = lines

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def iter_lines(self):
            yield from self._lines

    def _stream_side_effect(method, url, **kwargs):
        rid = url.rsplit("/", 2)[-2] if "/events" in url else ""
        lines = runs_sse.get(rid, [])
        ctx = MagicMock()
        ctx.__enter__.return_value = _FakeResp(lines)
        return ctx

    fake_client = MagicMock()
    fake_client.stream.side_effect = _stream_side_effect
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = False

    with patch("backend.services.hermes_client.httpx.Client", return_value=fake_client):
        with patch("backend.services.hermes_client._register_session", return_value="sk-mcp-retry"):
            events = list(
                __import__("backend.services.hermes_client", fromlist=["stream_agent_chat_runs"]).stream_agent_chat_runs(
                    messages=[{"role": "user", "content": "对比分析YYCQ和可比公司A25年的人员结构"}],
                    username="finance_test",
                    user_token="tok",
                    kb_scope={"selected_folder_ids": ["f1"]},
                    orientg_route="hermes_full",
                )
            )

    assert mock_create_run.call_count == 2
    retry_body = mock_create_run.call_args_list[1].kwargs["body"]
    assert retry_body.get("toolsets") == ["orientg"]

    done = next((e for e in events if e.get("type") == "done"), None)
    assert done is not None
    stats = done.get("hermes_stream_stats") or {}
    assert int(stats.get("hermes_orientg_kb_ask_calls") or 0) >= 1
    assert int(stats.get("hermes_mcp_retry_count") or 0) >= 1
    steps = [str(e.get("step") or "") for e in events if e.get("type") == "status"]
    assert "hermes_mcp_retry" in steps


@patch("backend.services.hermes_client.create_hermes_run")
@patch("backend.services.hermes_client.stop_hermes_run")
@patch("backend.services.hermes_client.settings")
def test_stream_runs_verify_continue_when_single_kb_ask(
    mock_settings,
    _mock_stop,
    mock_create_run,
):
    """E：首轮已 MCP×1（非 0）时 Hermes 核证续跑；不计 hermes_mcp_retry。"""
    mock_settings.hermes_configured = True
    mock_settings.hermes_model = "hermes-agent"
    mock_settings.hermes_request_timeout_s = 300
    mock_settings.hermes_stream_reasoning = False
    mock_settings.hermes_native_mcp_reply = True
    mock_create_run.side_effect = ["run_first", "run_verify"]

    runs_sse = {
        "run_first": [
            'data: {"event":"tool.started","tool":"mcp_orientg_orientg_kb_ask","preview":"kb","run_id":"run_first"}',
            'data: {"event":"tool.completed","tool":"mcp_orientg_orientg_kb_ask","preview":"ok","run_id":"run_first"}',
            'data: {"event":"message.delta","delta":"### 人员结构对照\\n|研发|1378|70|","run_id":"run_first"}',
            'data: {"event":"run.completed","output":"### 人员结构对照\\n表","run_id":"run_first"}',
        ],
        "run_verify": [
            'data: {"event":"tool.started","tool":"mcp_orientg_orientg_kb_ask","preview":"verify","run_id":"run_verify"}',
            'data: {"event":"tool.completed","tool":"mcp_orientg_orientg_kb_ask","preview":"ok","run_id":"run_verify"}',
            'data: {"event":"run.completed","output":"### 人员结构对照\\n核证后终稿","run_id":"run_verify"}',
        ],
    }

    class _FakeResp:
        def __init__(self, lines):
            self.status_code = 200
            self._lines = lines

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def iter_lines(self):
            yield from self._lines

    def _stream_side_effect(method, url, **kwargs):
        rid = url.rsplit("/", 2)[-2] if "/events" in url else ""
        lines = runs_sse.get(rid, [])
        ctx = MagicMock()
        ctx.__enter__.return_value = _FakeResp(lines)
        return ctx

    fake_client = MagicMock()
    fake_client.stream.side_effect = _stream_side_effect
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = False

    with patch("backend.services.hermes_client.httpx.Client", return_value=fake_client):
        with patch("backend.services.hermes_client._register_session", return_value="sk-verify"):
            events = list(
                __import__(
                    "backend.services.hermes_client", fromlist=["stream_agent_chat_runs"]
                ).stream_agent_chat_runs(
                    messages=[
                        {
                            "role": "user",
                            "content": "对比分析YYCQ和可比公司A25年的人员结构",
                        }
                    ],
                    username="finance_test",
                    user_token="tok",
                    kb_scope={"selected_folder_ids": ["f1"]},
                    orientg_route="hermes_full",
                )
            )

    assert mock_create_run.call_count == 2
    verify_body = mock_create_run.call_args_list[1].kwargs["body"]
    assert verify_body.get("toolsets") == ["orientg"]
    assert "核证" in str(verify_body.get("instructions") or "")
    done = next((e for e in events if e.get("type") == "done"), None)
    assert done is not None
    stats = done.get("hermes_stream_stats") or {}
    assert int(stats.get("hermes_orientg_kb_ask_calls") or 0) >= 2
    assert int(stats.get("hermes_mcp_retry_count") or 0) == 0
    steps = [str(e.get("step") or "") for e in events if e.get("type") == "status"]
    assert "hermes_mcp_verify_continue" in steps
    assert "hermes_mcp_retry" not in steps
    gate_msgs = [
        str(e.get("message") or "")
        for e in events
        if e.get("type") == "status" and e.get("step") == "hermes_mcp_verify_gate"
    ]
    assert gate_msgs and "want=True" in gate_msgs[0]


def test_orchestrate_personnel_verify_kb_ask_counts_gateway(monkeypatch):
    """orchestration 兜底计 gateway，不得冒充 Hermes 自调凑 hermes≥2。"""
    from backend.services import hermes_kb_mcp_bridge as bridge
    from backend.services.hermes_stream_stats import empty_stream_stats, bump_stream_event_stats

    def fake_ask(*_a, **_k):
        return {"denied": False, "reply": "ok", "citations": []}

    monkeypatch.setattr("backend.services.knowledge_pipeline.ask_knowledge", fake_ask)
    monkeypatch.setattr(
        "backend.services.kb_scope_resolve.resolve_kb_scope_for_ask",
        lambda *_a, **_k: {
            "collection_ids": [],
            "table_ids": [],
            "attached_doc_ids": [],
            "limit_to_attached": False,
        },
    )
    events, _ = bridge.orchestrate_personnel_verify_kb_ask(
        user_token="tok",
        verification_query="可比公司A 2025 研发人员",
        kb_scope={},
    )
    stats = empty_stream_stats()
    for e in events:
        bump_stream_event_stats(stats, e)
    assert int(stats.get("hermes_orientg_kb_ask_calls") or 0) == 0
    assert int(stats.get("gateway_orientg_kb_ask_calls") or 0) == 1