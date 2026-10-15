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
    assert "mcp__orientg__orientg_kb_ask" in text
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
    assert "mcp__orientg__orientg_kb_ask" in body["instructions"]
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
            "tool": "mcp__orientg__orientg_kb_ask",
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
    mock_create_run.side_effect = ["run_first", "run_retry", "run_write_final"]

    final = (
        "### 人员结构对照\\n| 职能 | A | B |\\n| 研发 | 10 | 20 |\\n"
        "### 对比分析\\n有 MCP 终稿"
    )
    runs_sse = {
        "run_first": [
            'data: {"event":"message.delta","delta":"## 拒答","run_id":"run_first"}',
            'data: {"event":"run.completed","output":"## 拒答","run_id":"run_first"}',
        ],
        "run_retry": [
            'data: {"event":"tool.started","tool":"mcp__orientg__orientg_kb_ask","preview":"kb","run_id":"run_retry"}',
            'data: {"event":"tool.completed","tool":"mcp__orientg__orientg_kb_ask","preview":"ok","run_id":"run_retry"}',
            # 仅短过程句：仍须再走成稿续跑
            'data: {"event":"run.completed","output":"已调 MCP，准备成稿","run_id":"run_retry"}',
        ],
        "run_write_final": [
            f'data: {{"event":"message.delta","delta":"{final}","run_id":"run_write_final"}}',
            f'data: {{"event":"run.completed","output":"{final}","run_id":"run_write_final"}}',
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

    assert mock_create_run.call_count >= 2
    retry_body = mock_create_run.call_args_list[1].kwargs["body"]
    assert retry_body.get("toolsets") == ["orientg"]

    done = next((e for e in events if e.get("type") == "done"), None)
    assert done is not None
    stats = done.get("hermes_stream_stats") or {}
    assert int(stats.get("hermes_orientg_kb_ask_calls") or 0) >= 1
    assert int(stats.get("hermes_mcp_retry_count") or 0) >= 1
    steps = [str(e.get("step") or "") for e in events if e.get("type") == "status"]
    assert "hermes_mcp_retry" in steps
    assert "hermes_mcp_write_final_continue" in steps
    assert "人员结构对照" in str(done.get("reply") or "")


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
            'data: {"event":"tool.started","tool":"mcp__orientg__orientg_kb_ask","preview":"kb","run_id":"run_first"}',
            'data: {"event":"tool.completed","tool":"mcp__orientg__orientg_kb_ask","preview":"ok","run_id":"run_first"}',
            # 首轮仅过程稿（尚无 user-facing 终稿）→ 应触发核证续跑
            'data: {"event":"message.delta","delta":"Let me first retrieve via orientg_kb_ask.\\n核证补缺计划：verification_queries","run_id":"run_first"}',
            'data: {"event":"run.completed","output":"Let me first retrieve via orientg_kb_ask.\\n核证补缺计划","run_id":"run_first"}',
        ],
        "run_verify": [
            'data: {"event":"tool.started","tool":"mcp__orientg__orientg_kb_ask","preview":"verify","run_id":"run_verify"}',
            'data: {"event":"tool.completed","tool":"mcp__orientg__orientg_kb_ask","preview":"ok","run_id":"run_verify"}',
            'data: {"event":"message.delta","delta":"### 人员结构对照\\n|研发|1378|70|\\n### 对比分析\\n核证后终稿","run_id":"run_verify"}',
            'data: {"event":"run.completed","output":"### 人员结构对照\\n|研发|1378|70|\\n### 对比分析\\n核证后终稿","run_id":"run_verify"}',
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


@patch("backend.services.hermes_client.create_hermes_run")
@patch("backend.services.hermes_client.stop_hermes_run")
@patch("backend.services.hermes_client.settings")
def test_write_final_when_mcp_done_but_only_process_draft_no_abort(
    mock_settings,
    _mock_stop,
    mock_create_run,
):
    """首轮已 MCP≥2 且 run 正常结束，但仍只有核证过程稿 → 须成稿续跑（勿直接 incomplete）。"""
    mock_settings.hermes_configured = True
    mock_settings.hermes_model = "hermes-agent"
    mock_settings.hermes_request_timeout_s = 300
    mock_settings.hermes_stream_reasoning = False
    mock_settings.hermes_native_mcp_reply = True
    mock_create_run.side_effect = ["run_first", "run_write_final"]

    process = (
        "首轮取证完成。可比公司A研发1378人。evidence_sufficient=false "
        "核证补缺计划 verification_queries next_action=verify_gap_then_write_final"
    )
    final = (
        "### 人员结构对照\\n| 职能 | 可比公司A | YYCQ |\\n"
        "| 研发 | 1378 人 | 70 人 |\\n### 对比分析\\n结构差异明显。"
    )
    runs_sse = {
        "run_first": [
            'data: {"event":"tool.started","tool":"mcp__orientg__orientg_kb_ask","preview":"kb1","run_id":"run_first"}',
            'data: {"event":"tool.completed","tool":"mcp__orientg__orientg_kb_ask","preview":"ok","run_id":"run_first"}',
            'data: {"event":"tool.started","tool":"mcp__orientg__orientg_kb_ask","preview":"kb2","run_id":"run_first"}',
            'data: {"event":"tool.completed","tool":"mcp__orientg__orientg_kb_ask","preview":"ok","run_id":"run_first"}',
            f'data: {{"event":"message.delta","delta":"{process}","run_id":"run_first"}}',
            f'data: {{"event":"run.completed","output":"{process}","run_id":"run_first"}}',
        ],
        "run_write_final": [
            f'data: {{"event":"message.delta","delta":"{final}","run_id":"run_write_final"}}',
            f'data: {{"event":"run.completed","output":"{final}","run_id":"run_write_final"}}',
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
        ctx = MagicMock()
        ctx.__enter__.return_value = _FakeResp(runs_sse.get(rid, []))
        return ctx

    fake_client = MagicMock()
    fake_client.stream.side_effect = _stream_side_effect
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = False

    with patch("backend.services.hermes_client.httpx.Client", return_value=fake_client):
        with patch(
            "backend.services.hermes_client._register_session",
            return_value="sk-write-final-no-abort",
        ):
            events = list(
                __import__(
                    "backend.services.hermes_client",
                    fromlist=["stream_agent_chat_runs"],
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
    steps = [str(e.get("step") or "") for e in events if e.get("type") == "status"]
    assert "hermes_mcp_retry" not in steps
    assert "hermes_mcp_write_final_continue" in steps
    done = next((e for e in events if e.get("type") == "done"), None)
    assert done is not None
    reply = str(done.get("reply") or "")
    assert "人员结构对照" in reply
    assert "1378" in reply
    stats = done.get("hermes_stream_stats") or {}
    assert int(stats.get("hermes_mcp_retry_count") or 0) == 0
    assert int(stats.get("hermes_orientg_kb_ask_calls") or 0) >= 2


@patch("backend.services.hermes_client.create_hermes_run")
@patch("backend.services.hermes_client.stop_hermes_run")
@patch("backend.services.hermes_client.settings")
def test_write_final_when_kb0_substantive_process_draft_skips_mcp_retry(
    mock_settings,
    _mock_stop,
    mock_create_run,
):
    """kb=0 + 实质过程稿：跳过未调 MCP 重试，走成稿续跑（禁止补检索链依赖）。"""
    mock_settings.hermes_configured = True
    mock_settings.hermes_model = "hermes-agent"
    mock_settings.hermes_request_timeout_s = 300
    mock_settings.hermes_stream_reasoning = False
    mock_settings.hermes_native_mcp_reply = True
    mock_create_run.side_effect = ["run_first", "run_write_final"]

    process = (
        "首轮取证完成。可比公司A研发人员1378人，YYCQ70人。"
        "正在做核证补缺计划后撰写终稿。evidence_sufficient=false"
    )
    final = (
        "### 人员结构对照\\n| 职能 | 可比公司A | YYCQ |\\n"
        "| 研发 | 1378 人 | 70 人 |\\n### 对比分析\\n结构差异明显。"
    )
    runs_sse = {
        "run_first": [
            f'data: {{"event":"message.delta","delta":"{process}","run_id":"run_first"}}',
            f'data: {{"event":"run.completed","output":"{process}","run_id":"run_first"}}',
        ],
        "run_write_final": [
            f'data: {{"event":"message.delta","delta":"{final}","run_id":"run_write_final"}}',
            f'data: {{"event":"run.completed","output":"{final}","run_id":"run_write_final"}}',
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
        ctx = MagicMock()
        ctx.__enter__.return_value = _FakeResp(runs_sse.get(rid, []))
        return ctx

    fake_client = MagicMock()
    fake_client.stream.side_effect = _stream_side_effect
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = False

    with patch("backend.services.hermes_client.httpx.Client", return_value=fake_client):
        with patch(
            "backend.services.hermes_client._register_session",
            return_value="sk-kb0-substantive-wf",
        ):
            events = list(
                __import__(
                    "backend.services.hermes_client",
                    fromlist=["stream_agent_chat_runs"],
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
    steps = [str(e.get("step") or "") for e in events if e.get("type") == "status"]
    assert "hermes_mcp_retry" not in steps
    assert "hermes_skip_mcp_retry_substantive_draft" in steps
    assert "hermes_mcp_write_final_continue" in steps
    skip_msgs = [
        str(e.get("message") or "")
        for e in events
        if e.get("type") == "status" and e.get("step") == "hermes_skip_mcp_retry_substantive_draft"
    ]
    assert skip_msgs and "实质" in skip_msgs[0]
    wf_msgs = [
        str(e.get("message") or "")
        for e in events
        if e.get("type") == "status" and e.get("step") == "hermes_mcp_write_final_continue"
    ]
    assert wf_msgs and "过程稿" in wf_msgs[0]
    done = next((e for e in events if e.get("type") == "done"), None)
    assert done is not None
    reply = str(done.get("reply") or "")
    assert "人员结构对照" in reply
    assert "1378" in reply
    stats = done.get("hermes_stream_stats") or {}
    assert int(stats.get("hermes_orientg_kb_ask_calls") or 0) == 0
    assert int(stats.get("hermes_mcp_retry_count") or 0) == 0


@patch("backend.services.hermes_client.create_hermes_run")
@patch("backend.services.hermes_client.stop_hermes_run")
@patch("backend.services.hermes_client.settings")
def test_stream_runs_write_final_after_kb_ask_loop(
    mock_settings,
    _mock_stop,
    mock_create_run,
):
    """kb_ask_loop abort 后必须成稿续跑；禁止把过程稿直接当 done。"""
    from backend.services.hermes_runs_loop_guard import HermesRunsLoopGuard

    mock_settings.hermes_configured = True
    mock_settings.hermes_model = "hermes-agent"
    mock_settings.hermes_request_timeout_s = 300
    mock_settings.hermes_stream_reasoning = False
    mock_settings.hermes_native_mcp_reply = True
    mock_create_run.side_effect = ["run_loop", "run_write_final"]

    personnel_q = "对比分析YYCQ和可比公司A25年的人员结构"
    process = (
        "Let me first retrieve personnel via orientg_kb_ask. "
        "evidence_sufficient=false 核证补缺计划 next_action=verify_gap_then_write_final"
    )
    final = (
        "## 人员结构对照\n"
        "| 职能 | 可比公司A | YYCQ |\n"
        "| 研发 | 1378 | 70 |\n"
        "| 运营 | 242 | 61 |\n"
        "### 对比分析\n结构差异明显。\n"
    )
    import json as _json

    runs_sse = {
        "run_loop": [
            'data: {"event":"tool.started","tool":"mcp__orientg__orientg_kb_ask","preview":"kb1","run_id":"run_loop"}',
            'data: {"event":"tool.completed","tool":"mcp__orientg__orientg_kb_ask","preview":"ok","run_id":"run_loop"}',
            'data: {"event":"tool.started","tool":"mcp__orientg__orientg_kb_ask","preview":"kb2","run_id":"run_loop"}',
            'data: {"event":"tool.completed","tool":"mcp__orientg__orientg_kb_ask","preview":"ok","run_id":"run_loop"}',
            'data: {"event":"tool.started","tool":"mcp__orientg__orientg_kb_ask","preview":"kb3","run_id":"run_loop"}',
            'data: {"event":"tool.completed","tool":"mcp__orientg__orientg_kb_ask","preview":"ok","run_id":"run_loop"}',
            'data: {"event":"tool.started","tool":"mcp__orientg__orientg_kb_ask","preview":"kb4","run_id":"run_loop"}',
            'data: {"event":"tool.completed","tool":"mcp__orientg__orientg_kb_ask","preview":"ok","run_id":"run_loop"}',
            "data: "
            + _json.dumps(
                {"event": "message.delta", "delta": process, "run_id": "run_loop"},
                ensure_ascii=False,
            ),
        ],
        "run_write_final": [
            "data: "
            + _json.dumps(
                {"event": "message.delta", "delta": final, "run_id": "run_write_final"},
                ensure_ascii=False,
            ),
            "data: "
            + _json.dumps(
                {"event": "run.completed", "output": final, "run_id": "run_write_final"},
                ensure_ascii=False,
            ),
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

    def _guard_factory(*, orientg_route=None, **kwargs):
        return HermesRunsLoopGuard(orientg_route=orientg_route)

    with patch("backend.services.hermes_client.httpx.Client", return_value=fake_client):
        with patch(
            "backend.services.hermes_client._register_session",
            return_value="sk-kb-loop-wf",
        ):
            with patch(
                "backend.services.hermes_runs_loop_guard.HermesRunsLoopGuard",
                side_effect=_guard_factory,
            ):
                events = list(
                    __import__(
                        "backend.services.hermes_client",
                        fromlist=["stream_agent_chat_runs"],
                    ).stream_agent_chat_runs(
                        messages=[{"role": "user", "content": personnel_q}],
                        username="finance_test",
                        user_token="tok",
                        kb_scope={"selected_folder_ids": ["f1"]},
                        orientg_route="hermes_full",
                    )
                )

    assert mock_create_run.call_count >= 2
    steps = [str(e.get("step") or "") for e in events if e.get("type") == "status"]
    assert "hermes_mcp_write_final_continue" in steps
    done = next((e for e in events if e.get("type") == "done"), None)
    assert done is not None
    body = str(done.get("reply") or "")
    assert "人员结构对照" in body
    assert "Let me first" not in body


@patch("backend.services.hermes_client.create_hermes_run")
@patch("backend.services.hermes_client.stop_hermes_run")
@patch("backend.services.hermes_client.settings")
def test_stream_runs_write_final_after_forbidden_with_kb(
    mock_settings,
    _mock_stop,
    mock_create_run,
):
    """全局：MCP 已取证后 forbidden 空转 → 成稿续跑，终稿仍为 Hermes。"""
    from backend.services.hermes_runs_loop_guard import HermesRunsLoopGuard

    mock_settings.hermes_configured = True
    mock_settings.hermes_model = "hermes-agent"
    mock_settings.hermes_request_timeout_s = 300
    mock_settings.hermes_stream_reasoning = False
    mock_settings.hermes_native_mcp_reply = True
    mock_create_run.side_effect = ["run_first", "run_write_final"]

    finance_q = "对比分析YYCQ和可比公司A2025年销售费用明细"
    runs_sse = {
        "run_first": [
            'data: {"event":"tool.started","tool":"mcp__orientg__orientg_kb_ask","preview":"kb","run_id":"run_first"}',
            'data: {"event":"tool.completed","tool":"mcp__orientg__orientg_kb_ask","preview":"ok","run_id":"run_first"}',
            'data: {"event":"tool.started","tool":"execute_code","preview":"json.loads","run_id":"run_first"}',
            'data: {"event":"tool.started","tool":"execute_code","preview":"parse","run_id":"run_first"}',
            'data: {"event":"message.delta","delta":"## 费用对比\\n过程","run_id":"run_first"}',
        ],
        "run_write_final": [
            'data: {"event":"message.delta","delta":"## 销售费用对比\\n| 分项 | YYCQ | 可比公司A |\\n| 广告 | 1.2亿 | 0.8亿 |\\n分析：广告投放是主因。","run_id":"run_write_final"}',
            'data: {"event":"run.completed","output":"## 销售费用对比\\n| 分项 | YYCQ | 可比公司A |\\n| 广告 | 1.2亿 | 0.8亿 |\\n分析：广告投放是主因。","run_id":"run_write_final"}',
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

    def _guard_factory(*, orientg_route=None, **kwargs):
        return HermesRunsLoopGuard(
            orientg_route=orientg_route,
            max_forbidden_blocks=2,
        )

    with patch("backend.services.hermes_client.httpx.Client", return_value=fake_client):
        with patch(
            "backend.services.hermes_client._register_session",
            return_value="sk-write-final",
        ):
            with patch(
                "backend.services.hermes_runs_loop_guard.HermesRunsLoopGuard",
                side_effect=_guard_factory,
            ):
                events = list(
                    __import__(
                        "backend.services.hermes_client",
                        fromlist=["stream_agent_chat_runs"],
                    ).stream_agent_chat_runs(
                        messages=[{"role": "user", "content": finance_q}],
                        username="finance_test",
                        user_token="tok",
                        kb_scope={"selected_folder_ids": ["f1"]},
                        orientg_route="hermes_full",
                    )
                )

    assert mock_create_run.call_count == 2
    wf_body = mock_create_run.call_args_list[1].kwargs["body"]
    assert "成稿" in str(wf_body.get("instructions") or "")
    assert "execute_code" in str(wf_body.get("instructions") or "")
    steps = [str(e.get("step") or "") for e in events if e.get("type") == "status"]
    assert "hermes_mcp_write_final_continue" in steps
    done = next((e for e in events if e.get("type") == "done"), None)
    assert done is not None
    assert "销售费用" in str(done.get("reply") or "") or "广告" in str(done.get("reply") or "")


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


_GOOD_PERSONNEL_FINAL = (
    "YYCQ vs 可比公司A · 2025 人员结构对比\\n"
    "### 人员结构对照\\n"
    "| 职能 | 可比公司A | YYCQ |\\n"
    "| 研发 | 1378 人 | 70 人 |\\n"
    "| 销售 | 946 人 | 证据未覆盖 |\\n"
    "| 运营 | 242 人 | 61 人 |\\n"
    "### 对比分析\\n"
    "两家口径不同，研发维度可比。"
)


@patch("backend.services.hermes_client.create_hermes_run")
@patch("backend.services.hermes_client.stop_hermes_run")
@patch("backend.services.hermes_client.settings")
def test_skip_mcp_retry_when_user_facing_final_already_ready(
    mock_settings,
    _mock_stop,
    mock_create_run,
):
    """已有合格用户面终稿时，禁止因「未调 MCP」发起优先重试（全局主答原则）。"""
    mock_settings.hermes_configured = True
    mock_settings.hermes_model = "hermes-agent"
    mock_settings.hermes_request_timeout_s = 300
    mock_settings.hermes_stream_reasoning = False
    mock_settings.hermes_native_mcp_reply = True
    mock_create_run.side_effect = ["run_first"]

    runs_sse = {
        "run_first": [
            f'data: {{"event":"message.delta","delta":"{_GOOD_PERSONNEL_FINAL}","run_id":"run_first"}}',
            f'data: {{"event":"run.completed","output":"{_GOOD_PERSONNEL_FINAL}","run_id":"run_first"}}',
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
        with patch(
            "backend.services.hermes_client._register_session",
            return_value="sk-no-mcp-retry",
        ):
            events = list(
                __import__(
                    "backend.services.hermes_client",
                    fromlist=["stream_agent_chat_runs"],
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

    assert mock_create_run.call_count == 1
    steps = [str(e.get("step") or "") for e in events if e.get("type") == "status"]
    assert "hermes_mcp_retry" not in steps
    done = next((e for e in events if e.get("type") == "done"), None)
    assert done is not None
    reply = str(done.get("reply") or "")
    assert "人员结构对照" in reply
    assert "1378" in reply
    stats = done.get("hermes_stream_stats") or {}
    assert int(stats.get("hermes_mcp_retry_count") or 0) == 0


@patch("backend.services.hermes_client.create_hermes_run")
@patch("backend.services.hermes_client.stop_hermes_run")
@patch("backend.services.knowledge_pipeline.ask_knowledge")
@patch("backend.services.kb_scope_resolve.resolve_kb_scope_for_ask")
@patch("backend.services.hermes_client.settings")
def test_mcp_retry_failure_preserves_prior_user_facing_draft(
    mock_settings,
    mock_scope,
    mock_ask,
    _mock_stop,
    mock_create_run,
):
    """防御：即便仍进入 MCP 重试且 follow-up 流失败，done 须保留首轮合格 draft。"""
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
    mock_ask.return_value = {"reply": "x", "citations": [{"doc_id": "ud_1"}], "denied": False}
    mock_create_run.side_effect = ["run_first", "run_retry"]

    runs_sse = {
        "run_first": [
            f'data: {{"event":"message.delta","delta":"{_GOOD_PERSONNEL_FINAL}","run_id":"run_first"}}',
            f'data: {{"event":"run.completed","output":"{_GOOD_PERSONNEL_FINAL}","run_id":"run_first"}}',
        ],
        "run_retry": [],
    }

    class _FakeResp:
        def __init__(self, lines, *, fail: bool = False):
            self.status_code = 200
            self._lines = lines
            self._fail = fail

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def iter_lines(self):
            if self._fail:
                raise __import__("httpx").RequestError("retry stream broken")
            yield from self._lines

    def _stream_side_effect(method, url, **kwargs):
        rid = url.rsplit("/", 2)[-2] if "/events" in url else ""
        fail = rid == "run_retry"
        ctx = MagicMock()
        ctx.__enter__.return_value = _FakeResp(runs_sse.get(rid, []), fail=fail)
        return ctx

    fake_client = MagicMock()
    fake_client.stream.side_effect = _stream_side_effect
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = False

    with patch("backend.services.hermes_client.httpx.Client", return_value=fake_client):
        with patch(
            "backend.services.hermes_client._register_session",
            return_value="sk-retry-preserve",
        ):
            # 故意关掉 user-facing / substantive 门禁，专测「retry 失败」的 snapshot 恢复
            with patch(
                "backend.services.hermes_response_analysis.hermes_reply_is_user_facing_final",
                return_value=False,
            ):
                with patch(
                    "backend.services.hermes_response_analysis.hermes_reply_has_substantive_draft",
                    return_value=False,
                ):
                    events = list(
                        __import__(
                            "backend.services.hermes_client",
                            fromlist=["stream_agent_chat_runs"],
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
    done = next((e for e in events if e.get("type") == "done"), None)
    assert done is not None
    reply = str(done.get("reply") or "")
    assert "人员结构对照" in reply
    assert "1378" in reply


def test_hermes_run_event_counts_tool_name_field_as_kb_ask():
    """Runs 事件若用 name 而非 tool 字段，仍应计入 Hermes MCP。"""
    from backend.services.hermes_client import hermes_run_event_to_sse
    from backend.services.hermes_stream_stats import bump_stream_event_stats, empty_stream_stats

    seen: set[str] = set()
    started = hermes_run_event_to_sse(
        {
            "event": "tool.started",
            "name": "mcp__orientg__orientg_kb_ask",
            "preview": "q",
            "run_id": "r1",
        },
        seen_tool_keys=seen,
    )
    completed = hermes_run_event_to_sse(
        {
            "event": "tool.completed",
            "name": "mcp__orientg__orientg_kb_ask",
            "preview": "ok",
            "run_id": "r1",
        },
        seen_tool_keys=seen,
    )
    stats = empty_stream_stats()
    for ev in [*started, *completed]:
        bump_stream_event_stats(stats, ev)
    assert int(stats.get("hermes_orientg_kb_ask_calls") or 0) == 1


def test_hermes_run_event_completed_without_started_still_counts_kb_ask():
    """Gateway 偶发只推 tool.completed：不得丢弃，否则 MCP 计数假 0 → 假重试毁流。"""
    from backend.services.hermes_client import hermes_run_event_to_sse
    from backend.services.hermes_stream_stats import bump_stream_event_stats, empty_stream_stats

    seen: set[str] = set()
    completed = hermes_run_event_to_sse(
        {
            "event": "tool.completed",
            "name": "mcp__orientg__orientg_kb_ask",
            "preview": "ok citations=12",
            "run_id": "r_orphan",
        },
        seen_tool_keys=seen,
    )
    assert completed, "tool.completed without prior started must emit SSE"
    assert completed[0].get("status") == "completed"
    stats = empty_stream_stats()
    for ev in completed:
        bump_stream_event_stats(stats, ev)
    assert int(stats.get("hermes_orientg_kb_ask_calls") or 0) == 1


@patch("backend.services.hermes_client.create_hermes_run")
@patch("backend.services.hermes_client.stop_hermes_run")
@patch("backend.services.hermes_client.settings")
def test_tool_name_field_events_prevent_false_mcp_retry(
    mock_settings,
    _mock_stop,
    mock_create_run,
):
    """仅 name 字段的 tool 事件须计入 MCP，避免假「未调用」重试。"""
    mock_settings.hermes_configured = True
    mock_settings.hermes_model = "hermes-agent"
    mock_settings.hermes_request_timeout_s = 300
    mock_settings.hermes_stream_reasoning = False
    mock_settings.hermes_native_mcp_reply = True
    mock_create_run.side_effect = ["run_first"]

    runs_sse = {
        "run_first": [
            'data: {"event":"tool.started","name":"mcp__orientg__orientg_kb_ask","preview":"kb","run_id":"run_first"}',
            'data: {"event":"tool.completed","name":"mcp__orientg__orientg_kb_ask","preview":"ok","run_id":"run_first"}',
            f'data: {{"event":"message.delta","delta":"{_GOOD_PERSONNEL_FINAL}","run_id":"run_first"}}',
            f'data: {{"event":"run.completed","output":"{_GOOD_PERSONNEL_FINAL}","run_id":"run_first"}}',
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
        ctx = MagicMock()
        ctx.__enter__.return_value = _FakeResp(runs_sse.get(rid, []))
        return ctx

    fake_client = MagicMock()
    fake_client.stream.side_effect = _stream_side_effect
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = False

    with patch("backend.services.hermes_client.httpx.Client", return_value=fake_client):
        with patch(
            "backend.services.hermes_client._register_session",
            return_value="sk-name-field",
        ):
            events = list(
                __import__(
                    "backend.services.hermes_client",
                    fromlist=["stream_agent_chat_runs"],
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

    assert mock_create_run.call_count == 1
    steps = [str(e.get("step") or "") for e in events if e.get("type") == "status"]
    assert "hermes_mcp_retry" not in steps
    done = next((e for e in events if e.get("type") == "done"), None)
    assert done is not None
    stats = done.get("hermes_stream_stats") or {}
    assert int(stats.get("hermes_orientg_kb_ask_calls") or 0) >= 1


@patch("backend.services.hermes_client.create_hermes_run")
@patch("backend.services.hermes_client.stop_hermes_run")
@patch("backend.services.hermes_client.settings")
def test_orphan_tool_completed_prevents_false_mcp_retry(
    mock_settings,
    _mock_stop,
    mock_create_run,
):
    """仅 tool.completed（无 started）须计入 MCP，禁止假「未调用」优先重试。"""
    mock_settings.hermes_configured = True
    mock_settings.hermes_model = "hermes-agent"
    mock_settings.hermes_request_timeout_s = 300
    mock_settings.hermes_stream_reasoning = False
    mock_settings.hermes_native_mcp_reply = True
    # count=1 后可能走核证续跑（非假 MCP retry）
    mock_create_run.side_effect = ["run_first", "run_verify"]

    process = (
        "首轮取证完成。可比公司A研发人员1378人，YYCQ70人。"
        "需要第二轮不同query核证补缺。"
    )
    final = (
        "### 人员结构对照\\n| 职能 | 可比公司A | YYCQ |\\n"
        "| 研发 | 1378 人 | 70 人 |\\n### 对比分析\\n核证后终稿"
    )
    runs_sse = {
        "run_first": [
            # 无 tool.started：旧逻辑会丢 completed → count=0 → 假重试
            'data: {"event":"tool.completed","name":"mcp__orientg__orientg_kb_ask","preview":"ok","run_id":"run_first"}',
            f'data: {{"event":"message.delta","delta":"{process}","run_id":"run_first"}}',
            f'data: {{"event":"run.completed","output":"{process}","run_id":"run_first"}}',
        ],
        "run_verify": [
            'data: {"event":"tool.started","tool":"mcp__orientg__orientg_kb_ask","preview":"v","run_id":"run_verify"}',
            'data: {"event":"tool.completed","tool":"mcp__orientg__orientg_kb_ask","preview":"ok","run_id":"run_verify"}',
            f'data: {{"event":"message.delta","delta":"{final}","run_id":"run_verify"}}',
            f'data: {{"event":"run.completed","output":"{final}","run_id":"run_verify"}}',
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
        ctx = MagicMock()
        ctx.__enter__.return_value = _FakeResp(runs_sse.get(rid, []))
        return ctx

    fake_client = MagicMock()
    fake_client.stream.side_effect = _stream_side_effect
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = False

    with patch("backend.services.hermes_client.httpx.Client", return_value=fake_client):
        with patch(
            "backend.services.hermes_client._register_session",
            return_value="sk-orphan-completed",
        ):
            events = list(
                __import__(
                    "backend.services.hermes_client",
                    fromlist=["stream_agent_chat_runs"],
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

    # 首轮 + 核证续跑；不得假「未调 MCP」再开 hermes_mcp_retry
    assert mock_create_run.call_count == 2
    steps = [str(e.get("step") or "") for e in events if e.get("type") == "status"]
    assert "hermes_mcp_retry" not in steps
    assert "hermes_mcp_verify_continue" in steps
    done = next((e for e in events if e.get("type") == "done"), None)
    assert done is not None
    stats = done.get("hermes_stream_stats") or {}
    assert int(stats.get("hermes_orientg_kb_ask_calls") or 0) >= 1
    assert int(stats.get("hermes_mcp_retry_count") or 0) == 0


@patch("backend.services.hermes_client.create_hermes_run")
@patch("backend.services.hermes_client.stop_hermes_run")
@patch("backend.services.hermes_client.settings")
def test_skip_mcp_retry_when_substantive_process_draft_ready(
    mock_settings,
    _mock_stop,
    mock_create_run,
):
    """实质过程稿（含证据数字）即便尚非 user-facing 终稿，也不得假 MCP 重试清稿毁流。

    kb=0 + 实质过程稿可走成稿续跑（非 MCP 重试）；禁止未调 MCP 优先重试毁流。
    """
    mock_settings.hermes_configured = True
    mock_settings.hermes_model = "hermes-agent"
    mock_settings.hermes_request_timeout_s = 300
    mock_settings.hermes_stream_reasoning = False
    mock_settings.hermes_native_mcp_reply = True
    mock_create_run.side_effect = ["run_first", "run_write_final"]

    process = (
        "首轮取证完成。证据显示可比公司A研发人员1,378人、销售946人；"
        "YYCQ研发70人、运营61人。正在做核证补缺计划："
        "verification_queries 若干后撰写终稿。"
    )
    final = (
        "### 人员结构对照\\n| 职能 | 可比公司A | YYCQ |\\n"
        "| 研发 | 1378 | 70 |\\n### 对比分析\\n结构差异明显。"
    )
    runs_sse = {
        "run_first": [
            f'data: {{"event":"message.delta","delta":"{process}","run_id":"run_first"}}',
            f'data: {{"event":"run.completed","output":"{process}","run_id":"run_first"}}',
        ],
        "run_write_final": [
            f'data: {{"event":"message.delta","delta":"{final}","run_id":"run_write_final"}}',
            f'data: {{"event":"run.completed","output":"{final}","run_id":"run_write_final"}}',
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
        ctx = MagicMock()
        ctx.__enter__.return_value = _FakeResp(runs_sse.get(rid, []))
        return ctx

    fake_client = MagicMock()
    fake_client.stream.side_effect = _stream_side_effect
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = False

    with patch("backend.services.hermes_client.httpx.Client", return_value=fake_client):
        with patch(
            "backend.services.hermes_client._register_session",
            return_value="sk-substantive-process",
        ):
            events = list(
                __import__(
                    "backend.services.hermes_client",
                    fromlist=["stream_agent_chat_runs"],
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
    steps = [str(e.get("step") or "") for e in events if e.get("type") == "status"]
    assert "hermes_mcp_retry" not in steps
    assert "hermes_skip_mcp_retry_substantive_draft" in steps
    assert "hermes_mcp_write_final_continue" in steps
    done = next((e for e in events if e.get("type") == "done"), None)
    assert done is not None
    reply = str(done.get("reply") or "")
    assert "1378" in reply or "1,378" in reply
    stats = done.get("hermes_stream_stats") or {}
    assert int(stats.get("hermes_mcp_retry_count") or 0) == 0


@patch("backend.services.hermes_client.create_hermes_run")
@patch("backend.services.hermes_client.stop_hermes_run")
@patch("backend.services.knowledge_pipeline.ask_knowledge")
@patch("backend.services.kb_scope_resolve.resolve_kb_scope_for_ask")
@patch("backend.services.hermes_client.settings")
def test_mcp_retry_failure_restores_even_after_partial_junk(
    mock_settings,
    mock_scope,
    mock_ask,
    _mock_stop,
    mock_create_run,
):
    """retry 流若先写入垃圾 delta 再断连，须强制恢复快照（不得留下 junk）。"""
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
    mock_ask.return_value = {"reply": "x", "citations": [{"doc_id": "ud_1"}], "denied": False}
    mock_create_run.side_effect = ["run_first", "run_retry"]

    runs_sse = {
        "run_first": [
            f'data: {{"event":"message.delta","delta":"{_GOOD_PERSONNEL_FINAL}","run_id":"run_first"}}',
            f'data: {{"event":"run.completed","output":"{_GOOD_PERSONNEL_FINAL}","run_id":"run_first"}}',
        ],
        "run_retry": [
            'data: {"event":"message.delta","delta":"junk partial","run_id":"run_retry"}',
        ],
    }

    class _FakeResp:
        def __init__(self, lines, *, fail_after: bool = False):
            self.status_code = 200
            self._lines = lines
            self._fail_after = fail_after

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def iter_lines(self):
            yield from self._lines
            if self._fail_after:
                raise __import__("httpx").RequestError("retry stream broken after junk")

    def _stream_side_effect(method, url, **kwargs):
        rid = url.rsplit("/", 2)[-2] if "/events" in url else ""
        fail = rid == "run_retry"
        ctx = MagicMock()
        ctx.__enter__.return_value = _FakeResp(runs_sse.get(rid, []), fail_after=fail)
        return ctx

    fake_client = MagicMock()
    fake_client.stream.side_effect = _stream_side_effect
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = False

    with patch("backend.services.hermes_client.httpx.Client", return_value=fake_client):
        with patch(
            "backend.services.hermes_client._register_session",
            return_value="sk-retry-junk",
        ):
            with patch(
                "backend.services.hermes_response_analysis.hermes_reply_is_user_facing_final",
                return_value=False,
            ):
                with patch(
                    "backend.services.hermes_response_analysis.hermes_reply_has_substantive_draft",
                    return_value=False,
                ):
                    events = list(
                        __import__(
                            "backend.services.hermes_client",
                            fromlist=["stream_agent_chat_runs"],
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
    done = next((e for e in events if e.get("type") == "done"), None)
    assert done is not None
    reply = str(done.get("reply") or "")
    assert "junk" not in reply.lower()
    assert "人员结构对照" in reply
    assert "1378" in reply
