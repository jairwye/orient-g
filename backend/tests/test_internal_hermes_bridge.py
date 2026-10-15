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


def test_remote_budget_fail_closed_when_bridge_errors(monkeypatch):
    from backend.services import hermes_bridge_http as http_bridge

    monkeypatch.setattr(http_bridge, "bridge_http_enabled", lambda: True)

    def boom(*_a, **_k):
        raise RuntimeError("bridge down")

    monkeypatch.setattr(http_bridge, "_post_json", boom)
    deny = http_bridge.consume_remote_kb_ask_budget("orientg-budget-fail")
    assert deny is not None
    assert "unavailable" in deny.lower()


def test_kb_ask_skips_remote_budget_when_shared_session_exists(monkeypatch):
    """MCP 子进程：DB 已有会话预算时，即使 HTTP 桥挂了也不应 deny。"""
    from backend.services import hermes_bridge_http as http_bridge
    from backend.services import hermes_shared_session as shared

    tok = _jwt()
    sk = "orientg-db-budget-skip-http"
    shared.persist_session(
        sk,
        tok,
        kb_scope={"selected_folder_ids": ["f1"]},
        kb_budget_max=None,
        orientg_route="hermes_full",
    )
    bridge.reset_for_tests()
    budget.reset_for_tests()

    http_calls: list[str] = []

    def boom(path, body):
        http_calls.append(path)
        raise RuntimeError("bridge must not be called")

    monkeypatch.setattr(http_bridge, "bridge_http_enabled", lambda: True)
    monkeypatch.setattr(http_bridge, "_post_json", boom)

    captured: dict = {}

    def fake_ask_knowledge(token, query, **kwargs):
        captured["token"] = token
        return {"denied": False, "reply": "ok", "citations": [{"doc_id": "d1"}]}

    monkeypatch.setattr(tools, "ask_knowledge", fake_ask_knowledge)
    monkeypatch.setattr(
        "backend.services.kb_scope_resolve.resolve_kb_scope_for_ask",
        lambda *a, **k: {
            "collection_ids": [],
            "table_ids": [],
            "attached_doc_ids": ["d1"],
            "limit_to_attached": True,
        },
    )

    res = tools.orientg_kb_ask("", "人员", hermes_session_key=sk)
    assert res.get("ok") is True
    assert captured.get("token") == tok
    assert not any("kb-ask-budget" in p for p in http_calls)


def test_kb_ask_uses_remote_budget_when_no_local_or_db_session(monkeypatch):
    """无内存桥、无 DB 会话时，须走 HTTP budget consume。"""
    from backend.services import hermes_bridge_http as http_bridge

    sk = "orientg-need-http-budget"
    bridge.reset_for_tests()
    budget.reset_for_tests()

    class _Ok:
        status_code = 200

        def json(self):
            return {"ok": True, "denied": False}

    calls: list[str] = []

    def fake_post(path, body):
        calls.append(path)
        if "resolve" in path:
            class _Sess:
                status_code = 200

                def json(self):
                    return {
                        "ok": True,
                        "user_token": _jwt(),
                        "kb_scope": {"selected_folder_ids": ["f1"]},
                        "allow_kb_write": False,
                    }

            return _Sess()
        return _Ok()

    monkeypatch.setenv("ORIENTG_INTERNAL_BASE_URL", "http://127.0.0.1:8000")
    monkeypatch.setenv("ORIENTG_MCP_BRIDGE_SECRET", BRIDGE_SECRET)
    monkeypatch.setattr(http_bridge, "_post_json", fake_post)
    monkeypatch.setattr(tools, "ask_knowledge", lambda *a, **k: {
        "denied": False,
        "reply": "ok",
        "citations": [{"doc_id": "d1"}],
    })
    monkeypatch.setattr(
        "backend.services.kb_scope_resolve.resolve_kb_scope_for_ask",
        lambda *a, **k: {
            "collection_ids": [],
            "table_ids": [],
            "attached_doc_ids": ["d1"],
            "limit_to_attached": True,
        },
    )

    res = tools.orientg_kb_ask("", "人员", hermes_session_key=sk)
    assert res.get("ok") is True
    assert any("kb-ask-budget" in p for p in calls)


def test_budget_bridge_unavailable_deny_reply_does_not_urge_retry():
    from backend.services.kb_ask_mcp_reply import orientg_kb_ask_denied_hermes_reply

    text = orientg_kb_ask_denied_hermes_reply("orientg_kb_ask budget bridge unavailable")
    assert "权限" not in text or "勿" in text
    assert "勿再重复调用" in text or "勿重试" in text or "基础设施" in text
    assert "请改用 MCP 工具" not in text


def test_production_bridge_rejects_non_private_client(client, monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "orientg_mcp_bridge_secret", BRIDGE_SECRET)
    # TestClient 默认 client host 为 testclient；生产应拒绝非 loopback/私网
    from backend.routers import internal_hermes as ih

    monkeypatch.setattr(ih, "_is_loopback_or_private", lambda _h: False)
    r = client.post(
        "/api/internal/hermes/session/resolve",
        headers=_headers(),
        json={"hermes_session_key": "orientg-x"},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "bridge_client_forbidden"
