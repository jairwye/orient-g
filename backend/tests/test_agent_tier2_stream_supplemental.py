"""Tier 2 流式路径：supplemental 须在 finalize 之前（避免误报「证据无分项」）。"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app
from backend.routers.settings import DEPARTMENT_FINANCE
from backend.services.dev_users import ensure_department_test_user
from backend.tests.test_acl_folder_shared_docs import FOLDER_JINGPIN_CAIBAO_25

QUERY = "出一份华清25、24两年销售费用明细的对比分析报告"
client = TestClient(app)

PREFETCH_WITH_FACETS = {
    "ok": True,
    "reply": "预检索摘要",
    "citations": [{"doc_id": "ud_0401544fb6f7425092db1d9f7a970917", "chunk_id": "c1"}],
    "evidence_pack": {
        "task_type": "breakdown",
        "coverage_score": 1.0,
        "gaps": [],
        "facets": [
            {
                "label": "销售费用附注",
                "excerpt": "职工薪酬 10,802,366.11 市场及推广 2,889,547.75 销售费用合计 13,722,360.23",
            }
        ],
    },
}

HERMES_LAZY = (
    "### 华清销售费用对比\n\n"
    "| 项目 | 2025 | 2024 |\n| --- | --- | --- |\n"
    "| 销售费用 | 13,722,360.23 | 25,081,092.51 |\n\n"
    "#### 2. 费用变动分析\n\n"
    "* 人员薪酬减少约 500-600 万元。\n"
)

SYNTH_GOOD = (
    "结论：2025年销售费用 13,722,360.23 元。\n"
    "| 项目 | 2025 | 2024 |\n| --- | --- | --- |\n"
    "| 职工薪酬 | 10,802,366.11 | 23,295,127.31 |\n"
    "| 市场及推广 | 2,889,547.75 | 1,526,703.85 |\n"
)


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


def test_tier2_stream_supplemental_before_finalize_not_false_gap(monkeypatch):
    monkeypatch.setattr(settings, "hermes_enabled", True)
    monkeypatch.setattr(settings, "hermes_base_url", "http://127.0.0.1:8642")
    monkeypatch.setattr(settings, "hermes_dev_mock", False)
    monkeypatch.setattr(settings, "hermes_agent_kb_prefetch", True)

    def _fake_hermes_stream(**kwargs):
        yield {"type": "status", "message": "mock", "step": "connect"}
        yield {
            "type": "done",
            "reply": HERMES_LAZY,
            "tool_calls": [],
            "hermes_stream_stats": {"orientg_kb_ask_calls": 0},
        }

    monkeypatch.setattr("backend.routers.agent.prefetch_kb_context", lambda *a, **k: (
        [{"role": "user", "content": QUERY}],
        PREFETCH_WITH_FACETS,
        [{"name": "orientg_kb_ask", "prefetch": True, "status": "ok"}],
    ))
    monkeypatch.setattr("backend.routers.agent.stream_agent_chat", _fake_hermes_stream)

    with patch(
        "backend.services.agent_kb_prefetch.synthesize_kb_reply",
        return_value={"reply": SYNTH_GOOD, "citations": [], "synthesis": "mock_synth"},
    ), patch(
        "backend.services.agent_kb_supplemental.run_supplemental_kb_asks",
        return_value=(PREFETCH_WITH_FACETS, []),
    ):
        r = client.post(
            "/api/agent/chat/stream",
            headers={"Authorization": f"Bearer {_finance_token()}"},
            json={
                "messages": [{"role": "user", "content": QUERY}],
                "kb_scope": {"selected_folder_ids": [FOLDER_JINGPIN_CAIBAO_25]},
                "agent_mode": "deep",
            },
        )
    assert r.status_code == 200, r.text[:500]
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
    reply = str(done.get("reply") or "")
    assert done.get("kb_supplemental") is True
    assert "证据中未提供可核查的分项" not in reply
    assert "10,802,366.11" in reply
    assert "500-600" not in reply
