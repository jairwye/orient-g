"""HERMES_* 环境变量加载与诊断。"""

import os

import pytest

from backend.config import Settings
from backend.services.hermes_settings import diagnose_hermes


def test_settings_loads_hermes_from_env(monkeypatch):
    monkeypatch.setenv("HERMES_ENABLED", "true")
    monkeypatch.setenv("HERMES_BASE_URL", "http://hermes-agent:8642")
    monkeypatch.setenv("HERMES_DEV_MOCK", "false")
    s = Settings()
    assert s.hermes_enabled is True
    assert s.hermes_base_url == "http://hermes-agent:8642"
    assert s.hermes_configured is True


def test_diagnose_missing_base_url(monkeypatch):
    monkeypatch.setenv("HERMES_ENABLED", "true")
    monkeypatch.delenv("HERMES_BASE_URL", raising=False)
    # 显式传入，避免项目根 .env 中的 HERMES_BASE_URL 被加载
    fresh = Settings(hermes_enabled=True, hermes_base_url=None, hermes_dev_mock=False)
    monkeypatch.setattr("backend.services.hermes_settings.settings", fresh)
    d = diagnose_hermes()
    assert d["hermes_enabled"] is True
    assert d["hermes_configured"] is False
    assert "HERMES_BASE_URL" in str(d["missing"]) or "HERMES_BASE_URL" in " ".join(d["hints"])


def test_diagnose_dev_mock_active(monkeypatch):
    monkeypatch.setenv("HERMES_ENABLED", "false")
    monkeypatch.setenv("HERMES_DEV_MOCK", "true")
    monkeypatch.delenv("HERMES_BASE_URL", raising=False)
    fresh = Settings(hermes_enabled=False, hermes_dev_mock=True, hermes_base_url=None)
    monkeypatch.setattr("backend.services.hermes_settings.settings", fresh)
    d = diagnose_hermes()
    assert d["hermes_dev_mock_active"] is True
    assert d["ready_for_agent_chat"] is True


def test_agent_status_includes_diagnosis(monkeypatch):
    from fastapi.testclient import TestClient

    from backend.main import app

    monkeypatch.setenv("HERMES_ENABLED", "true")
    monkeypatch.setenv("HERMES_BASE_URL", "http://hermes-agent:8642")
    fresh = Settings()
    monkeypatch.setattr("backend.services.hermes_settings.settings", fresh)
    monkeypatch.setattr("backend.routers.agent.settings", fresh)

    c = TestClient(app)
    r = c.get("/api/agent/status")
    assert r.status_code == 200
    body = r.json()
    assert body["hermes_configured"] is True
    assert body.get("ready_for_agent_chat") is True
    assert "hints" in body
