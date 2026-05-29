"""Hermes 会话内 orientg_kb_ask 次数预算（MCP 硬约束）。"""

from __future__ import annotations

import time

import jwt
import pytest

from backend.config import settings
from backend.services import hermes_token_bridge as bridge
from backend.services import kb_ask_budget as budget
from backend.services import orientg_mcp_tools as tools


@pytest.fixture(autouse=True)
def _reset():
    bridge.reset_for_tests()
    budget.reset_for_tests()
    yield
    bridge.reset_for_tests()
    budget.reset_for_tests()


def _token() -> str:
    return jwt.encode(
        {"sub": "finance_test", "iat": int(time.time()), "exp": int(time.time()) + 3600},
        settings.auth_secret,
        algorithm="HS256",
    )


def test_budget_allows_up_to_max_calls():
    sk = bridge.register("orientg-b1", _token())
    budget.register_session_kb_budget(sk, 2)
    assert budget.check_and_consume_ask(sk) is None
    assert budget.check_and_consume_ask(sk) is None
    reason = budget.check_and_consume_ask(sk)
    assert reason and "budget" in reason.lower()


def test_unlimited_when_max_is_none():
    sk = bridge.register("orientg-b2", _token())
    budget.register_session_kb_budget(sk, None)
    for _ in range(5):
        assert budget.check_and_consume_ask(sk) is None


def test_orientg_kb_ask_denied_when_budget_exhausted(monkeypatch):
    sk = bridge.register("orientg-b3", _token())
    budget.register_session_kb_budget(sk, 1)
    monkeypatch.setattr(
        tools,
        "ask_knowledge",
        lambda *a, **k: {"denied": False, "reply": "ok", "citations": []},
    )
    r1 = tools.orientg_kb_ask("", "q1", hermes_session_key=sk)
    assert r1.get("ok") is True
    r2 = tools.orientg_kb_ask("", "q2", hermes_session_key=sk)
    assert r2.get("denied") is True
    assert "budget" in (r2.get("reason") or "").lower()
