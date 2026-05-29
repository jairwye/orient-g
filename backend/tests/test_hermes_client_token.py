"""hermes_client：登记 JWT、X-Hermes-Session-Key、system 上下文。"""

import json
import time
from unittest.mock import MagicMock, patch

import jwt
import pytest

from backend.config import settings
from backend.services import hermes_token_bridge as bridge
from backend.services.hermes_client import run_agent_chat


def _jwt(sub: str = "bob") -> str:
    return jwt.encode(
        {"sub": sub, "iat": int(time.time()), "exp": int(time.time()) + 3600},
        settings.auth_secret,
        algorithm="HS256",
    )


@pytest.fixture(autouse=True)
def _clear_bridge():
    bridge.reset_for_tests()
    yield
    bridge.reset_for_tests()


def test_run_agent_chat_registers_token_and_sends_session_key_header(monkeypatch):
    monkeypatch.setattr(settings, "hermes_enabled", True)
    monkeypatch.setattr(settings, "hermes_base_url", "http://127.0.0.1:8642")
    monkeypatch.setattr(settings, "hermes_internal_token", "svc-key")
    monkeypatch.setattr(settings, "hermes_model", "hermes-agent")

    captured: dict = {}

    class FakeResp:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": "ok", "tool_calls": []}}]}

    def fake_post(url, json=None, headers=None, **kwargs):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return FakeResp()

    tok = _jwt()
    with patch("httpx.Client") as client_cls:
        client_cls.return_value.__enter__.return_value.post = fake_post
        run_agent_chat(
            messages=[{"role": "user", "content": "hi"}],
            username="bob",
            user_token=tok,
            hermes_session_id="sess-abc",
        )

    assert captured["headers"]["Authorization"] == "Bearer svc-key"
    sk = captured["headers"]["X-Hermes-Session-Key"]
    assert sk == "orientg-sess-abc"
    assert bridge.resolve(sk) == tok

    messages = captured["json"]["messages"]
    system = messages[0]
    assert system["role"] == "system"
    ctx = json.loads(system["content"].split("\n", 1)[1])
    assert ctx["orientg_hermes_session_key"] == sk
    assert ctx["orientg_username"] == "bob"
    assert "hermes_session_key" in (ctx.get("orientg_mcp_instruction") or "")


def test_build_messages_includes_mcp_instruction():
    from backend.services.hermes_client import _build_messages

    msgs = _build_messages(
        [{"role": "user", "content": "q"}],
        username="u1",
        kb_scope={},
        allow_kb_write=True,
        attached_doc_ids=[],
        hermes_session_id="s1",
        orientg_hermes_session_key="orientg-s1",
    )
    ctx = json.loads(msgs[0]["content"].split("\n", 1)[1])
    assert ctx["orientg_hermes_session_key"] == "orientg-s1"
