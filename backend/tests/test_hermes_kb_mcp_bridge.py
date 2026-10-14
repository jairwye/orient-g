"""Hermes × orientg_kb_ask：网关 MCP 引导与 Runs 请求体约束。"""

from __future__ import annotations

import json
from unittest.mock import patch

from backend.services.agent_hermes_tier_policy import hermes_orientg_context_extras
from backend.services.hermes_client import _build_messages, guard_kb_forbidden_tool_sse
from backend.services.hermes_kb_mcp_bridge import (
    format_kb_ask_primer_for_instructions,
    kb_ask_tool_invocation_hint,
    run_kb_ask_primer,
    should_prime_kb_ask_before_hermes_run,
)
from backend.services.hermes_orientg_policy import kb_route_allowed_toolsets

PERSONNEL_QUERY = "对比分析YYCQ和可比公司A25年的人员结构"


def test_kb_route_toolsets_only_orientg_for_kb_tasks():
    assert kb_route_allowed_toolsets("hermes_full") == ["orientg"]
    assert kb_route_allowed_toolsets("hermes_lite") == ["orientg"]
    assert kb_route_allowed_toolsets("fast") is None


def test_should_prime_before_hermes_full_with_kb_scope():
    assert should_prime_kb_ask_before_hermes_run(
        orientg_route="hermes_full",
        kb_scope={"selected_folder_ids": ["f1"]},
    )
    assert not should_prime_kb_ask_before_hermes_run(
        orientg_route="hermes_lite",
        kb_scope={"selected_folder_ids": ["f1"]},
    )
    assert not should_prime_kb_ask_before_hermes_run(
        orientg_route="hermes_full",
        kb_scope={},
    )


def test_should_prime_skips_native_personnel(monkeypatch):
    """目标 4：native + 人员横比 跳过 gateway primer。"""
    from backend.config import settings

    monkeypatch.setattr(settings, "hermes_native_mcp_reply", True)
    assert not should_prime_kb_ask_before_hermes_run(
        orientg_route="hermes_full",
        kb_scope={"selected_folder_ids": ["f1"]},
        user_query=PERSONNEL_QUERY,
    )
    # 非人员仍可 priming
    assert should_prime_kb_ask_before_hermes_run(
        orientg_route="hermes_full",
        kb_scope={"selected_folder_ids": ["f1"]},
        user_query="对比可比公司E2024与2025营收",
    )


def test_tier_full_with_kb_always_requires_kb_ask():
    extras = hermes_orientg_context_extras(
        tier="full",
        evidence_pack={"gaps": [], "task_type": "general"},
        user_query="对比分析YYCQ和可比公司A25年的人员结构",
        kb_scope={"selected_folder_ids": ["f1"]},
    )
    assert extras.get("orientg_kb_ask_required") is True
    assert int(extras.get("orientg_kb_ask_min_calls_before_final_answer") or 0) >= 2
    suggested = extras.get("orientg_suggested_kb_queries") or []
    assert PERSONNEL_QUERY in suggested[0]
    assert len(suggested) >= 1


def test_build_messages_includes_kb_ask_tool_hint_for_full_tier():
    msgs = _build_messages(
        [{"role": "user", "content": "对比分析YYCQ和可比公司A25年的人员结构"}],
        username="u1",
        kb_scope={"selected_folder_ids": ["f1"]},
        allow_kb_write=False,
        attached_doc_ids=None,
        hermes_session_id="hs1",
        orientg_hermes_session_key="sk-test-1",
        orientg_route="hermes_full",
    )
    payload = json.loads(msgs[0]["content"].split("\n", 1)[1])
    hint = payload.get("orientg_kb_ask_tool") or {}
    assert hint.get("hermes_tool_name") == "mcp__orientg__orientg_kb_ask"
    assert hint.get("example", {}).get("hermes_session_key") == "sk-test-1"
    assert "人员结构" in str(hint.get("example", {}).get("query") or "")


