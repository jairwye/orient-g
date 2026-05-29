"""AI 互动：与 Agent 共用 retrieve_kb_evidence_pack（多 query + Evidence Pack）。"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.ai_interaction_kb import citations_for_chat_llm, retrieve_kb_for_chat
from backend.tests.test_acl_folder_shared_docs import FOLDER_JINGPIN_CAIBAO_25, _finance_token

FEE_NOTE_DOC = "ud_2ccb589f993b43d5892a637150cbc6af"

client = TestClient(app)


def test_retrieve_kb_for_chat_passes_limit_to_attached_scope():
    captured: dict = {}

    def _fake_pack(_token, _query, _scope, **kwargs):
        captured.update(kwargs)
        return (
            {
                "ok": True,
                "citations": [{"doc_id": "ud_x", "chunk_id": "c1"}],
                "evidence_pack": {"task_type": "fact", "coverage_score": 0.8, "gaps": []},
                "reply": "hit",
            },
            [],
        )

    with patch("backend.services.ai_interaction_kb.retrieve_and_answer", side_effect=_fake_pack):
        out = retrieve_kb_for_chat(
            "tok",
            "华清营收",
            selected_collection_ids=None,
            selected_table_ids=None,
            attached_doc_ids=["ud_a", "ud_b"],
            limit_to_attached=True,
            fixtures={"tenant_id": "tenant1", "documents": []},
        )
    assert out.get("ok")
    rs = captured.get("resolved_scope") or {}
    assert rs.get("limit_to_attached") is True
    assert "ud_a" in (rs.get("attached_doc_ids") or [])


def test_citations_for_chat_llm_uses_top_rerank():
    prefetch = {
        "citations": [
            {"doc_id": "d1", "chunk_id": "c1"},
            {"doc_id": "d2", "chunk_id": "c2"},
        ],
        "evidence_pack": {"task_type": "compare"},
    }
    top = citations_for_chat_llm(
        prefetch,
        "对比",
        tenant_id="tenant1",
        fixtures={"tenant_id": "tenant1", "documents": []},
    )
    assert len(top) <= 8


@pytest.mark.integration
def test_ai_interaction_chat_folder_uses_evidence_pack():
    token = _finance_token()
    with patch("backend.services.ai_interaction_llm.generate_answer_with_evidence") as mock_llm:
        mock_llm.return_value = "（测试）基于证据的回答"
        r = client.post(
            "/api/ai-interaction/chat",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "messages": [{"role": "user", "content": "成本下降主要是怎么实现的，分解成明细的对比"}],
                "kb_scope": {"selected_folder_ids": [FOLDER_JINGPIN_CAIBAO_25]},
            },
        )
    assert r.status_code == 200, r.text
    data = r.json()
    assert not data.get("denied")
    pack = data.get("evidence_pack")
    assert pack is not None
    assert pack.get("task_type") == "breakdown"
    queries = pack.get("retrieval_queries") or []
    assert len(queries) >= 2
    cites = data.get("citations") or []
    doc_ids = {c.get("doc_id") for c in cites}
    assert FEE_NOTE_DOC in doc_ids or any("91f55322" in str(d) for d in doc_ids)


def test_ai_interaction_chat_mocked_pack_path():
    """路由层应调用 retrieve_kb_for_chat 而非单次 ask_knowledge。"""
    token = _finance_token()
    fake = {
        "ok": True,
        "citations": [{"doc_id": "ud_fee", "chunk_id": "c1"}],
        "reply": "pack reply",
        "evidence_pack": {
            "task_type": "breakdown",
            "coverage_score": 0.9,
            "gaps": [],
            "retrieval_queries": ["q1", "q2 销售费用"],
        },
    }

    with patch("backend.services.ai_interaction_kb.retrieve_kb_for_chat", return_value=fake):
        with patch("backend.services.ai_interaction_llm.generate_answer_with_evidence") as mock_llm:
            mock_llm.return_value = "LLM 答案"
            r = client.post(
                "/api/ai-interaction/chat",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "messages": [{"role": "user", "content": "测试 pack 路径"}],
                    "kb_scope": {"selected_collection_ids": ["c_finance_public_1"]},
                },
            )
    assert r.status_code == 200
    data = r.json()
    assert data.get("evidence_pack", {}).get("task_type") == "breakdown"
    assert data.get("read_mode") == "rag_pack"
    mock_llm.assert_called_once()
    kw = mock_llm.call_args.kwargs
    assert kw.get("citations") or (mock_llm.call_args.args[3] if len(mock_llm.call_args.args) > 3 else None)
