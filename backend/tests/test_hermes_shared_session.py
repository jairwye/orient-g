"""Hermes 会话 PostgreSQL 共享存储（跨 worker / MCP HTTP 桥）。"""

import time

import jwt
import pytest

from backend.config import settings
from backend.database import init_hermes_session_store_table
from backend.services import hermes_session_context as session_ctx
from backend.services import hermes_token_bridge as bridge
from backend.services import kb_ask_budget as budget
from backend.services import hermes_shared_session as shared
from backend.services import orientg_mcp_tools as tools


@pytest.fixture(autouse=True)
def _reset_all():
    init_hermes_session_store_table()
    bridge.reset_for_tests()
    session_ctx.reset_for_tests()
    budget.reset_for_tests()
    shared.reset_for_tests()
    yield
    bridge.reset_for_tests()
    session_ctx.reset_for_tests()
    budget.reset_for_tests()
    shared.reset_for_tests()


def _jwt(sub: str = "finance_test") -> str:
    return jwt.encode(
        {"sub": sub, "iat": int(time.time()), "exp": int(time.time()) + 3600},
        settings.auth_secret,
        algorithm="HS256",
    )


def test_persist_and_load_across_fresh_memory():
    tok = _jwt()
    sk = bridge.register("orientg-shared-1", tok, ttl_seconds=3600)
    session_ctx.register(
        sk,
        kb_scope={"selected_folder_ids": ["f_competitor"]},
        orientg_route="hermes_full",
    )
    budget.register_session_kb_budget(sk, max_calls=3)
    shared.persist_session(
        sk,
        tok,
        kb_scope={"selected_folder_ids": ["f_competitor"]},
        orientg_route="hermes_full",
        kb_budget_max=3,
    )

    bridge.reset_for_tests()
    session_ctx.reset_for_tests()
    budget.reset_for_tests()

    loaded = shared.load_session(sk)
    assert loaded is not None
    assert loaded["user_token"] == tok
    assert loaded["kb_scope"]["selected_folder_ids"] == ["f_competitor"]
    assert loaded["orientg_route"] == "hermes_full"
    assert loaded["kb_budget_max"] == 3


def test_persist_seals_jwt_at_rest():
    """DB 行不得明文存 JWT；load 仍可还原。"""
    from sqlalchemy import text

    from backend.database import engine

    tok = _jwt()
    sk = "orientg-sealed-jwt"
    shared.persist_session(sk, tok, kb_scope={"selected_folder_ids": ["f1"]})
    with engine.connect() as conn:
        raw = conn.execute(
            text("SELECT user_token FROM hermes_session_store WHERE session_key = :k"),
            {"k": sk},
        ).scalar()
    assert raw and str(raw).startswith("v1:")
    assert tok not in str(raw)
    loaded = shared.load_session(sk)
    assert loaded is not None
    assert loaded["user_token"] == tok


def test_unseal_accepts_legacy_plaintext_rows():
    from sqlalchemy import text

    from backend.database import engine, init_hermes_session_store_table

    init_hermes_session_store_table()
    tok = _jwt()
    sk = "orientg-legacy-plain"
    with engine.connect() as conn:
        conn.execute(
            text(
                """
                INSERT INTO hermes_session_store (
                    session_key, user_token, kb_scope_json, allow_kb_write, expires_at
                ) VALUES (
                    :k, :t, '{}', false, NOW() + INTERVAL '1 hour'
                )
                ON CONFLICT (session_key) DO UPDATE SET user_token = EXCLUDED.user_token
                """
            ),
            {"k": sk, "t": tok},
        )
        conn.commit()
    loaded = shared.load_session(sk)
    assert loaded is not None
    assert loaded["user_token"] == tok


