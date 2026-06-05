"""财务账号 + 竞品财报25 文件夹：Agent 流式应能完成华清损益对比。"""

from __future__ import annotations

import json

import jwt
import time
import pytest
from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app
from backend.routers.settings import DEPARTMENT_FINANCE
from backend.services.dev_users import ensure_department_test_user
from backend.tests.test_acl_folder_shared_docs import FOLDER_JINGPIN_CAIBAO_25

# 竞品财报25 文件夹内：华清年报主文档（目录为主）与含损益表 chunk 的解析文档
HUAQING_PL_DOC = "ud_91f55322e2594b9c9d3ba7ceb89fafb2"  # 合并利润表（默认口径）
HUAQING_PARENT_PL_DOC = "ud_67d0f860dbbb4196861d5ab97b472584"

client = TestClient(app)
QUERY = "做一张华清25和24年损益对比的表，仅依据知识库证据，缺项请说明。"


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


def test_agent_stream_folder_jingpin_huaqing(monkeypatch):
    """流式 + 预检索 + 标准模式：标准固定 Tier 1（Hermes lite）；快速/auto 可 Tier 0。"""
    monkeypatch.setattr(settings, "hermes_enabled", True)
    monkeypatch.setattr(settings, "hermes_base_url", "http://127.0.0.1:8642")
    monkeypatch.setattr(settings, "hermes_dev_mock", False)
    monkeypatch.setattr(settings, "hermes_agent_kb_prefetch", True)
    monkeypatch.setattr(settings, "hermes_agent_kb_fast_path", False)
    monkeypatch.setattr(settings, "hermes_agent_simple_query_fast", True)

    def _fake_hermes_stream(**kwargs):
        yield {"type": "status", "message": "mock hermes", "step": "connect"}
        yield {
            "type": "done",
            "reply": (
                "## 华清损益对比（测试桩）\n\n"
                "| 项目 | 2025年 | 2024年 |\n|---|---|---|\n"
                "| 营业收入 | 100,148,026.24 | 138,539,446.45 |\n"
            ),
            "hermes_session_id": "test_session",
            "tool_calls": [{"name": "orientg_kb_ask", "status": "ok"}],
        }

    monkeypatch.setattr(
        "backend.services.hermes_client.stream_agent_chat",
        _fake_hermes_stream,
    )

    def _fake_prefetch(_token, msgs, _scope, **kwargs):
        cites = [
            {"doc_id": HUAQING_PL_DOC, "chunk_id": "c_pl", "score": 0.9},
            {"doc_id": HUAQING_PARENT_PL_DOC, "chunk_id": "c_parent", "score": 0.5},
        ]
        prefetch = {
            "ok": True,
            "citations": cites,
            "reply": "预检索桩",
            "evidence_pack": {
                "task_type": "compare",
                "coverage_score": 0.9,
                "gaps": [],
                "facets": [{"keywords_hit": ["营业收入", "合并利润表"]}],
                "retrieval_queries": [QUERY],
            },
        }
        tool_calls = [{"name": "orientg_kb_ask", "status": "ok", "result": prefetch}]
        return msgs, prefetch, tool_calls

    monkeypatch.setattr(
        "backend.services.agent_kb_prefetch.prefetch_kb_context",
        _fake_prefetch,
    )

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
    body = r.text
    assert "agent_tier" in body
    assert '"agent_tier": 1' in body or '"agent_tier": 0' in body or "kb_fast_path" in body
    done = {}
    for block in body.split("\n\n"):
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
    assert done.get("agent_route") in ("fast", "hermes_lite")
    assert done.get("agent_tier") in (0, 1)
    reply = (done.get("reply") or "").strip()
    assert "100,148" in reply or "损益" in reply, reply[:500]
    assert "timed out" not in reply.lower()


@pytest.mark.integration
def test_live_agent_folder_jingpin_huaqing():
    import httpx

    try:
        httpx.get("http://127.0.0.1:8000/api/agent/status", timeout=5).raise_for_status()
    except Exception as e:
        pytest.skip(f"backend not up: {e}")

    token = _finance_token()
    r = client.post(
        "/api/agent/chat/stream",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "messages": [{"role": "user", "content": QUERY}],
            "kb_scope": {"selected_folder_ids": [FOLDER_JINGPIN_CAIBAO_25]},
            "allow_kb_write": False,
        },
    )
    assert r.status_code == 200, r.text
    assert HUAQING_PL_DOC in r.text or "56,071" in r.text or "798" in r.text
