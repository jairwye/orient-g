"""Evidence Pack 构建与覆盖率。"""

from __future__ import annotations

from backend.services.evidence_pack import (
    build_evidence_pack,
    merge_citations,
    pack_coverage_sufficient,
    query_needs_hermes_orchestration,
)


def test_merge_citations_dedup_by_chunk():
    a = [{"doc_id": "d1", "chunk_id": "c1"}]
    b = [{"doc_id": "d1", "chunk_id": "c1"}, {"doc_id": "d2", "chunk_id": "c2"}]
    merged = merge_citations([a, b])
    assert len(merged) == 2


def test_build_pack_has_facets_and_score():
    cites = [
        {"doc_id": "ud_x", "chunk_id": "c1", "evidence_type": "doc_chunk"},
    ]
    pack = build_evidence_pack(
        user_query="华清营收",
        task_type="fact",
        retrieval_queries=["华清营收"],
        citations=cites,
        reply_parts=["hit 1"],
        tenant_id="tenant1",
        fixtures={"tenant_id": "tenant1", "documents": []},
        chunk_texts={"ud_x:c1": "## 合并利润表\n营业收入 100.00"},
    )
    assert pack["version"] == 1
    assert pack["task_type"] == "fact"
    assert pack["facets"]
    assert pack["coverage_score"] >= 0.2


def test_coverage_breakdown_requires_fee_keyword():
    pack = {
        "task_type": "breakdown",
        "coverage_score": 0.3,
        "citations": [{"doc_id": "d1"}],
        "facets": [{"keywords_hit": ["营业成本"]}],
        "gaps": [],
    }
    assert not pack_coverage_sufficient(pack, user_query="成本明细分解")
    pack["facets"].append(
        {
            "label": "销售费用",
            "keywords_hit": ["销售费用", "管理费用"],
            "excerpt": "职工薪酬 1,000,000.00\n折旧 200,000.00",
        }
    )
    pack["coverage_score"] = 0.65
    assert pack_coverage_sufficient(pack, user_query="成本明细分解")


def test_compare_with_gaps_needs_orchestration():
    pack = {"task_type": "compare", "gaps": ["缺少 2024 合并利润表"], "coverage_score": 0.4}
    assert query_needs_hermes_orchestration("两年对比", pack)


def test_breakdown_detail_without_gaps_still_needs_orchestration():
    pack = {"task_type": "breakdown", "gaps": [], "coverage_score": 0.9}
    assert query_needs_hermes_orchestration("华清25、24两年销售费用明细对比报告", pack)


def test_change_reason_gap_not_raised_when_excerpt_has_narrative():
    pack = build_evidence_pack(
        user_query="出一份华清25、24两年销售费用明细的对比分析报告",
        task_type="breakdown",
        retrieval_queries=["华清 销售费用 附注"],
        citations=[{"doc_id": "ud_a", "chunk_id": "c1", "evidence_type": "doc_chunk"}],
        reply_parts=["ok"],
        tenant_id="tenant1",
        fixtures={"tenant_id": "tenant1", "documents": []},
        chunk_texts={
            "ud_a:c1": (
                "## 31 、销售费用\n| 职工薪酬 | 10,802,366.11 | 23,295,127.31 |\n"
                "## 项目重大变动原因\n销售费用减少，主要系人员减少，职工薪酬减少 1,249.28 万元。"
            ),
        },
    )
    assert "未命中费用变动的文字性原因说明" not in (pack.get("gaps") or [])
