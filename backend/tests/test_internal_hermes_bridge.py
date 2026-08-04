"""Hermes MCP 跨进程会话桥：internal HTTP API + HTTP fallback 客户端。"""

import time

import jwt
import pytest
from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app
from backend.services import hermes_session_context as session_ctx
from backend.services import hermes_token_bridge as bridge
from backend.services import kb_ask_budget as budget
from backend.services import orientg_mcp_tools as tools
from backend.services.hermes_bridge_http import clear_session_cache_for_tests


BRIDGE_SECRET = "test-bridge-secret-xyz"


@pytest.fixture(autouse=True)
def _reset_stores():
    bridge.reset_for_tests()
    session_ctx.reset_for_tests()
    budget.reset_for_tests()
    clear_session_cache_for_tests()
    yield
    bridge.reset_for_tests()
    session_ctx.reset_for_tests()
    budget.reset_for_tests()
    clear_session_cache_for_tests()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "orientg_mcp_bridge_secret", BRIDGE_SECRET)
    return TestClient(app)


def _jwt(sub: str = "finance_test") -> str:
    return jwt.encode(
        {"sub": sub, "iat": int(time.time()), "exp": int(time.time()) + 3600},
        settings.auth_secret,
        algorithm="HS256",
    )


def _headers() -> dict[str, str]:
    return {"X-OrientG-MCP-Bridge-Secret": BRIDGE_SECRET}


def test_session_resolve_requires_secret(client):
    r = client.post(
        "/api/internal/hermes/session/resolve",
        json={"hermes_session_key": "orientg-x"},
    )
    assert r.status_code == 403


def test_session_resolve_returns_token_and_kb_scope(client):
    tok = _jwt()
    sk = bridge.register("orientg-bridge-1", tok)
    session_ctx.register(
        sk,
        kb_scope={"selected_folder_ids": ["f_competitor_25"]},
        allow_kb_write=False,
        orientg_route="hermes_full",
    )

    r = client.post(
        "/api/internal/hermes/session/resolve",
        headers=_headers(),
        json={"hermes_session_key": sk},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["user_token"] == tok
    assert data["kb_scope"]["selected_folder_ids"] == ["f_competitor_25"]
    assert data["orientg_route"] == "hermes_full"


def test_session_resolve_includes_native_mcp_flag(client, monkeypatch):
    monkeypatch.setattr(settings, "hermes_native_mcp_reply", True)
    tok = _jwt()
    sk = bridge.register("orientg-native-flag", tok)
    session_ctx.register(sk, kb_scope={"selected_folder_ids": ["f1"]}, orientg_route="hermes_full")
    r = client.post(
        "/api/internal/hermes/session/resolve",
        headers=_headers(),
        json={"hermes_session_key": sk},
    )
    assert r.status_code == 200
    assert r.json().get("native_mcp_reply") is True


def test_session_resolve_missing_returns_404(client):
    r = client.post(
        "/api/internal/hermes/session/resolve",
        headers=_headers(),
        json={"hermes_session_key": "orientg-missing"},
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "session_not_found"


def test_kb_ask_budget_consume_via_internal_api(client):
    sk = bridge.register("orientg-budget-1", _jwt())
    budget.register_session_kb_budget(sk, max_calls=1)

    r1 = client.post(
        "/api/internal/hermes/session/kb-ask-budget/consume",
        headers=_headers(),
        json={"hermes_session_key": sk},
    )
    assert r1.status_code == 200
    assert r1.json()["ok"] is True
    assert r1.json().get("denied") is not True

    r2 = client.post(
        "/api/internal/hermes/session/kb-ask-budget/consume",
        headers=_headers(),
        json={"hermes_session_key": sk},
    )
    assert r2.status_code == 200
    assert r2.json()["denied"] is True
    assert "budget" in (r2.json().get("reason") or "").lower()


def test_resolve_user_token_http_fallback_when_local_bridge_empty(monkeypatch):
    """MCP 侧：本地 bridge 未命中时，HTTP 返回的 JWT 应被 resolve_user_token 采用。"""
    tok = _jwt()
    sk = "orientg-http-fallback"

    class _FakeResp:
        status_code = 200

        def json(self):
            return {
                "ok": True,
                "user_token": tok,
                "kb_scope": {"selected_folder_ids": ["f1"]},
                "allow_kb_write": False,
                "orientg_route": "hermes_full",
            }

    monkeypatch.setattr("backend.services.hermes_token_bridge.resolve", lambda _key: None)
    monkeypatch.setenv("ORIENTG_INTERNAL_BASE_URL", "http://127.0.0.1:8000")
    monkeypatch.setenv("ORIENTG_MCP_BRIDGE_SECRET", BRIDGE_SECRET)
    monkeypatch.setattr(
        "backend.services.hermes_bridge_http._post_json",
        lambda path, body: _FakeResp(),
    )

    resolved = tools.resolve_user_token("", hermes_session_key=sk)
    assert resolved == tok


def test_orientg_kb_ask_applies_session_kb_scope_via_http(monkeypatch, client):
    """Hermes MCP 未传 collection_ids 时，应继承会话 kb_scope（经 HTTP 拉取）。"""
    tok = _jwt()
    sk = bridge.register("orientg-scope-1", tok)
    session_ctx.register(
        sk,
        kb_scope={"selected_folder_ids": ["folder_a"]},
    )

    captured: dict = {}

    def fake_ask_knowledge(token, query, **kwargs):
        captured["token"] = token
        captured.update(kwargs)
        return {"denied": False, "reply": "scoped", "citations": [{"doc_id": "d1"}]}

    def fake_resolve_scope(tenant_id, kb_scope, **kwargs):
        return {
            "collection_ids": [],
            "table_ids": [],
            "attached_doc_ids": ["ud_folder_a_doc"],
            "folder_doc_ids": ["ud_folder_a_doc"],
            "folder_ids": ["folder_a"],
            "limit_to_attached": True,
        }

    monkeypatch.setattr(tools, "ask_knowledge", fake_ask_knowledge)
    monkeypatch.setattr(
        "backend.services.kb_scope_resolve.resolve_kb_scope_for_ask",
        fake_resolve_scope,
    )
    monkeypatch.setattr(session_ctx, "resolve", lambda _key: None)
    from backend.services.hermes_bridge_http import RemoteHermesSession

    monkeypatch.setattr(
        "backend.services.hermes_bridge_http.fetch_remote_session",
        lambda _sk: RemoteHermesSession(
            user_token=tok,
            kb_scope={"selected_folder_ids": ["folder_a"]},
        ),
    )

    res = tools.orientg_kb_ask("", "人员结构", hermes_session_key=sk)

    assert res.get("ok") is True
    assert captured["token"] == tok
    assert captured.get("limit_to_attached") is True
    assert captured.get("attached_doc_ids") == ["ud_folder_a_doc"]
