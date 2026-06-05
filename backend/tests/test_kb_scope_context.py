"""文件夹范围上下文（多公司横比）。"""

from __future__ import annotations

from backend.services.agent_kb_prefetch import _diversify_citations_by_folder, _top_citations_for_llm
from backend.services.kb_scope_context import build_scope_folder_context, multi_company_scope_addon


def test_multi_company_scope_addon():
    hint = multi_company_scope_addon(
        {
            "multi_company_scope": True,
            "scope_folders": [{"name": "华清25"}, {"name": "竞品B25"}],
        }
    )
    assert "多主体" in hint
    assert "华清25" in hint


def test_diversify_citations_by_folder():
    labels = {"d1": "华清25", "d2": "竞品B25"}
    scored = [
        (1000.0, {"doc_id": "d1", "chunk_id": "c1"}),
        (990.0, {"doc_id": "d1", "chunk_id": "c2"}),
        (800.0, {"doc_id": "d2", "chunk_id": "c3"}),
    ]
    out = _diversify_citations_by_folder(scored, labels, 2)
    assert len(out) == 2
    assert {c["doc_id"] for c in out} == {"d1", "d2"}


def test_top_citations_multi_company_prefers_diversity():
    labels = {f"d{i}": f"公司{i}" for i in range(4)}
    citations = [{"doc_id": f"d{i}", "chunk_id": f"c{i}", "score": 100 - i} for i in range(4)]
    top = _top_citations_for_llm(
        citations,
        "多家销售费用对比",
        limit=3,
        doc_folder_labels=labels,
        multi_company_scope=True,
    )
    assert len(top) == 3
    folders = {labels[str(c["doc_id"])] for c in top}
    assert len(folders) >= 2
