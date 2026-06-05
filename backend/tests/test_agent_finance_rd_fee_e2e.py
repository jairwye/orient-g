"""财务测试账号 + 竞品财报25：研发费用明细 MCP/预检索验收（通用，非生产硬编码）。

doc_id 仅作验收锚点；生产逻辑不写死华清/研发费用金额。
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app
from backend.routers.settings import DEPARTMENT_FINANCE
from backend.services.agent_kb_prefetch import build_prefetch_evidence_excerpts, synthesize_kb_reply
from backend.services.dev_users import ensure_department_test_user
from backend.services.evidence_reply_align import reply_has_derived_breakdown_amounts
from backend.services.kb_retrieve_pack import retrieve_kb_evidence_pack
from backend.services.kb_scope_resolve import resolve_kb_scope_for_ask
from backend.services.knowledge_acl import load_fixtures
from backend.services.knowledge_pipeline import is_fee_appendix_chunk, query_wants_fee_breakdown
from backend.services import orientg_mcp_tools as mcp_tools
from backend.tests.test_acl_folder_shared_docs import FOLDER_JINGPIN_CAIBAO_25

QUERY = "出一份华清25、24两年研发费用明细的对比分析报告"
FEE_NOTE_DOC = "ud_2ccb589f993b43d5892a637150cbc6af"
MERGED_PL_DOC = "ud_91f55322e2594b9c9d3ba7ceb89fafb2"

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


def _resolved_folder_attach(token: str) -> dict:
    fixtures = load_fixtures()
    return resolve_kb_scope_for_ask(
        fixtures.get("tenant_id") or "tenant1",
        _folder_scope(),
    )


@pytest.fixture(scope="module")
def finance_rd_pack():
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
        "resolved": resolved,
    }


def test_query_wants_rd_fee_breakdown():
    assert query_wants_fee_breakdown(QUERY)


def test_rd_pack_retrieval_hits_fee_or_pl_docs(finance_rd_pack):
    doc_ids = {str(c.get("doc_id") or "") for c in finance_rd_pack["citations"]}
    assert FEE_NOTE_DOC in doc_ids or MERGED_PL_DOC in doc_ids, sorted(doc_ids)[:12]


def test_rd_prefetch_excerpt_mentions_rd_or_period_fee(finance_rd_pack):
    fixtures = finance_rd_pack["fixtures"]
    excerpts = build_prefetch_evidence_excerpts(
        finance_rd_pack["citations"],
        QUERY,
        tenant_id="tenant1",
        fixtures=fixtures,
        limit=10,
        max_chunks_per_doc=2,
    )
    blob = "\n".join(str(e.get("excerpt") or "") for e in excerpts)
    assert "研发费用" in blob or "120,565,207.54" in blob or "172,697,867.39" in blob


def test_mcp_ask_rd_fee_returns_numeric_evidence(finance_rd_pack):
    token = finance_rd_pack["token"]
    resolved = finance_rd_pack["resolved"]
    out = mcp_tools.orientg_kb_ask(
        token,
        "华清 研发费用 附注 2024 2025 职工薪酬",
        attached_doc_ids=list(resolved.get("attached_doc_ids") or [])[:200],
        limit_to_attached=bool(resolved.get("limit_to_attached")),
    )
    assert out.get("denied") is not True, out
    assert out.get("ok") is True, out
    cites = out.get("citations") or []
    assert len(cites) >= 3, "MCP 应返回 citations"
    doc_ids = {str(c.get("doc_id") or "") for c in cites}
    assert FEE_NOTE_DOC in doc_ids or MERGED_PL_DOC in doc_ids or len(doc_ids) >= 5, sorted(doc_ids)[:8]
    reply = str(out.get("reply") or "")
    blob = reply + " ".join(str(c) for c in cites)
    assert re.search(r"\d{1,3}(?:,\d{3})+\.\d{2}", blob) or len(cites) >= 10, reply[:200]


def test_rd_synth_reply_no_derived_amounts(finance_rd_pack):
    if not settings.chat_llm_available:
        pytest.skip("LLM not configured")
    from backend.services.agent_kb_supplemental import supplemental_answer_addon
    from backend.services.evidence_reply_align import pack_amounts_for_alignment, reply_amount_coverage
    from backend.services.hermes_stream_sanitize import finalize_agent_reply

    synth = synthesize_kb_reply(
        tenant_id="tenant1",
        user_query=QUERY,
        prefetch_result=finance_rd_pack["pack_res"],
        fixtures=finance_rd_pack["fixtures"],
        skill_addon_extra=supplemental_answer_addon(user_query=QUERY, tier="lite"),
        cite_limit=12,
    )
    reply = finalize_agent_reply(
        str(synth.get("reply") or ""),
        user_query=QUERY,
        tier2_native=False,
    )
    assert reply.strip(), synth
    assert not reply_has_derived_breakdown_amounts(reply), reply[:800]
    assert "[doc_chunk" not in reply
    anchors = pack_amounts_for_alignment(finance_rd_pack["pack_res"].get("evidence_pack"))
    assert reply_amount_coverage(reply, anchors[:4]) >= 0.25 or re.search(
        r"\d{1,3}(?:,\d{3})+\.\d{2}", reply
    ), reply[:400]


def test_rd_appendix_chunk_in_corpus_if_present(finance_rd_pack):
    excerpts = build_prefetch_evidence_excerpts(
        finance_rd_pack["citations"],
        QUERY,
        tenant_id="tenant1",
        fixtures=finance_rd_pack["fixtures"],
        limit=12,
        max_chunks_per_doc=2,
    )
    rd_chunks = [
        str(e.get("excerpt") or "")
        for e in excerpts
        if "研发费用" in str(e.get("excerpt") or "") and "##" in str(e.get("excerpt") or "")
    ]
    if not rd_chunks:
        pytest.skip("KB 未返回研发费用附注 chunk（数据依赖）")
    assert any(is_fee_appendix_chunk(c, query=QUERY) for c in rd_chunks)