def test_kb_ask_tool_invocation_hint_names_mcp_tool():
    hint = kb_ask_tool_invocation_hint(session_key="sk1", user_query="查人员")
    assert hint["hermes_tool_name"] == "mcp__orientg__orientg_kb_ask"
    assert hint["example"]["hermes_session_key"] == "sk1"
    # Hermes ≥0.21.6：旧单下划线名会 not a known tool → 权限受限幻觉
    assert "mcp_orientg_orientg_kb_ask" not in hint["hermes_tool_name"]
    assert "mcp__orientg__orientg_kb_ask" in str(hint.get("instruction") or "")
    assert "勿用" in str(hint.get("instruction") or "") or "旧名" in str(hint.get("instruction") or "")
    assert "selected_collection_ids" in (hint.get("forbidden_args") or [])
    assert "勿传" in str(hint.get("instruction") or "") or "仅" in str(hint.get("instruction") or "")


def test_native_hint_requires_multi_round_personnel(monkeypatch):
    from backend.config import settings

    monkeypatch.setattr(settings, "hermes_native_mcp_reply", True)
    hint = kb_ask_tool_invocation_hint(session_key="sk1", user_query=PERSONNEL_QUERY)
    text = str(hint.get("instruction") or "")
    assert "至少 2 次" in text or "≥2" in text
    assert "核证" in text or "verify" in text.lower()


def test_format_primer_snippet_for_instructions():
    text = format_kb_ask_primer_for_instructions(
        query="人员结构",
        reply="YYCQ 研发 70 人",
        citations=[{"doc_id": "ud_x", "title": "1.1信息-人员"}],
        native_mode=False,
    )
    assert "orientg_kb_ask" in text or "mcp_orientg" in text
    assert "ud_x" in text
    assert "YYCQ 研发 70 人" not in text


def test_format_primer_snippet_native_allows_preview_clue():
    text = format_kb_ask_primer_for_instructions(
        query="人员结构",
        reply="YYCQ 研发 70 人",
        citations=[{"doc_id": "ud_x"}],
        native_mode=True,
    )
    assert "原生 MCP" in text or "agent_payload" in text
    assert "YYCQ 研发 70 人" in text
    assert "不得直接作为终稿" not in text


@patch("backend.services.knowledge_pipeline.ask_knowledge")
@patch("backend.services.kb_scope_resolve.resolve_kb_scope_for_ask")
def test_run_kb_ask_primer_yields_tool_progress(mock_scope, mock_ask):
    mock_scope.return_value = {
        "collection_ids": [],
        "table_ids": [],
        "attached_doc_ids": [],
        "limit_to_attached": False,
    }
    mock_ask.return_value = {
        "reply": "研发 70 人",
        "citations": [{"doc_id": "ud_1", "title": "人员"}],
        "denied": False,
    }
    events, result = run_kb_ask_primer(
        user_token="tok",
        user_query="YYCQ2025年人员结构",
        kb_scope={"selected_folder_ids": ["f1"]},
        fixtures={"tenant_id": "tenant1"},
    )
    assert result is not None
    assert result.get("reply") == "研发 70 人"
    assert any(e.get("type") == "tool_progress" and e.get("status") == "completed" for e in events)
    mock_ask.assert_called_once()


