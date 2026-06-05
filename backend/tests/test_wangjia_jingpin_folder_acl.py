"""wangjia + 竞品财报25：ACL 与 Agent 预检索（TDD，不依赖 live Hermes）。"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app
from backend.routers.settings import DEPARTMENT_FINANCE
from backend.services.dev_users import ensure_department_test_user
from backend.services.kb_folders import collect_subtree_doc_ids
from backend.services.knowledge_acl import compute_acl_scope, load_fixtures
from backend.services.knowledge_pipeline import ask_knowledge
from backend.services.kb_scope_resolve import resolve_kb_scope_for_ask
from backend.tests.test_acl_folder_shared_docs import (
    FOLDER_JINGPIN_CAIBAO_25,
    HUAQING_DOC_IN_FOLDER,
)

WANGJIA_PASSWORD = "WangjiaTest!2026"
QUERY = "出一份华清25、24两年销售费用明细的对比分析报告"

client = TestClient(app)


def _ensure_wangjia() -> None:
    ensure_department_test_user(
        "wangjia",
        password=WANGJIA_PASSWORD,
        department=DEPARTMENT_FINANCE,
        roles=["admin"],
        is_department_lead=True,
    )


def _wangjia_token() -> str:
    _ensure_wangjia()
    r = client.post(
        "/api/auth/login",
        json={"username": "wangjia", "password": WANGJIA_PASSWORD},
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


def test_wangjia_acl_covers_entire_jingpin_folder_subtree():
    token = _wangjia_token()
    fixtures = load_fixtures()
    scope = compute_acl_scope(token, fixtures=fixtures)
    allowed = set(scope.get("allowed_doc_ids") or [])
    subtree = set(collect_subtree_doc_ids("tenant1", FOLDER_JINGPIN_CAIBAO_25))
    assert len(subtree) > 50
    assert HUAQING_DOC_IN_FOLDER in subtree
    missing = subtree - allowed
    assert not missing, f"ACL missing {len(missing)} docs, sample={list(missing)[:5]}"


def test_wangjia_ask_knowledge_via_jingpin_folder_not_denied():
    token = _wangjia_token()
    fixtures = load_fixtures()
    resolved = resolve_kb_scope_for_ask(
        "tenant1",
        {"selected_folder_ids": [FOLDER_JINGPIN_CAIBAO_25]},
    )
    assert resolved.get("limit_to_attached") is True
    assert len(resolved.get("attached_doc_ids") or []) > 10
    out = ask_knowledge(
        token,
        QUERY,
        selected_collection_ids=resolved["collection_ids"] or None,
        attached_doc_ids=resolved["attached_doc_ids"] or None,
        limit_to_attached=bool(resolved.get("limit_to_attached")),
        fixtures=fixtures,
    )
    assert not out.get("denied"), out.get("deny_reason") or out
    cites = out.get("citations") or []
    doc_ids = {c.get("doc_id") for c in cites if c.get("doc_id")}
    assert HUAQING_DOC_IN_FOLDER in doc_ids or any(
        "销售费用" in str(c.get("snippet") or "") for c in cites
    ), f"citations={list(doc_ids)[:8]}"


def test_wangjia_agent_deep_prefetch_ok_with_folder_scope(monkeypatch):
    """预检索须成功且非 denied；与 UI 选「竞品财报25」一致。"""
    monkeypatch.setattr(settings, "hermes_enabled", True)
    monkeypatch.setattr(settings, "hermes_base_url", "http://127.0.0.1:8642")
    monkeypatch.setattr(settings, "hermes_dev_mock", True)
    monkeypatch.setattr(settings, "hermes_agent_kb_prefetch", True)

    captured: dict = {}

    def _fake_stream(**kwargs):
        captured.update(kwargs)
        yield {"type": "done", "reply": "# ok", "tool_calls": [], "hermes_stream_stats": {}}

    monkeypatch.setattr("backend.routers.agent.stream_agent_chat", _fake_stream)

    token = _wangjia_token()
    r = client.post(
        "/api/agent/chat/stream",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "messages": [{"role": "user", "content": QUERY}],
            "kb_scope": {"selected_folder_ids": [FOLDER_JINGPIN_CAIBAO_25]},
            "agent_mode": "deep",
        },
    )
    assert r.status_code == 200, r.text[:400]
    done = None
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
    assert done is not None
    assert done.get("agent_tier") == 2
    scope = (captured.get("kb_scope") or {}) if captured else {}
    folder_ids = scope.get("selected_folder_ids") or []
    assert FOLDER_JINGPIN_CAIBAO_25 in folder_ids


def test_wangjia_deep_context_extras_require_kb_ask_for_sales_fee():
    from backend.services.agent_hermes_tier_policy import hermes_orientg_context_extras

    extras = hermes_orientg_context_extras(
        tier="full",
        evidence_pack={"gaps": [], "task_type": "breakdown", "coverage_score": 1.0},
        user_query=QUERY,
    )
    assert extras.get("orientg_kb_ask_required") is True
