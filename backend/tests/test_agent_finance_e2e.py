"""财务测试账号 + Agent 页链路（Hermes / KB 预检索）TDD。"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app
from backend.routers.settings import DEPARTMENT_FINANCE
from backend.services.agent_kb_prefetch import last_user_query
from backend.services.dev_users import ensure_department_test_user

client = TestClient(app)
FINANCE_TEST_PASSWORD = "FinanceTest!2026"
FINANCE_USER = "finance_test"


def _ensure_finance_token() -> str:
    ensure_department_test_user(
        FINANCE_USER,
        password=FINANCE_TEST_PASSWORD,
        department=DEPARTMENT_FINANCE,
    )
    res = client.post(
        "/api/auth/login",
        json={"username": FINANCE_USER, "password": FINANCE_TEST_PASSWORD},
    )
    assert res.status_code == 200, res.text
    return res.json()["token"]


def _mock_prefetch_factory(
    *,
    reply: str,
    citations: list[dict[str, Any]] | None = None,
    evidence_pack: dict[str, Any] | None = None,
    captured: dict[str, Any] | None = None,
):
    cites = citations or [{"doc_id": "d_finance_1", "chunk_id": "ch1", "evidence_type": "doc_chunk"}]
    pack = evidence_pack or {
        "task_type": "lookup",
        "coverage_score": 0.9,
        "gaps": [],
        "citations": cites,
        "facets": [{"keywords_hit": ["营业收入"]}],
    }

    def _prefetch(user_token, messages, kb_scope, **kwargs):
        query = last_user_query(messages)
        if captured is not None:
            captured["query"] = query
            captured["cols"] = list(kb_scope.get("selected_collection_ids") or [])
        ask_res: dict[str, Any] = {
            "ok": True,
            "reply": reply,
            "citations": cites,
            "evidence_pack": pack,
        }
        prefetch_msg = {
            "role": "system",
            "content": f"预检索摘要：{reply}",
        }
        tool_calls = [
            {
                "name": "orientg_kb_ask",
                "status": "ok",
                "prefetch": True,
                "query": query,
                "result": ask_res,
            }
        ]
        return [prefetch_msg, *messages], ask_res, tool_calls

    return _prefetch


def test_finance_agent_status_ready_when_hermes_configured(monkeypatch):
    monkeypatch.setattr(settings, "hermes_enabled", True)
    monkeypatch.setattr(settings, "hermes_base_url", "http://127.0.0.1:8642")
    monkeypatch.setattr(settings, "hermes_dev_mock", False)

    token = _ensure_finance_token()
    r = client.get("/api/agent/status", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["hermes_configured"] is True
    assert body["hermes_dev_mock_active"] is False
    assert body["ready_for_agent_chat"] is True


def test_finance_agent_chat_default_uses_hermes_not_local(monkeypatch):
    token = _ensure_finance_token()
    monkeypatch.setattr(settings, "hermes_enabled", True)
    monkeypatch.setattr(settings, "hermes_base_url", "http://127.0.0.1:8642")
    monkeypatch.setattr(settings, "hermes_dev_mock", False)
    monkeypatch.setattr(settings, "hermes_agent_kb_synthesize", True)
    monkeypatch.setattr(settings, "hermes_agent_kb_prefetch", False)

    hermes_called = {"n": 0}

    def _hermes(**k):
        hermes_called["n"] += 1
        return {"reply": "Hermes 答复", "tool_calls": [{"name": "orientg_kb_ask"}], "hermes_session_id": "s1", "artifacts": []}

    monkeypatch.setattr("backend.routers.agent.run_agent_chat", _hermes)
    local_called = {"n": 0}
    monkeypatch.setattr(
        "backend.services.agent_kb_local.run_agent_kb_local_answer",
        lambda **k: local_called.__setitem__("n", local_called["n"] + 1) or {"ok": True, "reply": "local"},
    )

    r = client.post(
        "/api/agent/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "messages": [{"role": "user", "content": "华清损益"}],
            "kb_scope": {"selected_collection_ids": ["c_finance_public_1"]},
        },
    )
    assert r.status_code == 200, r.text
    assert hermes_called["n"] == 1
    assert local_called["n"] == 0
    assert r.json().get("hermes_used") is True


def test_finance_agent_chat_stream_returns_sse(monkeypatch):
    token = _ensure_finance_token()
    monkeypatch.setattr(settings, "hermes_enabled", True)
    monkeypatch.setattr(settings, "hermes_base_url", "http://127.0.0.1:8642")
    monkeypatch.setattr(settings, "hermes_dev_mock", False)
    monkeypatch.setattr(settings, "hermes_agent_kb_prefetch", False)

    def _fake_stream(**k):
        yield {"type": "delta", "content": "流"}
        yield {"type": "delta", "content": "式"}
        yield {"type": "done", "reply": "流式", "hermes_session_id": "sess-stream", "tool_calls": []}

    monkeypatch.setattr("backend.routers.agent.stream_agent_chat", _fake_stream)

    r = client.post(
        "/api/agent/chat/stream",
        headers={"Authorization": f"Bearer {token}"},
        json={"messages": [{"role": "user", "content": "你好"}]},
    )
    assert r.status_code == 200
    assert "text/event-stream" in (r.headers.get("content-type") or "")
    body = r.text
    assert '"type": "delta"' in body or '"type":"delta"' in body
    assert "sess-stream" in body


def test_finance_agent_chat_prefetches_kb_before_hermes(monkeypatch):
    token = _ensure_finance_token()
    monkeypatch.setattr(settings, "hermes_enabled", True)
    monkeypatch.setattr(settings, "hermes_base_url", "http://127.0.0.1:8642")
    monkeypatch.setattr(settings, "hermes_dev_mock", False)
    monkeypatch.setattr(settings, "hermes_agent_kb_prefetch", True)
    monkeypatch.setattr(settings, "hermes_agent_kb_synthesize", True)
    monkeypatch.setattr(settings, "hermes_agent_kb_fast_path", False)

    captured: dict = {}
    monkeypatch.setattr(
        "backend.routers.agent.prefetch_kb_context",
        _mock_prefetch_factory(
            reply="财务审核 T+2 表示两个工作日内完成。",
            citations=[{"doc_id": "d_finance_public_rules_1", "chunk_id": "ch_finance_1"}],
            evidence_pack={
                "task_type": "lookup",
                "coverage_score": 0.35,
                "gaps": ["未命中完整制度条文"],
                "citations": [{"doc_id": "d_finance_public_rules_1"}],
                "facets": [],
            },
            captured=captured,
        ),
    )

    def _fake_hermes(**kwargs):
        msgs = kwargs.get("messages") or []
        captured["hermes_messages"] = msgs
        assert any("预检索" in (m.get("content") or "") for m in msgs if m.get("role") == "system")
        return {
            "reply": "根据预检索：T+2 两个工作日。",
            "tool_calls": [],
            "hermes_session_id": "sess-1",
            "artifacts": [],
        }

    monkeypatch.setattr("backend.routers.agent.run_agent_chat", _fake_hermes)

    r = client.post(
        "/api/agent/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "messages": [{"role": "user", "content": "财务审核 T+2 是什么意思？"}],
            "kb_scope": {"selected_collection_ids": ["c_finance_public_1"]},
            "allow_kb_write": False,
            "agent_mode": "standard",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("kb_prefetch") is True
    assert captured["cols"] == ["c_finance_public_1"]
    assert "T+2" in (body.get("reply") or "")
    tools = body.get("tool_calls") or []
    assert any(t.get("name") == "orientg_kb_ask" and t.get("prefetch") for t in tools)


def test_finance_agent_stream_kb_fast_path_skips_hermes(monkeypatch):
    """Tier 0（fast 模式）有 citations 时不应调用 stream_agent_chat（Hermes MCP）。"""
    token = _ensure_finance_token()
    monkeypatch.setattr(settings, "hermes_enabled", True)
    monkeypatch.setattr(settings, "hermes_base_url", "http://127.0.0.1:8642")
    monkeypatch.setattr(settings, "hermes_dev_mock", False)
    monkeypatch.setattr(settings, "hermes_agent_kb_prefetch", True)
    monkeypatch.setattr(settings, "hermes_agent_kb_fast_path", True)
    monkeypatch.setattr(settings, "llm_base_url", "http://llm.test/v1")
    monkeypatch.setattr(settings, "llm_model", "test-model")

    monkeypatch.setattr(
        "backend.routers.agent.prefetch_kb_context",
        _mock_prefetch_factory(
            reply="检索摘要",
            citations=[{"doc_id": "d_finance_1", "chunk_id": "ch1", "evidence_type": "doc_chunk"}],
        ),
    )

    hermes_stream = {"n": 0}

    def _hermes_stream(**k):
        hermes_stream["n"] += 1
        yield {"type": "delta", "content": "不应出现"}
        yield {"type": "done", "reply": "x", "tool_calls": []}

    monkeypatch.setattr("backend.routers.agent.stream_agent_chat", _hermes_stream)

    def _fake_stream_fast(**k):
        yield {"type": "status", "message": "快速路径", "step": "kb_fast_path"}
        yield {"type": "delta", "content": "| 指标 | 2024 | 2025 |"}
        yield {
            "type": "done",
            "ok": True,
            "reply": "| 指标 | 2024 | 2025 |",
            "kb_fast_path": True,
            "hermes_used": False,
            "tool_calls": [],
        }

    monkeypatch.setattr("backend.routers.agent.stream_kb_fast_path_events", lambda **k: _fake_stream_fast())

    r = client.post(
        "/api/agent/chat/stream",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "messages": [{"role": "user", "content": "出具华清25、24两年损益的对比分析表"}],
            "kb_scope": {"selected_collection_ids": ["c_finance_public_1"]},
            "agent_mode": "fast",
        },
    )
    assert r.status_code == 200, r.text
    assert hermes_stream["n"] == 0
    assert "kb_fast_path" in r.text


def test_finance_agent_chat_kb_fast_path_blocking(monkeypatch):
    token = _ensure_finance_token()
    monkeypatch.setattr(settings, "hermes_enabled", True)
    monkeypatch.setattr(settings, "hermes_base_url", "http://127.0.0.1:8642")
    monkeypatch.setattr(settings, "hermes_dev_mock", False)
    monkeypatch.setattr(settings, "hermes_agent_kb_prefetch", True)
    monkeypatch.setattr(settings, "hermes_agent_kb_fast_path", True)

    monkeypatch.setattr(
        "backend.routers.agent.prefetch_kb_context",
        _mock_prefetch_factory(
            reply="x",
            citations=[{"doc_id": "d1", "evidence_type": "doc_chunk"}],
        ),
    )
    hermes_called = {"n": 0}

    def _hermes(**k):
        hermes_called["n"] += 1
        return {"reply": "x", "tool_calls": [], "hermes_session_id": "s", "artifacts": []}

    monkeypatch.setattr("backend.routers.agent.run_agent_chat", _hermes)
    monkeypatch.setattr(
        "backend.services.agent_kb_prefetch.synthesize_kb_reply",
        lambda **k: {
            "ok": True,
            "reply": "华清对比表（本地综合）",
            "citations": [{"doc_id": "d1"}],
            "synthesis": "local_llm",
        },
    )

    r = client.post(
        "/api/agent/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "messages": [{"role": "user", "content": "华清25、24损益对比"}],
            "kb_scope": {"selected_collection_ids": ["c_finance_public_1"]},
            "agent_mode": "fast",
        },
    )
    assert r.status_code == 200, r.text
    assert hermes_called["n"] == 0
    assert r.json().get("kb_fast_path") is True
    assert "对比" in (r.json().get("reply") or "")


def test_finance_agent_chat_kb_uses_local_llm_when_synthesize_disabled(monkeypatch):
    token = _ensure_finance_token()
    monkeypatch.setattr(settings, "hermes_enabled", True)
    monkeypatch.setattr(settings, "hermes_base_url", "http://127.0.0.1:8642")
    monkeypatch.setattr(settings, "hermes_dev_mock", False)
    monkeypatch.setattr(settings, "hermes_agent_kb_prefetch", True)
    monkeypatch.setattr(settings, "hermes_agent_kb_synthesize", False)  # 显式关闭才走本地 LLM
    monkeypatch.setattr(settings, "llm_base_url", "http://llm.test/v1")
    monkeypatch.setattr(settings, "llm_model", "test-model")

    hermes_called = {"n": 0}

    def _hermes(**k):
        hermes_called["n"] += 1
        return {"reply": "x", "tool_calls": [], "hermes_session_id": "s", "artifacts": []}

    monkeypatch.setattr("backend.routers.agent.run_agent_chat", _hermes)
    monkeypatch.setattr(
        "backend.services.agent_kb_local.run_agent_kb_local_answer",
        lambda **k: {
            "ok": True,
            "reply": "华清 2025 年营收约为证据所示金额（LLM 综合）",
            "citations": [{"doc_id": "d_finance_public_rules_1", "chunk_id": "ch1"}],
            "synthesis": "local_llm",
            "llm_model": "test-model",
            "tool_calls": [{"name": "orientg_kb_ask", "prefetch": True}],
        },
    )

    r = client.post(
        "/api/agent/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "messages": [{"role": "user", "content": "华清25年营收是多少"}],
            "kb_scope": {"selected_collection_ids": ["c_finance_public_1"]},
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("hermes_used") is False
    assert body.get("synthesis") == "local_llm"
    assert hermes_called["n"] == 0
    assert "LLM 综合" in (body.get("reply") or "")
    assert "混合检索命中" not in (body.get("reply") or "")


def test_finance_agent_chat_hermes_mock_without_kb_scope_skips_prefetch(monkeypatch):
    token = _ensure_finance_token()
    monkeypatch.setattr(settings, "hermes_enabled", True)
    monkeypatch.setattr(settings, "hermes_base_url", "http://127.0.0.1:8642")
    monkeypatch.setattr(settings, "hermes_dev_mock", False)
    monkeypatch.setattr(settings, "hermes_agent_kb_prefetch", True)

    ask_called = {"n": 0}

    def _fake_ask(*a, **k):
        ask_called["n"] += 1
        return {"ok": True, "reply": "x", "citations": []}

    monkeypatch.setattr("backend.services.agent_kb_prefetch.mcp_tools.orientg_kb_ask", _fake_ask)
    monkeypatch.setattr(
        "backend.routers.agent.run_agent_chat",
        lambda **k: {"reply": "hi", "tool_calls": [], "hermes_session_id": "s", "artifacts": []},
    )

    r = client.post(
        "/api/agent/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"messages": [{"role": "user", "content": "你好"}]},
    )
    assert r.status_code == 200
    assert ask_called["n"] == 0
    assert r.json().get("kb_prefetch") is False


@pytest.mark.integration
def test_finance_agent_chat_live_hermes_simple():
    """需本机 backend + Hermes Gateway；无服务时 skip。"""
    import httpx

    if not settings.hermes_configured or settings.hermes_dev_mock:
        pytest.skip("HERMES_ENABLED + HERMES_BASE_URL required, HERMES_DEV_MOCK=false")

    token = _ensure_finance_token()
    try:
        st = httpx.get("http://127.0.0.1:8642/health", timeout=5)
        if st.status_code != 200:
            pytest.skip("hermes gateway not up")
    except Exception as e:
        pytest.skip(f"hermes gateway not reachable: {e}")

    r = client.post(
        "/api/agent/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"messages": [{"role": "user", "content": "你好，请一句话回复"}]},
    )
    if r.status_code == 502:
        pytest.skip(f"hermes error: {r.json()}")
    assert r.status_code == 200, r.text
    assert (r.json().get("reply") or "").strip()


@pytest.mark.integration
def test_finance_live_huaqing_stream_uses_kb_fast_path(monkeypatch):
    """华清损益对比流式：优先连本机 uvicorn；否则 TestClient + mock 走 Tier 0。"""
    import httpx

    live_fast_path = False
    try:
        st = httpx.get("http://127.0.0.1:8000/api/agent/status", timeout=5)
        st.raise_for_status()
        live_fast_path = bool(st.json().get("hermes_agent_kb_fast_path"))
    except Exception:
        live_fast_path = False

    token = _ensure_finance_token()
    body = {
        "messages": [
            {
                "role": "user",
                "content": "出具一份华清25、24两年损益的对比分析表，仅依据知识库证据。",
            }
        ],
        "kb_scope": {"selected_collection_ids": ["c_finance_public_1"]},
        "allow_kb_write": False,
        "agent_mode": "fast",
    }

    if live_fast_path:
        reply_parts: list[str] = []
        done_meta: dict = {}
        statuses: list[str] = []
        with httpx.Client(timeout=httpx.Timeout(30.0, read=180.0)) as http_client:
            with http_client.stream(
                "POST",
                "http://127.0.0.1:8000/api/agent/chat/stream",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=body,
            ) as res:
                assert res.status_code == 200, res.read()
                buf = ""
                for chunk in res.iter_bytes():
                    buf += chunk.decode("utf-8", errors="replace")
                    while "\n\n" in buf:
                        block, buf = buf.split("\n\n", 1)
                        for line in block.split("\n"):
                            line = line.strip()
                            if not line.startswith("data:"):
                                continue
                            raw = line[5:].strip()
                            if not raw or raw == "[DONE]":
                                continue
                            import json

                            evt = json.loads(raw)
                            if evt.get("type") == "status" and evt.get("message"):
                                statuses.append(str(evt["message"]))
                            if evt.get("type") == "delta" and evt.get("content"):
                                reply_parts.append(str(evt["content"]))
                            if evt.get("type") == "done":
                                done_meta = evt

        reply = "".join(reply_parts).strip() or (done_meta.get("reply") or "").strip()
        assert reply, "empty reply"
        assert done_meta.get("kb_fast_path") is True
        assert done_meta.get("hermes_used") is False
        assert done_meta.get("kb_prefetch") is True
        assert any("跳过 Hermes" in s or "快速路径" in s for s in statuses)
        assert "|" in reply or "对比" in reply
        if settings.chat_llm_available:
            assert "834" in reply or "798" in reply, f"expected P&L numbers in reply: {reply[:300]}"
        return

    monkeypatch.setattr(settings, "hermes_enabled", True)
    monkeypatch.setattr(settings, "hermes_base_url", "http://127.0.0.1:8642")
    monkeypatch.setattr(settings, "hermes_dev_mock", False)
    monkeypatch.setattr(settings, "hermes_agent_kb_prefetch", True)
    monkeypatch.setattr(settings, "hermes_agent_kb_fast_path", True)
    monkeypatch.setattr(
        "backend.routers.agent.prefetch_kb_context",
        _mock_prefetch_factory(
            reply="华清 2025 营业收入 834,527,936.00；2024 年 798,118,000.00",
            citations=[{"doc_id": "d_finance_huaqing_pl_1", "chunk_id": "ch_pl", "evidence_type": "doc_chunk"}],
        ),
    )
    hermes_stream = {"n": 0}

    def _hermes_stream(**k):
        hermes_stream["n"] += 1
        yield {"type": "done", "reply": "x", "tool_calls": []}

    monkeypatch.setattr("backend.routers.agent.stream_agent_chat", _hermes_stream)

    def _fake_stream_fast(**k):
        yield {"type": "status", "message": "快速路径", "step": "kb_fast_path"}
        yield {"type": "delta", "content": "| 指标 | 2024 | 2025 |"}
        yield {
            "type": "done",
            "ok": True,
            "reply": "华清对比表 834527936 / 798118000",
            "kb_fast_path": True,
            "hermes_used": False,
            "kb_prefetch": True,
            "tool_calls": [],
        }

    monkeypatch.setattr("backend.routers.agent.stream_kb_fast_path_events", lambda **k: _fake_stream_fast())

    r = client.post(
        "/api/agent/chat/stream",
        headers={"Authorization": f"Bearer {token}"},
        json=body,
    )
    assert r.status_code == 200, r.text
    assert hermes_stream["n"] == 0
    assert "kb_fast_path" in r.text
    assert "834" in r.text or "798" in r.text


@pytest.mark.integration
def test_finance_agent_chat_live_kb_prefetch():
    """本机 Hermes + DB；KB 预检索 + Hermes 综合（应明显快于纯 MCP 工具环）。"""
    import httpx

    if not settings.hermes_configured or settings.hermes_dev_mock:
        pytest.skip("hermes not configured for live test")
    if not settings.hermes_agent_kb_prefetch:
        pytest.skip("HERMES_AGENT_KB_PREFETCH=false")

    token = _ensure_finance_token()
    try:
        httpx.get("http://127.0.0.1:8642/health", timeout=5).raise_for_status()
    except Exception as e:
        pytest.skip(f"hermes: {e}")

    r = client.post(
        "/api/agent/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "messages": [{"role": "user", "content": "财务审核 T+2 是什么意思？"}],
            "kb_scope": {"selected_collection_ids": ["c_finance_public_1"]},
            "allow_kb_write": False,
        },
    )
    if r.status_code == 502:
        pytest.skip(f"hermes error: {r.json()}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("kb_prefetch") is True
    tools = body.get("tool_calls") or []
    assert any(t.get("prefetch") for t in tools)
    reply = (body.get("reply") or "").lower()
    assert reply and ("t+2" in reply or "工作日" in reply or "两" in reply or "财务" in reply)
