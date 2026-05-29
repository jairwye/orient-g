"""MCP 工具：hermes_session_key 从 bridge 解析 JWT。"""

import time

import jwt
import pytest

from backend.config import settings
from backend.services import hermes_token_bridge as bridge
from backend.services import orientg_mcp_tools as tools


@pytest.fixture(autouse=True)
def _clear_bridge():
    bridge.reset_for_tests()
    yield
    bridge.reset_for_tests()


def test_orientg_kb_ask_resolves_token_from_session_key(monkeypatch):
    tok = jwt.encode(
        {"sub": "finance_test", "iat": int(time.time()), "exp": int(time.time()) + 3600},
        settings.auth_secret,
        algorithm="HS256",
    )
    sk = bridge.register("orientg-t1", tok)

    monkeypatch.setattr(
        tools,
        "ask_knowledge",
        lambda *a, **k: {"denied": False, "reply": "ok", "citations": []},
    )

    res = tools.orientg_kb_ask("", "q", hermes_session_key=sk)
    assert res.get("ok") is True or res.get("denied") is False
