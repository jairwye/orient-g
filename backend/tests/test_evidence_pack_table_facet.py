"""Evidence Pack：表格 citation 生成 facet。"""

from backend.services.evidence_pack import build_evidence_pack


def test_build_pack_table_row_facet():
    pack = build_evidence_pack(
        user_query="表内营收",
        task_type="fact",
        retrieval_queries=["表内营收"],
        citations=[
            {
                "evidence_type": "table_row",
                "table_id": "t1",
                "row_key": "r1",
                "column_id": "amount",
            }
        ],
        reply_parts=["表格命中"],
        tenant_id="tenant1",
        fixtures={"tenant_id": "tenant1", "documents": []},
    )
    facets = pack.get("facets") or []
    assert len(facets) == 1
    assert facets[0].get("table_id") == "t1"
    assert "表 t1" in (facets[0].get("label") or "")