@patch("backend.services.knowledge_pipeline.ask_knowledge")
@patch("backend.services.kb_scope_resolve.resolve_kb_scope_for_ask")
def test_primer_snippet_appended_to_runs_instructions(mock_scope, mock_ask):
    from backend.services.hermes_client import messages_to_hermes_runs_body
    from backend.services.hermes_kb_mcp_bridge import (
        format_kb_ask_primer_for_instructions,
        run_kb_ask_primer,
    )

    mock_scope.return_value = {
        "collection_ids": [],
        "table_ids": [],
        "attached_doc_ids": [],
        "limit_to_attached": False,
    }
    mock_ask.return_value = {
        "reply": "研发 70 人",
        "citations": [{"doc_id": "ud_1"}],
        "denied": False,
    }
    _events, primer = run_kb_ask_primer(
        user_token="tok",
        user_query="人员结构",
        kb_scope={"selected_folder_ids": ["f1"]},
        fixtures={"tenant_id": "tenant1"},
    )
    body = messages_to_hermes_runs_body(
        [{"role": "system", "content": "ctx"}, {"role": "user", "content": "人员结构"}],
        model="hermes-agent",
        session_id="sk1",
    )
    body["toolsets"] = ["orientg"]
    snippet = format_kb_ask_primer_for_instructions(
        query=str(primer.get("query") or ""),
        reply=str(primer.get("reply") or ""),
        citations=list(primer.get("citations") or []),
        native_mode=False,
    )
    body["instructions"] = f"{body.get('instructions') or ''}\n\n{snippet}".strip()
    assert body["toolsets"] == ["orientg"]
    assert "mcp__orientg__orientg_kb_ask" in body["instructions"]
    assert "研发 70 人" not in body["instructions"]


@patch("backend.services.hermes_client.create_hermes_run")
@patch("backend.services.hermes_client.stop_hermes_run")
@patch("backend.services.knowledge_pipeline.ask_knowledge")
@patch("backend.services.kb_scope_resolve.resolve_kb_scope_for_ask")
@patch("backend.services.hermes_client.settings")
def test_stream_runs_emits_gateway_primer_before_hermes_done(
    mock_settings,
    mock_scope,
    mock_ask,
    _mock_stop,
    mock_create_run,
    monkeypatch,
):
    """进程内 E2E：legacy（非 native）Tier2 Runs 路径须先出现网关 orientg_kb_ask 引导。"""
    import queue
    import threading
    from unittest.mock import MagicMock

    from backend.config import settings as cfg

    # .env 可能已开 native；本测验证 legacy primer 行为
    monkeypatch.setattr(cfg, "hermes_native_mcp_reply", False)
    # hermes_client.settings 被 patch 成 MagicMock；须显式 False，否则 getattr 真值触发 E 尺补齐
    mock_settings.hermes_native_mcp_reply = False

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
        "reply": "YYCQ 研发 70 人；可比公司A 研发 1378 人",
        "citations": [{"doc_id": "ud_personnel", "title": "人员"}],
        "denied": False,
    }
    mock_create_run.return_value = "run_test_1"

    # 模拟 Hermes Runs SSE：快速完成
    class _FakeResp:
        status_code = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def iter_lines(self):
            yield 'data: {"event":"run.completed","output":"## 人员对比\\n完成","run_id":"run_test_1"}'

    fake_client = MagicMock()
    fake_client.stream.return_value.__enter__.return_value = _FakeResp()
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = False

    with patch("backend.services.hermes_client.httpx.Client", return_value=fake_client):
        with patch("backend.services.hermes_client._register_session", return_value="sk-primer-test"):
            events = list(
                __import__("backend.services.hermes_client", fromlist=["stream_agent_chat_runs"]).stream_agent_chat_runs(
                    messages=[{"role": "user", "content": PERSONNEL_QUERY}],
                    username="finance_test",
                    user_token="tok",
                    kb_scope={"selected_folder_ids": ["f1"]},
                    orientg_route="hermes_full",
                )
            )

    primer = [
        e
        for e in events
        if e.get("type") == "tool_progress" and "网关引导" in str(e.get("message") or "")
    ]
    done = next((e for e in events if e.get("type") == "done"), None)
    assert len(primer) >= 1, [e.get("type") for e in events]
    assert mock_create_run.called
    body = mock_create_run.call_args.kwargs["body"]
    assert body.get("toolsets") == ["orientg"]
    instr = str(body.get("instructions") or "")
    assert "YYCQ" not in instr or "mcp__orientg__orientg_kb_ask" in instr or "orientg_kb_ask" in instr
    assert done is not None
    stats = done.get("hermes_stream_stats") or {}
    assert int(stats.get("gateway_orientg_kb_ask_calls") or 0) >= 1
    assert int(stats.get("hermes_orientg_kb_ask_calls") or 0) == 0
    assert int(stats.get("orientg_kb_ask_calls") or 0) >= 1


