"""Agent API：Hermes 开关与网关。"""

import time

import jwt
import pytest
from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app


def _token(sub: str = "admin") -> str:
    payload = {"sub": sub, "iat": int(time.time()), "exp": int(time.time()) + 3600}
    return jwt.encode(payload, settings.auth_secret, algorithm="HS256")


@pytest.fixture
def client():
    return TestClient(app)


def test_agent_status(client):
    r = client.get("/api/agent/status")
    assert r.status_code == 200
    data = r.json()
    assert "hermes_enabled" in data


def test_agent_chat_503_when_hermes_disabled_and_no_llm(client, monkeypatch):
    monkeypatch.setattr(settings, "hermes_enabled", False)
    monkeypatch.setattr(settings, "hermes_base_url", None)
    monkeypatch.setattr(settings, "hermes_dev_mock", False)
    monkeypatch.setattr(settings, "llm_base_url", None)
    monkeypatch.setattr(settings, "llm_model", None)
    monkeypatch.setattr(settings, "ollama_url", None)

    r = client.post(
        "/api/agent/chat",
        headers={"Authorization": f"Bearer {_token()}"},
        json={"messages": [{"role": "user", "content": "你好"}]},
    )
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "hermes_disabled"


def test_agent_chat_local_llm_when_hermes_disabled(client, monkeypatch):
    monkeypatch.setattr(settings, "hermes_enabled", False)
    monkeypatch.setattr(settings, "hermes_base_url", None)
    monkeypatch.setattr(settings, "hermes_dev_mock", False)
    monkeypatch.setattr(settings, "llm_base_url", "http://llm.test/v1")
    monkeypatch.setattr(settings, "llm_model", "test-model")
    monkeypatch.setattr(
        "backend.services.ai_interaction_llm.generate_chat_reply",
        lambda **k: "本地 LLM 回复",
    )

    r = client.post(
        "/api/agent/chat",
        headers={"Authorization": f"Bearer {_token()}"},
        json={"messages": [{"role": "user", "content": "你好"}]},
    )
    assert r.status_code == 200
    assert r.json().get("synthesis") == "local_llm"
    assert r.json().get("hermes_used") is False


def test_agent_chat_forwards_to_hermes(client, monkeypatch):
    monkeypatch.setattr(settings, "hermes_enabled", True)
    monkeypatch.setattr(settings, "hermes_base_url", "http://hermes-agent:8787")
    monkeypatch.setattr(
        "backend.routers.agent.run_agent_chat",
        lambda **k: {
            "reply": "hermes-ok",
            "tool_calls": [{"name": "orientg_kb_ask", "status": "ok"}],
            "hermes_session_id": "h_sess_1",
            "artifacts": [],
        },
    )

    r = client.post(
        "/api/agent/chat",
        headers={"Authorization": f"Bearer {_token()}"},
        json={
            "messages": [{"role": "user", "content": "整理合同台账"}],
            "allow_kb_write": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["reply"] == "hermes-ok"
    assert body["hermes_session_id"] == "h_sess_1"
    assert len(body["tool_calls"]) == 1
