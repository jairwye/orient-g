"""多 query 检索与 pack 组装（mock ask）。"""

from __future__ import annotations

from unittest.mock import patch

from backend.services.kb_retrieve_pack import retrieve_kb_evidence_pack


def test_multi_query_merges_citations():
    calls: list[str] = []

    def _fake_ask(_token, query, **kwargs):
        calls.append(query)
        if "销售费用" in query:
            return {
                "ok": True,
                "citations": [{"doc_id": "ud_fee", "chunk_id": "c_fee"}],
                "reply": "fee hit",
            }
        return {
            "ok": True,
            "citations": [{"doc_id": "ud_pl", "chunk_id": "c_pl"}],
            "reply": "pl hit",
        }

    with patch("backend.services.kb_retrieve_pack.ask_knowledge", side_effect=_fake_ask):
        result, tools = retrieve_kb_evidence_pack(
            "token",
            "华清成本明细分解",
            {"selected_folder_ids": ["f1"]},
            fixtures={"tenant_id": "tenant1", "documents": []},
            multi_query=True,
            resolved_scope={
                "collection_ids": [],
                "attached_doc_ids": ["ud_pl"],
                "limit_to_attached": True,
            },
        )
    assert result.get("ok")
    assert len(calls) >= 2
    ids = {c.get("doc_id") for c in result.get("citations") or []}
    assert "ud_fee" in ids
    assert "ud_pl" in ids
    assert result.get("evidence_pack")
    assert len(tools) == len(calls)


def test_partial_subquery_denied_merges_ok_results():
    calls: list[str] = []

    def _fake_ask(_token, query, **kwargs):
        calls.append(query)
        if "销售费用" in query:
            return {"denied": True, "deny_reason": "no access"}
        return {
            "ok": True,
            "citations": [{"doc_id": "ud_ok", "chunk_id": "c1"}],
            "reply": "ok",
        }

    with patch("backend.services.kb_retrieve_pack.ask_knowledge", side_effect=_fake_ask):
        result, tools = retrieve_kb_evidence_pack(
            "token",
            "成本明细",
            {},
            fixtures={"tenant_id": "tenant1", "documents": []},
            multi_query=True,
            resolved_scope={
                "collection_ids": [],
                "attached_doc_ids": [],
                "limit_to_attached": False,
            },
        )
    assert result.get("ok")
    assert result.get("partial_denied") is True
    assert any(c.get("doc_id") == "ud_ok" for c in (result.get("citations") or []))
    assert any(t.get("status") == "denied" for t in tools)
    assert "部分子检索" in " ".join(result.get("evidence_pack", {}).get("gaps") or [])
