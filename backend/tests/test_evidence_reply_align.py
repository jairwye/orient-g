"""Evidence Pack 与终稿对齐（通用，无公司/科目硬编码）。"""

from __future__ import annotations

from backend.services.evidence_reply_align import (
    build_evidence_synth_fallback_reply,
    extract_tabular_amounts,
    pack_amounts_for_alignment,
    pack_has_tabular_breakdown,
    reply_amount_coverage,
    reply_has_gap_placeholder,
)


def test_pack_has_tabular_breakdown_generic_facets():
    pack = {
        "facets": [
            {
                "label": "附注 管理费用",
                "excerpt": "职工薪酬 1,234,567.89 折旧 98,765.43 合计 2,345,678.90",
            }
        ]
    }
    assert pack_has_tabular_breakdown(pack)
    amounts = pack_amounts_for_alignment(pack)
    assert "1,234,567.89" in amounts


def test_build_evidence_synth_fallback_with_subject_amounts():
    pack = {
        "facets": [
            {"excerpt": "A 10,802,366.11 B 2,889,547.75 C 13,722,360.23"},
        ]
    }
    anchors = pack_amounts_for_alignment(pack)
    short = "合计 13,722,360.23"
    full = "A 10,802,366.11 B 2,889,547.75 合计 13,722,360.23"
    assert reply_amount_coverage(short, anchors) < reply_amount_coverage(full, anchors)


def test_gap_placeholder_generic():
    assert reply_has_gap_placeholder("证据中未提供可核查的分项金额")
    assert not reply_has_gap_placeholder("分项明细表如下")


def test_choose_supplemental_prefers_synth_on_pack_coverage():
    from backend.services.agent_kb_supplemental import choose_supplemental_reply

    pack = {
        "facets": [
            {"excerpt": "职工薪酬 10,802,366.11 市场及推广 2,889,547.75 合计 13,722,360.23"},
        ]
    }
    prefetch = {"evidence_pack": pack}
    hermes = "| 合计 | 13,722,360.23 | 25,081,092.51 |"
    synth = (
        "结论\n| 职工薪酬 | 10,802,366.11 | 23,295,127.31 |\n"
        "| 市场及推广 | 2,889,547.75 | 1,526,703.85 |\n"
        "| 合计 | 13,722,360.23 | 25,081,092.51 |"
    )
    final, adopted, reason = choose_supplemental_reply(
        hermes_reply=hermes,
        synth_reply=synth,
        prefetch_result=prefetch,
    )
    assert adopted is True
    assert reason in ("synth_better_pack_coverage", "synth_more_amounts", "default_synth")
    assert "10,802,366.11" in final


def test_build_evidence_synth_fallback_honest_missing():
    reply = build_evidence_synth_fallback_reply(
        "2025年末与2024年末应收账款余额对比",
        citations=[{"doc_id": "ud_test", "excerpt": "应收账款周转率 7.02"}],
        evidence_pack={"facets": []},
    )
    assert "缺少证据" in reply
    assert "应收账款" in reply


def test_build_evidence_synth_fallback_with_subject_amounts():
    reply = build_evidence_synth_fallback_reply(
        "2025与2024年销售费用对比",
        citations=[
            {
                "doc_id": "ud_test",
                "excerpt": "销售费用 13,722,360.23 25,081,092.51",
            }
        ],
        evidence_pack={"facets": []},
    )
    assert "13,722,360.23" in reply
    assert "销售费用" in reply


def test_synthesize_kb_reply_uses_evidence_fallback_on_llm_failure(monkeypatch):
    from backend.services.agent_kb_prefetch import synthesize_kb_reply
    from backend.services.knowledge_acl import load_fixtures

    def _boom(**_kwargs):
        raise TimeoutError("timed out")

    monkeypatch.setattr(
        "backend.services.ai_interaction_llm.generate_answer_with_evidence",
        _boom,
    )
    result = synthesize_kb_reply(
        tenant_id="tenant1",
        user_query="2025与2024年销售费用对比",
        prefetch_result={
            "citations": [
                {
                    "doc_id": "ud_test",
                    "excerpt": "销售费用 13,722,360.23 25,081,092.51",
                }
            ],
            "evidence_pack": {"facets": [], "task_type": "compare"},
        },
        fixtures=load_fixtures(),
    )
    assert result["synthesis"] == "prefetch_fallback_evidence"
    assert "13,722,360.23" in result["reply"]