@patch("backend.services.hermes_client.create_hermes_run")
@patch("backend.services.hermes_client.stop_hermes_run")
@patch("backend.services.knowledge_pipeline.ask_knowledge")
@patch("backend.services.kb_scope_resolve.resolve_kb_scope_for_ask")
@patch("backend.services.hermes_client.settings")
def test_stream_runs_skips_primer_when_native_personnel(
    mock_settings,
    mock_scope,
    mock_ask,
    _mock_stop,
    mock_create_run,
    monkeypatch,
):
    """目标 4：native 人员深度不发 gateway primer。"""
    from unittest.mock import MagicMock

    from backend.config import settings as cfg

    monkeypatch.setattr(cfg, "hermes_native_mcp_reply", True)
    mock_settings.hermes_native_mcp_reply = True

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
        "reply": "核证摘录",
        "citations": [],
        "denied": False,
    }
    mock_create_run.side_effect = ["run_native_1", "run_retry_1"]

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

    runs_sse = {
        "run_native_1": [
            'data: {"event":"run.completed","output":"## 人员对比\\n完成","run_id":"run_native_1"}',
        ],
        "run_retry_1": [
            'data: {"event":"tool.started","tool":"mcp__orientg__orientg_kb_ask","preview":"kb","run_id":"run_retry_1"}',
            'data: {"event":"tool.completed","tool":"mcp__orientg__orientg_kb_ask","preview":"ok","run_id":"run_retry_1"}',
            'data: {"event":"run.completed","output":"### 人员结构对照\\n表","run_id":"run_retry_1"}',
        ],
    }

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
        with patch("backend.services.hermes_client._register_session", return_value="sk-native"):
            events = list(
                __import__("backend.services.hermes_client", fromlist=["stream_agent_chat_runs"]).stream_agent_chat_runs(
                    messages=[{"role": "user", "content": PERSONNEL_QUERY}],
                    username="finance_test",
                    user_token="tok",
                    kb_scope={"selected_folder_ids": ["f1"]},
                    orientg_route="hermes_full",
                )
            )

    primer = [
        e
        for e in events
        if e.get("type") == "tool_progress" and "网关引导" in str(e.get("message") or "")
    ]
    assert primer == [], [e.get("type") for e in events]
    # 无 gateway primer；首轮 0 MCP → 触发 MCP 优先重试（验收常态仍应 retry=0，此处只证保险丝）
    assert mock_create_run.call_count >= 2
    done = next((e for e in events if e.get("type") == "done"), None)
    assert done is not None
    stats = done.get("hermes_stream_stats") or {}
    assert int(stats.get("gateway_orientg_kb_ask_calls") or 0) == 0
    assert int(stats.get("hermes_mcp_retry_count") or 0) >= 1
    assert int(stats.get("hermes_orientg_kb_ask_calls") or 0) >= 1
    # 禁止用 orchestration 把 hermes 凑到 ≥2；ask_knowledge 不应被核证垫片调用
    assert mock_ask.call_count == 0
    steps = [str(e.get("step") or "") for e in events if e.get("type") == "status"]
    assert "hermes_mcp_retry" in steps
    gate_msgs = [
        str(e.get("message") or "")
        for e in events
        if e.get("type") == "status" and e.get("step") == "hermes_mcp_verify_gate"
    ]
    # retry>0 时 want 必须为 False（与实况一致，禁止叠加重试凑核证）
    assert gate_msgs and "want=False" in gate_msgs[0] and "retry=1" in gate_msgs[0]