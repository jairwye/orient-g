"""财务测试账号 + 竞品财报25：销售费用明细 Agent 路径（TDD，不写死 doc 进生产逻辑）。

用例只断言「附注分项 chunk 被排进 LLM 证据」，doc_id 仅作验收锚点。
"""

from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app
from backend.routers.settings import DEPARTMENT_FINANCE
from backend.services.agent_kb_prefetch import (
    _top_citations_for_llm,
    build_prefetch_evidence_excerpts,
    prefetch_kb_context,
    synthesize_kb_reply,
)
from backend.services.dev_users import ensure_department_test_user
from backend.services.kb_retrieve_pack import retrieve_kb_evidence_pack
from backend.services.kb_scope_resolve import resolve_kb_scope_for_ask
from backend.services.knowledge_acl import load_fixtures
from backend.services.knowledge_pipeline import is_fee_appendix_chunk, query_wants_fee_breakdown
from backend.tests.test_acl_folder_shared_docs import FOLDER_JINGPIN_CAIBAO_25

# 竞品财报25 内 §销售费用附注（验收锚点，非生产硬编码）
FEE_APPENDIX_DOC = "ud_2ccb589f993b43d5892a637150cbc6af"
PARENT_PL_DOC = "ud_67d0f860dbbb4196861d5ab97b472584"
MERGED_PL_DOC = "ud_91f55322e2594b9c9d3ba7ceb89fafb2"

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


def _folder_scope() -> dict[str, list[str]]:
    return {"selected_folder_ids": [FOLDER_JINGPIN_CAIBAO_25]}


@pytest.fixture(scope="module")
def finance_pack():
    token = _finance_token()
    fixtures = load_fixtures()
    scope = _folder_scope()
    resolved = resolve_kb_scope_for_ask("tenant1", scope)
    pack_res, tools = retrieve_kb_evidence_pack(
        token,
        QUERY,
        scope,
        fixtures=fixtures,
        resolved_scope=resolved,
        multi_query=True,
    )
    assert pack_res.get("ok"), pack_res
    return {
        "token": token,
        "fixtures": fixtures,
        "pack_res": pack_res,
        "tools": tools,
        "citations": pack_res.get("citations") or [],
    }


def test_query_wants_fee_breakdown_for_sales_fee_compare():
    assert query_wants_fee_breakdown(QUERY)


def test_pack_retrieval_includes_fee_appendix_doc(finance_pack):
    doc_ids = {c.get("doc_id") for c in finance_pack["citations"]}
    assert FEE_APPENDIX_DOC in doc_ids


def test_top_citations_rank_fee_appendix_for_detail_query(finance_pack):
    fixtures = finance_pack["fixtures"]
    cites = finance_pack["citations"]
    top = _top_citations_for_llm(
        cites,
        QUERY,
        limit=8,
        tenant_id="tenant1",
        fixtures=fixtures,
        max_chunks_per_doc=2,
    )
    top_ids = [c.get("doc_id") for c in top]
    assert FEE_APPENDIX_DOC in top_ids, top_ids[:8]
    fee_idx = top_ids.index(FEE_APPENDIX_DOC)
    merged_idx = top_ids.index(MERGED_PL_DOC) if MERGED_PL_DOC in top_ids else 99
    assert fee_idx < merged_idx, "附注分项应排在合并利润表之前"


def test_prefetch_excerpts_contain_fee_line_items(finance_pack):
    fixtures = finance_pack["fixtures"]
    excerpts = build_prefetch_evidence_excerpts(
        finance_pack["citations"],
        QUERY,
        tenant_id="tenant1",
        fixtures=fixtures,
        limit=8,
        max_chunks_per_doc=2,
    )
    blob = "\n".join(e.get("excerpt") or "" for e in excerpts)
    assert "职工薪酬" in blob, "Hermes 预检索节选应含附注分项"
    assert any(e.get("doc_id") == FEE_APPENDIX_DOC for e in excerpts)


def test_evidence_pack_facets_hit_sales_fee_keywords(finance_pack):
    pack = finance_pack["pack_res"].get("evidence_pack") or {}
    hits: set[str] = set()
    for f in pack.get("facets") or []:
        hits.update(f.get("keywords_hit") or [])
    assert "销售费用" in hits
    facet_docs = {f.get("doc_id") for f in pack.get("facets") or []}
    assert FEE_APPENDIX_DOC in facet_docs or PARENT_PL_DOC in facet_docs


def test_synthesize_passes_fee_appendix_to_llm(finance_pack, monkeypatch):
    if not settings.chat_llm_available:
        pytest.skip("LLM not configured")
    captured: dict = {}

    def _fake_gen(**kwargs):
        captured["citations"] = kwargs.get("citations") or []
        return "mock"

    monkeypatch.setattr(
        "backend.services.ai_interaction_llm.generate_answer_with_evidence",
        _fake_gen,
    )
    synth = synthesize_kb_reply(
        tenant_id="tenant1",
        user_query=QUERY,
        prefetch_result=finance_pack["pack_res"],
        fixtures=finance_pack["fixtures"],
    )
    assert synth.get("ok")
    cite_ids = [c.get("doc_id") for c in captured.get("citations") or []]
    assert FEE_APPENDIX_DOC in cite_ids, cite_ids


def test_agent_stream_prefetch_citations_include_fee_appendix(monkeypatch, finance_pack):
    """模拟 Agent 标准轮：真实预检索 + mock Hermes，done 引用应含附注 doc。"""
    monkeypatch.setattr(settings, "hermes_enabled", True)
    monkeypatch.setattr(settings, "hermes_base_url", "http://127.0.0.1:8642")
    monkeypatch.setattr(settings, "hermes_dev_mock", False)
    monkeypatch.setattr(settings, "hermes_agent_kb_prefetch", True)
    monkeypatch.setattr(settings, "hermes_agent_kb_fast_path", False)

    def _fake_hermes_stream(**kwargs):
        yield {"type": "status", "message": "mock", "step": "connect"}
        yield {
            "type": "done",
            "reply": "（mock hermes）",
            "hermes_session_id": "sess_test",
            "tool_calls": [],
            "hermes_stream_stats": {"orientg_kb_ask_calls": 0},
        }

    monkeypatch.setattr("backend.services.hermes_client.stream_agent_chat", _fake_hermes_stream)

    token = finance_pack["token"]
    r = client.post(
        "/api/agent/chat/stream",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "messages": [{"role": "user", "content": QUERY}],
            "kb_scope": _folder_scope(),
            "allow_kb_write": False,
            "agent_mode": "standard",
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
    assert done, "missing done event"
    cite_ids = {c.get("doc_id") for c in done.get("citations") or [] if isinstance(c, dict)}
    assert FEE_APPENDIX_DOC in cite_ids or any(
        is_fee_appendix_chunk(str(c.get("excerpt") or "")) for c in (done.get("citations") or [])
    ), sorted(cite_ids)[:12]


def test_fee_appendix_detector_on_live_chunk():
    from backend.services.ai_interaction_llm import _load_doc_chunk_text

    txt = _load_doc_chunk_text("tenant1", FEE_APPENDIX_DOC, None, 1) or ""
    assert txt
    assert is_fee_appendix_chunk(txt)
    assert re.search(r"10,802,366\.11|13,722,360\.23", txt)
