"""Agent allow_kb_write 仅深度模式生效。"""

import time

import jwt
from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app
from backend.routers.agent import AgentChatBody, _effective_allow_kb_write


def _token(sub: str = "admin") -> str:
    payload = {"sub": sub, "iat": int(time.time()), "exp": int(time.time()) + 3600}
    return jwt.encode(payload, settings.auth_secret, algorithm="HS256")


def test_effective_allow_kb_write_deep_only():
    assert not _effective_allow_kb_write(
        AgentChatBody(messages=[{"role": "user", "content": "x"}], allow_kb_write=True, agent_mode="standard")
    )
    assert _effective_allow_kb_write(
        AgentChatBody(messages=[{"role": "user", "content": "x"}], allow_kb_write=True, agent_mode="deep")
    )
    assert not _effective_allow_kb_write(
        AgentChatBody(messages=[{"role": "user", "content": "x"}], allow_kb_write=False, agent_mode="deep")
    )


def test_stream_requires_run_id_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "agent_require_run_id", True)
    client = TestClient(app)
    r = client.post(
        "/api/agent/chat/stream",
        headers={"Authorization": f"Bearer {_token()}"},
        json={
            "messages": [{"role": "user", "content": "查费用"}],
            "kb_scope": {"selected_folder_ids": ["f1"]},
            "agent_mode": "standard",
        },
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "agent_run_id_required"
