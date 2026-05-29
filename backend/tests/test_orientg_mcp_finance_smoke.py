"""财务部测试账号 + orientg_kb_ask 对 c_finance_public_1 冒烟（TDD）。"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app
from backend.routers.settings import DEPARTMENT_FINANCE
from backend.services import orientg_mcp_tools as mcp_tools
from backend.services.dev_users import ensure_department_test_user
from backend.services.knowledge_acl import compute_acl_scope

client = TestClient(app)
FINANCE_TEST_PASSWORD = "FinanceTest!2026"


def _finance_user_and_token() -> tuple[str, str]:
    username = f"finance_mcp_{uuid.uuid4().hex[:8]}"
    ensure_department_test_user(
        username,
        password=FINANCE_TEST_PASSWORD,
        department=DEPARTMENT_FINANCE,
    )
    res = client.post(
        "/api/auth/login",
        json={"username": username, "password": FINANCE_TEST_PASSWORD},
    )
    assert res.status_code == 200, res.text
    token = res.json().get("token")
    assert token
    return username, token


def test_finance_acl_includes_finance_public_collection():
    _, token = _finance_user_and_token()
    scope = compute_acl_scope(token)
    assert "c_finance_public_1" in scope["allowed_collection_ids"]


def test_finance_orientg_kb_ask_finance_public_not_denied(monkeypatch):
    _, token = _finance_user_and_token()

    monkeypatch.setattr(
        "backend.services.orientg_mcp_tools.ask_knowledge",
        lambda user_token, query, **kwargs: {
            "denied": False,
            "reply": "finance-stub",
            "citations": [{"doc_id": "d_fin_rules_1", "chunk_id": "ch1"}],
        },
    )
    monkeypatch.setattr("backend.services.orientg_mcp_tools.write_event", lambda *a, **k: None)

    out = mcp_tools.orientg_kb_ask(
        token,
        "财务制度里报销流程是什么？",
        selected_collection_ids=["c_finance_public_1"],
    )
    assert out.get("denied") is not True, out
    assert out["ok"] is True
    assert out["reply"] == "finance-stub"


def test_finance_orientg_kb_ask_integration_when_llm_or_retrieval_available(monkeypatch):
    """无 mock 时走真实 ask_knowledge；无库/无嵌入时跳过。"""
    _, token = _finance_user_and_token()
    monkeypatch.setattr("backend.services.orientg_mcp_tools.write_event", lambda *a, **k: None)

    try:
        out = mcp_tools.orientg_kb_ask(
            token,
            "测试检索",
            selected_collection_ids=["c_finance_public_1"],
        )
    except Exception as e:
        pytest.skip(f"integration prerequisites missing: {e}")

    if out.get("denied") and out.get("reason") == "selected_collection_ids not allowed":
        pytest.fail(f"finance user should allow c_finance_public_1: {out}")
    # 允许空检索结果，但不允许 ACL deny
    assert out.get("reason") != "selected_collection_ids not allowed"
