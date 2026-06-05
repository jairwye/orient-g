"""Tier 2 终稿不得被 Orient-G 网关追加段落（仅 Hermes 原生 + 过程稿剥离）。"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app
from backend.routers.settings import DEPARTMENT_FINANCE
from backend.services.dev_users import ensure_department_test_user
from backend.tests.test_acl_folder_shared_docs import FOLDER_JINGPIN_CAIBAO_25

QUERY = "出一份华清25、24两年销售费用明细的对比分析报告"
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


def test_tier2_done_never_gateway_append(monkeypatch):
    monkeypatch.setattr(settings, "hermes_enabled", True)
    monkeypatch.setattr(settings, "hermes_base_url", "http://127.0.0.1:8642")
    monkeypatch.setattr(settings, "hermes_dev_mock", False)
    monkeypatch.setattr(settings, "hermes_agent_kb_prefetch", True)

    hermes_reply = (
        "# 华清销售费用对比\n\n"
        "| 项目 | 2025 | 2024 |\n|---|---|---|\n"
        "| 合计 | 13,722,360.23 | 25,081,092.51 |\n"
    )

    def _fake_hermes_stream(**kwargs):
        yield {"type": "status", "message": "mock", "step": "connect"}
        yield {
            "type": "done",
            "reply": hermes_reply,
            "hermes_session_id": "s1",
            "tool_calls": [],
            "hermes_stream_stats": {"orientg_kb_ask_calls": 0},
        }

    monkeypatch.setattr("backend.routers.agent.stream_agent_chat", _fake_hermes_stream)

    r = client.post(
        "/api/agent/chat/stream",
        headers={"Authorization": f"Bearer {_finance_token()}"},
        json={
            "messages": [{"role": "user", "content": QUERY}],
            "kb_scope": {"selected_folder_ids": [FOLDER_JINGPIN_CAIBAO_25]},
            "agent_mode": "deep",
        },
    )
    assert r.status_code == 200, r.text
    done = {}
    for block in r.text.split("\n\n"):
        for line in block.split("\n"):
            if not line.strip().startswith("data:"):
                continue
            raw = line.strip()[5:].strip()
            if not raw or raw == "[DONE]":
                continue
            try:
                evt = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if evt.get("type") == "done":
                done = evt
    assert done.get("agent_tier") == 2
    reply = str(done.get("reply") or "")
    assert "补充检索（Orient-G 网关）" not in reply
    assert done.get("supplemental_mode") != "tier2_gap_append"
    assert "13,722,360.23" in reply
    # Hermes 仅给总额时，网关可 kb_supplemental 修订分项（非 tier2_gap_append）
    if done.get("kb_supplemental"):
        assert "证据中未提供可核查的分项" not in reply
