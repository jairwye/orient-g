"""HERMES_DEV_MOCK：无 Hermes 时 /agent 直接调 MCP。"""

import time
import uuid

import jwt
import pytest
from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app
from backend.routers.settings import DEPARTMENT_FINANCE
from backend.services.dev_users import ensure_department_test_user

client = TestClient(app)
FINANCE_TEST_PASSWORD = "FinanceTest!2026"


def test_agent_dev_mock_calls_mcp(monkeypatch):
    username = f"finance_mock_{uuid.uuid4().hex[:8]}"
    ensure_department_test_user(username, password=FINANCE_TEST_PASSWORD, department=DEPARTMENT_FINANCE)
    login = client.post("/api/auth/login", json={"username": username, "password": FINANCE_TEST_PASSWORD})
    assert login.status_code == 200
    token = login.json()["token"]

    monkeypatch.setattr(settings, "hermes_enabled", False)
    monkeypatch.setattr(settings, "hermes_base_url", None)
    monkeypatch.setattr(settings, "hermes_dev_mock", True)
    monkeypatch.setattr(
        "backend.services.orientg_mcp_tools.ask_knowledge",
        lambda *a, **k: {"denied": False, "reply": "mock-rag", "citations": []},
    )
    monkeypatch.setattr(
        "backend.services.orientg_mcp_tools.orientg_kb_list_docs",
        lambda *a, **k: {"ok": True, "items": []},
    )

    r = client.post(
        "/api/agent/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"messages": [{"role": "user", "content": "查制度"}]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("dev_mock") is True
    assert "mock-rag" in (body.get("reply") or "")
    assert len(body.get("tool_calls") or []) >= 1
