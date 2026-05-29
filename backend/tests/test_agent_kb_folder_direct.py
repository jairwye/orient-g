"""Agent：选文件夹时应走直接读文档（与 AI 互动一致）。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app
from backend.routers.settings import DEPARTMENT_FINANCE
from backend.services.dev_users import ensure_department_test_user

client = TestClient(app)
FINANCE_TEST_PASSWORD = "FinanceTest!2026"
FINANCE_USER = "finance_test"


def _token() -> str:
    ensure_department_test_user(FINANCE_USER, password=FINANCE_TEST_PASSWORD, department=DEPARTMENT_FINANCE)
    r = client.post("/api/auth/login", json={"username": FINANCE_USER, "password": FINANCE_TEST_PASSWORD})
    assert r.status_code == 200
    return r.json()["token"]


def test_agent_folder_scope_uses_direct_read(monkeypatch):
    token = _token()
    monkeypatch.setattr(settings, "hermes_enabled", True)
    monkeypatch.setattr(settings, "hermes_base_url", "http://127.0.0.1:8642")
    monkeypatch.setattr(settings, "hermes_dev_mock", False)
    monkeypatch.setattr(settings, "hermes_agent_kb_prefetch", True)
    monkeypatch.setattr(settings, "hermes_agent_kb_synthesize", False)
    monkeypatch.setattr(settings, "llm_base_url", "http://llm.test/v1")
    monkeypatch.setattr(settings, "llm_model", "test-model")

    captured: dict = {}

    def _local(**kwargs):
        captured.update(kwargs)
        return {
            "ok": True,
            "reply": "损益对比表（直接读）",
            "citations": [],
            "synthesis": "direct_read",
            "llm_model": "test-model",
            "tool_calls": [{"name": "kb_direct_read", "status": "ok"}],
        }

    monkeypatch.setattr("backend.services.agent_kb_local.run_agent_kb_local_answer", _local)

    r = client.post(
        "/api/agent/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "messages": [{"role": "user", "content": "做华清25与24年损益对比表"}],
            "kb_scope": {"selected_folder_ids": ["f_finance_public"]},
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("synthesis") == "direct_read"
    assert "直接读" in (body.get("reply") or "")
    assert captured.get("kb_scope_payload", {}).get("selected_folder_ids") == ["f_finance_public"]
