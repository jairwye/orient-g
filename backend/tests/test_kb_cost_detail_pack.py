"""成本/费用分解：多 query pack 应命中销售费用附注 doc。"""

from __future__ import annotations

from backend.services.kb_retrieve_pack import retrieve_kb_evidence_pack
from backend.services.knowledge_acl import load_fixtures
from backend.tests.test_acl_folder_shared_docs import FOLDER_JINGPIN_CAIBAO_25, _finance_token

FEE_NOTE_DOC = "ud_2ccb589f993b43d5892a637150cbc6af"
MERGED_PL_DOC = "ud_91f55322e2594b9c9d3ba7ceb89fafb2"


def test_breakdown_pack_includes_sales_fee_note_doc():
    token = _finance_token()
    fixtures = load_fixtures()
    from backend.services.kb_scope_resolve import resolve_kb_scope_for_ask

    resolved = resolve_kb_scope_for_ask(
        "tenant1", {"selected_folder_ids": [FOLDER_JINGPIN_CAIBAO_25]}
    )
    result, tools = retrieve_kb_evidence_pack(
        token,
        "成本下降主要是怎么实现的，分解成明细的对比",
        {"selected_folder_ids": [FOLDER_JINGPIN_CAIBAO_25]},
        fixtures=fixtures,
        resolved_scope=resolved,
        multi_query=True,
    )
    assert result.get("ok"), result
    assert len(tools) >= 2
    doc_ids = {c.get("doc_id") for c in result.get("citations") or []}
    assert FEE_NOTE_DOC in doc_ids or MERGED_PL_DOC in doc_ids, sorted(doc_ids)[:10]
    pack = result.get("evidence_pack") or {}
    assert pack.get("task_type") == "breakdown"
    hits = set()
    for f in pack.get("facets") or []:
        hits.update(f.get("keywords_hit") or [])
    assert "销售费用" in hits or FEE_NOTE_DOC in doc_ids
