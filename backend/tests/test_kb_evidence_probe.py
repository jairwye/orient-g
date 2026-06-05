"""KB 证据探测：问句驱动、非写死 probe 表。"""

from __future__ import annotations

from backend.services.kb_evidence_probe import (
    blob_has_subject_near_amount,
    build_evidence_probe_query,
    primary_compare_subject,
    reply_matches_kb_evidence,
    reply_says_honest_missing,
)
from backend.services.kb_retrieval_plan import compare_subjects_from_query


def test_compare_subjects_from_fee_query():
    subs = compare_subjects_from_query("出一份25、24两年研发费用明细的对比分析报告")
    assert "研发费用" in subs


def test_compare_subjects_from_balance_sheet_query():
    subs = compare_subjects_from_query("2025年末与2024年末应收账款余额对比")
    assert "应收账款" in subs


def test_compare_subjects_from_cf_query():
    subs = compare_subjects_from_query("2025年与2024年经营活动产生的现金流量净额对比")
    assert any("经营" in s and "现金流" in s for s in subs)


def test_build_probe_query_uses_plan_not_hardcoded_entity():
    q = "2025年末与2024年末存货对比"
    probe = build_evidence_probe_query(q, entity="某公司")
    assert "某公司" in probe
    assert "存货" in probe.replace(" ", "")


def test_blob_subject_same_line_amount():
    blob = "应收账款 | 1,234,567.89 | 987,654.32"
    assert blob_has_subject_near_amount(blob, "应收账款")
    assert not blob_has_subject_near_amount(blob, "应收股利")


def test_blob_rejects_unrelated_line_item():
    blob = "应收股利 | 1,234,567.89 | 987,654.32"
    assert not blob_has_subject_near_amount(blob, "应收账款")


def test_reply_honest_missing_accepts_gap_table():
    t = "| 存货 | 缺少证据 | 缺少证据 |"
    assert reply_says_honest_missing("结论：缺少证据\n" + t)


def test_reply_matches_kb_when_kb_has_no_data():
    probe = {"has_data": False, "anchors": [], "user_query": "存货对比"}
    assert reply_matches_kb_evidence("缺少证据，无法对比", user_query="存货对比", kb_probe=probe)


def test_reply_matches_kb_fails_when_kb_has_data_but_reply_missing():
    probe = {
        "has_data": True,
        "anchors": ["13,722,360.23"],
        "user_query": "销售费用对比",
    }
    assert not reply_matches_kb_evidence(
        "缺少证据，KB 无数据",
        user_query="销售费用对比",
        kb_probe=probe,
    )


def test_primary_compare_subject_from_query():
    assert primary_compare_subject("华清2025年与2024年净利润对比分析") == "净利润"