def test_resolve_user_token_from_db_when_memory_empty(monkeypatch):
    tok = _jwt()
    sk = bridge.register("orientg-shared-2", tok)
    session_ctx.register(sk, kb_scope={"selected_folder_ids": ["f1"]})
    shared.persist_session(sk, tok, kb_scope={"selected_folder_ids": ["f1"]})

    bridge.reset_for_tests()
    session_ctx.reset_for_tests()

    monkeypatch.setenv("ORIENTG_INTERNAL_BASE_URL", "")
    resolved = tools.resolve_user_token("", hermes_session_key=sk)
    assert resolved == tok


def test_db_hydrate_native_mcp_reply_follows_settings(monkeypatch):
    """多 worker：内存 ctx 清空后从 DB hydrate，不得把 native_mcp_reply 静默压成 False。"""
    from backend.config import settings

    monkeypatch.setattr(settings, "hermes_native_mcp_reply", True)
    tok = _jwt()
    sk = "orientg-native-hydrate"
    shared.persist_session(
        sk,
        tok,
        kb_scope={"selected_folder_ids": ["f1"]},
        native_mcp_reply=True,
    )
    session_ctx.reset_for_tests()
    loaded = shared.load_session(sk)
    assert loaded is not None
    assert loaded.get("native_mcp_reply") is True
    assert "__orientg_native_mcp_reply" not in (loaded.get("kb_scope") or {})
    ctx = session_ctx.resolve(sk)
    assert ctx is not None
    assert ctx.native_mcp_reply is True


def test_db_hydrate_native_mcp_reply_missing_field_falls_back_to_settings(monkeypatch):
    """旧行无 native 字段时回退 settings，避免覆盖 settings.hermes_native_mcp_reply。"""
    from sqlalchemy import text

    from backend.config import settings
    from backend.database import engine, init_hermes_session_store_table

    monkeypatch.setattr(settings, "hermes_native_mcp_reply", True)
    init_hermes_session_store_table()
    tok = _jwt()
    sk = "orientg-native-legacy"
    with engine.connect() as conn:
        conn.execute(
            text(
                """
                INSERT INTO hermes_session_store (
                    session_key, user_token, kb_scope_json, allow_kb_write, expires_at
                ) VALUES (
                    :k, :t, '{"selected_folder_ids":["f1"]}', false, NOW() + INTERVAL '1 hour'
                )
                ON CONFLICT (session_key) DO UPDATE SET
                    user_token = EXCLUDED.user_token,
                    kb_scope_json = EXCLUDED.kb_scope_json
                """
            ),
            {"k": sk, "t": tok},
        )
        conn.commit()
    session_ctx.reset_for_tests()
    ctx = session_ctx.resolve(sk)
    assert ctx is not None
    assert ctx.native_mcp_reply is True


def test_orientg_kb_ask_inherits_kb_scope_from_db(monkeypatch):
    tok = _jwt()
    sk = bridge.register("orientg-shared-3", tok)
    session_ctx.register(sk, kb_scope={"selected_folder_ids": ["folder_x"]})
    shared.persist_session(sk, tok, kb_scope={"selected_folder_ids": ["folder_x"]})

    bridge.reset_for_tests()
    session_ctx.reset_for_tests()

    captured: dict = {}

    def fake_ask_knowledge(token, query, **kwargs):
        captured.update({"token": token, **kwargs})
        return {"denied": False, "reply": "ok", "citations": [{"doc_id": "d1"}]}

    def fake_resolve_scope(tenant_id, kb_scope, **kwargs):
        return {
            "collection_ids": [],
            "table_ids": [],
            "attached_doc_ids": ["ud_x"],
            "limit_to_attached": True,
        }

    monkeypatch.setattr(tools, "ask_knowledge", fake_ask_knowledge)
    monkeypatch.setattr(
        "backend.services.kb_scope_resolve.resolve_kb_scope_for_ask",
        fake_resolve_scope,
    )

    res = tools.orientg_kb_ask("", "人员结构", hermes_session_key=sk)
    assert res.get("ok") is True
    assert captured.get("token") == tok
    assert captured.get("limit_to_attached") is True
