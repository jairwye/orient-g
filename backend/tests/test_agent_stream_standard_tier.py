"""标准模式 + 竞品文件夹：流式 done 须为 Tier 1（非误升 Tier 2）。"""

from __future__ import annotations

import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app
from backend.routers.settings import DEPARTMENT_FINANCE
from backend.services.dev_users import ensure_department_test_user
from backend.tests.test_acl_folder_shared_docs import FOLDER_JINGPIN_CAIBAO_25

QUERY = "出一份华清25、24两年研发费用明细的对比分析报告"
client = TestClient(app)


def _finance_token() -> str:
    ensure_department_test_user(
        "finance_test",
        password="FinanceTest!2026",
        department=DEPARTMENT_FINANCE,
    )
    r = client.post(
        "/api/auth/login",
        json={"username": "finance_test", "password": "FinanceTest!2026"},
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


def test_standard_mode_stream_done_is_tier1_not_tier2(monkeypatch):
    monkeypatch.setattr(settings, "hermes_enabled", True)
    monkeypatch.setattr(settings, "hermes_base_url", "http://127.0.0.1:8642")
    monkeypatch.setattr(settings, "hermes_dev_mock", False)
    monkeypatch.setattr(settings, "hermes_agent_kb_prefetch", True)

    def _fake_stream(**kwargs):
        assert kwargs.get("orientg_route") == "hermes_lite", kwargs.get("orientg_route")
        yield {"type": "status", "message": "mock", "step": "connect"}
        yield {
            "type": "done",
            "reply": "结论：研发费用对比（mock）",
            "tool_calls": [],
            "hermes_stream_stats": {"orientg_kb_ask_calls": 0},
        }

    monkeypatch.setattr("backend.services.hermes_client.stream_agent_chat", _fake_stream)

    token = _finance_token()
    r = client.post(
        "/api/agent/chat/stream",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "messages": [{"role": "user", "content": QUERY}],
            "kb_scope": {"selected_folder_ids": [FOLDER_JINGPIN_CAIBAO_25]},
            "allow_kb_write": False,
            "agent_mode": "standard",
        },
    )
    assert r.status_code == 200, r.text
    done = None
    for block in r.text.split("\n\n"):
        for line in block.split("\n"):
            if not line.strip().startswith("data:"):
                continue
            raw = line.strip()[5:].strip()
            if not raw or raw == "[DONE]":
                continue
            evt = json.loads(raw)
            if evt.get("type") == "done":
                done = evt
    assert done is not None
    assert done.get("agent_route") == "hermes_lite"
    assert done.get("agent_tier") == 1
