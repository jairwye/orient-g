"""finance_matrix_browser_validate 验收规则单测。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend" / "scripts"))

from finance_matrix_browser_validate import validate_row  # noqa: E402


def test_narrative_ok_when_partial_reason_in_parenthetical():
    head = (
        "结论：研发费用减少。\n说明：\n"
        "变动原因：证据未提供变动原因说明，仅列示金额与分项对比"
        "（注：项目重大变动原因提到主要是由于人员减少，职工薪酬减少5,170.50万元）。"
        "\n项目\t2025年\t2024年\n合计\t123,448,492.22\t176,499,977.92"
    )
    row = validate_row(
        {
            "category": "note",
            "subject": "附注-研发",
            "mode": "fast",
            "query": "根据附注说明华清两年研发支出构成变化",
            "tier_line": "执行过程(Tier 0（本地证据综合） · 标准 · Tier 0（Orient-G 本地证据综合，未走 Hermes）)",
            "citations": 10,
            "notes": "cdp-unattended",
            "extract": {
                "hasMoney": True,
                "honestMissing": False,
                "head": head,
                "len": len(head),
                "streamFail": False,
            },
        }
    )
    assert row["checks"]["narrative_change_ok"] is True
    assert row["ok"] is True


def test_inventory_deep_honest_missing_passes():
    head = (
        "存货周转率\t未披露\t未披露\t—\t"
        "存货周转率两期均为「未披露」，侧面印证存货科目期末余额未进入当前知识库索引范围。"
        "依据 skill 文档与预检索结果，Orient-G 无法从现有年报片段中提取存货两期对比金额。"
        "建议：上传包含完整合并资产负债表及附注的财务报告后再查询。"
    )
    row = validate_row(
        {
            "category": "bs",
            "subject": "存货",
            "mode": "deep",
            "query": "华清2025年末与2024年末存货对比",
            "tier_line": "执行过程(Tier 2（Hermes 深度） · 深度（Hermes 全编排）)",
            "citations": 0,
            "notes": "cdp-unattended",
            "extract": {
                "hasMoney": False,
                "honestMissing": True,
                "head": head,
                "len": len(head),
                "streamFail": False,
            },
        }
    )
    assert row["checks"]["honest_missing_evidence"] is True
    assert row["checks"]["has_amounts_or_honest"] is True
    assert row["checks"]["stream_completed"] is True


def test_inventory_deep_report_row_reconciles_pass():
    """report 中 bs/存货/deep 旧行：未披露 + 建议上传 → 诚实缺证据通过。"""
    head = (
        '存货周转率\t未披露\t未披露\t—\t存货周转率两期均为"-"（未披露），'
        "侧面印证存货数据未进入报表附注的索引范围。"
        "建议：如需获取存货两期对比数据，请上传包含完整合并资产负债表及附注的财务报告文件至 Orient-G知识库。"
    )
    row = validate_row(
        {
            "category": "bs",
            "subject": "存货",
            "mode": "deep",
            "query": "华清2025年末与2024年末存货对比",
            "tier_line": "执行过程(Tier 2（Hermes 深度） · 深度（Hermes 全编排）)",
            "citations": 0,
            "notes": "cdp-unattended",
            "extract": {
                "hasMoney": False,
                "honestMissing": False,
                "head": head,
                "len": len(head),
                "streamFail": False,
            },
        }
    )
    assert row["checks"]["stream_completed"] is True
    assert row["checks"]["deep_substance_ok"] is True
    assert row["ok"] is True


def test_inventory_standard_process_leak_fails():
    head = (
        "根据检索结果，Evidence Pack中缺少合并资产负债表中\"存货\"科目的两期期末余额数据。"
        "让我通过 KB检索补充。\n结论\nOrient-G知识库中无法获取华清存货的2025年末与2024年末数据。"
    )
    row = validate_row(
        {
            "category": "bs",
            "subject": "存货",
            "mode": "standard",
            "query": "华清2025年末与2024年末存货对比",
            "tier_line": "执行过程(Tier 1（Hermes 受限） · 标准（Hermes lite + Evidence Pack）)",
            "citations": 12,
            "notes": "cdp-unattended",
            "extract": {
                "hasMoney": False,
                "honestMissing": True,
                "processInAnswer": False,
                "head": head,
                "len": len(head),
                "streamFail": False,
            },
        }
    )
    assert row["checks"]["no_process_in_answer"] is False
    assert row["ok"] is False


def test_deep_citations_zero_with_long_money_fails_stream():
    head = "结论：投资活动现金流量净额 -9,231,582.65 元\n" + ("说明行\n" * 80)
    row = validate_row(
        {
            "category": "cf",
            "subject": "投资活动现金流",
            "mode": "deep",
            "query": "华清2025年与2024年投资活动现金流量对比",
            "tier_line": "执行过程(Tier 2（Hermes 深度） · 深度（Hermes 全编排）)",
            "citations": 0,
            "notes": "cdp-unattended",
            "extract": {
                "hasMoney": True,
                "honestMissing": False,
                "head": head,
                "len": len(head),
                "streamFail": False,
            },
        }
    )
    assert row["checks"]["stream_completed"] is False
    assert row["ok"] is False


def test_bad_est_with_table_fails():
    head = (
        "结论：货币资金约8684万元。\n"
        "项目\t2025年\t2024年\n货币资金\t86,841,234.56\t90,123,456.78"
    )
    row = validate_row(
        {
            "category": "bs",
            "subject": "货币资金",
            "mode": "standard",
            "query": "华清2025年末与2024年末货币资金对比",
            "tier_line": "执行过程(Tier 1（Hermes 受限） · 标准（Hermes lite + Evidence Pack）)",
            "citations": 10,
            "notes": "cdp-unattended",
            "extract": {
                "hasMoney": True,
                "honestMissing": False,
                "badEst": True,
                "head": head,
                "len": len(head),
                "streamFail": False,
            },
        }
    )
    assert row["checks"]["no_unsupported_estimate"] is False
    assert row["ok"] is False
