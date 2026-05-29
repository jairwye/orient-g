"""Evidence Pack 检索：表格证据并入 pack。"""

from __future__ import annotations

from unittest.mock import patch

from backend.services.kb_retrieve_pack import retrieve_kb_evidence_pack


def test_table_evidence_merged_into_pack():
    table_ev = {
        "evidence_type": "table_row",
        "table_id": "tbl_fin_1",
        "row_key": "2025Q1",
        "column_id": "revenue",
    }

    def _fake_ask(_token, query, **kwargs):
        return {"ok": True, "citations": [], "reply": "no doc"}

    def _fake_table(_tenant, *, selected_table_ids, query):
        assert "tbl_fin_1" in selected_table_ids
        return {"evidence": table_ev, "answer_value": 12345}

    with patch("backend.services.kb_retrieve_pack.ask_knowledge", side_effect=_fake_ask):
        with patch(
            "backend.services.kb_tables.retrieve_table_evidence",
            side_effect=_fake_table,
        ):
            result, _ = retrieve_kb_evidence_pack(
                "token",
                "营收是多少",
                {},
                fixtures={"tenant_id": "tenant1", "documents": []},
                multi_query=False,
                resolved_scope={
                    "collection_ids": [],
                    "table_ids": ["tbl_fin_1"],
                    "attached_doc_ids": [],
                    "limit_to_attached": False,
                },
            )
    assert result.get("ok")
    cites = result.get("citations") or []
    assert any(c.get("table_id") == "tbl_fin_1" for c in cites)
    pack = result.get("evidence_pack") or {}
    facets = pack.get("facets") or []
    assert any(f.get("table_id") == "tbl_fin_1" for f in facets)
