"""华清损益：财务公共库应有可引用证据（非「缺少证据」）。"""

from __future__ import annotations

import jwt
import time

import pytest
from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app
from backend.routers.settings import DEPARTMENT_FINANCE
from backend.services import orientg_mcp_tools as mcp_tools
from backend.services.agent_kb_prefetch import synthesize_kb_reply
from backend.services.dev_users import ensure_department_test_user
from backend.services.kb_fixture_bindings import (
    FINANCE_PUBLIC_COLLECTION,
    HUAQING_DOC_ID,
    HUAQING_TABLE_ID,
    ensure_finance_huaqing_fixture_bindings,
)
from backend.services.knowledge_acl import load_fixtures
from backend.services.knowledge_pipeline import ask_knowledge

client = TestClient(app)
FINANCE_TEST_PASSWORD = "FinanceTest!2026"
FINANCE_USER = "finance_test"
QUERY = "出具一份华清25、24两年损益的对比分析表，仅依据知识库证据。"


@pytest.fixture(autouse=True)
def _bind_huaqing_fixture():
    ensure_finance_huaqing_fixture_bindings()


def _finance_token() -> str:
    ensure_department_test_user(
        FINANCE_USER,
        password=FINANCE_TEST_PASSWORD,
        department=DEPARTMENT_FINANCE,
    )
    r = client.post(
        "/api/auth/login",
        json={"username": FINANCE_USER, "password": FINANCE_TEST_PASSWORD},
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


def test_expand_retrieval_terms_for_pl_compare():
    from backend.services import knowledge_pipeline as kp

    terms = kp._expand_retrieval_terms(kp._tokenize_query(QUERY), QUERY)
    assert "利润表" in terms
    assert "2024" in terms or "2025" in terms


def _citations_have_huaqing_pl_evidence(cites: list) -> bool:
    import json

    blob = json.dumps(cites, ensure_ascii=False)
    if HUAQING_DOC_ID in blob or HUAQING_TABLE_ID in blob:
        return True
    if any(x in blob for x in ("834", "798", "118", "56,071", "56071", "revenue", "营业收入")):
        return True
    for c in cites:
        if not isinstance(c, dict):
            continue
        if c.get("evidence_type") == "table_row" and c.get("row_key"):
            return True
        did = str(c.get("doc_id") or "")
        if did.startswith("ud_") and c.get("collection_id") == FINANCE_PUBLIC_COLLECTION:
            return True
    return False


def test_ask_knowledge_returns_huaqing_pl_fixture_chunk():
    token = _finance_token()
    fixtures = load_fixtures()
    out = ask_knowledge(
        token,
        QUERY,
        selected_collection_ids=[FINANCE_PUBLIC_COLLECTION],
        fixtures=fixtures,
    )
    assert not out.get("denied"), out
    cites = out.get("citations") or []
    assert cites, cites
    assert _citations_have_huaqing_pl_evidence(cites), [c.get("doc_id") for c in cites]
    assert all(c.get("doc_id") or c.get("table_id") for c in cites)


def test_mcp_ask_huaqing_has_numeric_evidence_in_synthesis(monkeypatch):
    token = _finance_token()
    fixtures = load_fixtures()
    ask_res = mcp_tools.orientg_kb_ask(
        token,
        QUERY,
        selected_collection_ids=["c_finance_public_1"],
    )
    assert ask_res.get("ok")
    cites = ask_res.get("citations") or []
    assert _citations_have_huaqing_pl_evidence(cites), cites

    if not settings.chat_llm_available:
        pytest.skip("LLM not configured")

    monkeypatch.setattr(
        "backend.services.ai_interaction_llm.generate_answer_with_evidence",
        lambda **k: "华清 2025 年营业收入 834,527,936.00；2024 年 798,118,000.00",
    )

    synth = synthesize_kb_reply(
        tenant_id=fixtures.get("tenant_id") or "tenant1",
        user_query=QUERY,
        prefetch_result=ask_res,
        fixtures=fixtures,
    )
    reply = (synth.get("reply") or "").strip()
    assert reply
    assert "缺少证据" not in reply
    assert "834" in reply or "798" in reply or "118" in reply


def test_agent_stream_huaqing_reply_contains_numbers(monkeypatch):
    """fast 模式 + mock 预检索：Tier 0 流式应答应含损益数字。"""
    token = _finance_token()
    monkeypatch.setattr(settings, "hermes_enabled", True)
    monkeypatch.setattr(settings, "hermes_base_url", "http://127.0.0.1:8642")
    monkeypatch.setattr(settings, "hermes_dev_mock", False)
    monkeypatch.setattr(settings, "hermes_agent_kb_prefetch", True)
    monkeypatch.setattr(settings, "hermes_agent_kb_fast_path", True)

    def _mock_prefetch(user_token, messages, kb_scope, **kwargs):
        ask_res = {
            "ok": True,
            "reply": "华清 2025 营业收入 834,527,936.00；2024 年 798,118,000.00",
            "citations": [{"doc_id": HUAQING_DOC_ID, "chunk_id": "ch_pl", "evidence_type": "doc_chunk"}],
            "evidence_pack": {
                "task_type": "compare",
                "coverage_score": 0.9,
                "gaps": [],
                "citations": [{"doc_id": HUAQING_DOC_ID}],
                "facets": [{"keywords_hit": ["营业收入"]}],
            },
        }
        return (
            [{"role": "system", "content": "预检索摘要"}],
            ask_res,
            [{"name": "orientg_kb_ask", "status": "ok", "prefetch": True, "result": ask_res}],
        )

    monkeypatch.setattr("backend.routers.agent.prefetch_kb_context", _mock_prefetch)

    def _fake_stream_fast(**k):
        yield {"type": "status", "message": "快速路径", "step": "kb_fast_path"}
        yield {"type": "delta", "content": "834527936"}
        yield {
            "type": "done",
            "ok": True,
            "reply": "华清 2025 营业收入 834527936；2024 年 798118000",
            "kb_fast_path": True,
            "hermes_used": False,
            "tool_calls": [],
        }

    monkeypatch.setattr("backend.routers.agent.stream_kb_fast_path_events", lambda **k: _fake_stream_fast())
    hermes_stream = {"n": 0}

    def _hermes_stream(**k):
        hermes_stream["n"] += 1
        yield {"type": "done", "reply": "x", "tool_calls": []}

    monkeypatch.setattr("backend.routers.agent.stream_agent_chat", _hermes_stream)

    r = client.post(
        "/api/agent/chat/stream",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "messages": [{"role": "user", "content": QUERY}],
            "kb_scope": {"selected_collection_ids": [FINANCE_PUBLIC_COLLECTION]},
            "allow_kb_write": False,
            "agent_mode": "fast",
        },
        timeout=180,
    )
    assert r.status_code == 200, r.text
    body = r.text
    assert hermes_stream["n"] == 0
    assert "kb_fast_path" in body
    if settings.chat_llm_available:
        assert "834" in body or "798" in body
