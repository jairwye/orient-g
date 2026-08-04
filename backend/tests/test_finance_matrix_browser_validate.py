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
            "query": "根据附注说明可比E两年研发支出构成变化",
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
            "query": "可比E2025年末与2024年末存货对比",
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
            "query": "可比E2025年末与2024年末存货对比",
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
        "让我通过 KB检索补充。\n结论\nOrient-G知识库中无法获取可比E存货的2025年末与2024年末数据。"
    )
    row = validate_row(
        {
            "category": "bs",
            "subject": "存货",
            "mode": "standard",
            "query": "可比E2025年末与2024年末存货对比",
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


def test_standard_poll_timeout_substantive_answer_passes_stream():
    """浏览器实测：Tier1 完成但 citations 未渲染，正文已含金额表 → poll_timeout  salvage。"""
    head = (
        "可比公司E2025年与2024年营业收入对比\n结论可比公司E2025年营业收入为1.00亿元，"
        "较2024年的1.39亿元减少3,839万元，同比下降27.71%。\n"
        "核心指标\n指标\t2025年度\t2024年度\t变动额\t变动幅度\n"
        "营业收入\t100,148,026.24元\t138,539,446.45元\t-38,391,420.21元\t-27.71%\n"
        "按地区分类\n境内\t41,321,781.95元\t+17.09%\n境外\t58,826,244.29元\t-43.02%\n"
        "变动原因根据年报原文\"项目重大变动原因\"：境外收入大幅下滑43.02%是营业收入整体下降的主要原因。\n"
        "口径说明\n数据来源：可比公司E网络股份有限公司（母公司口径）合并利润表。"
    )
    row = validate_row(
        {
            "category": "pnl",
            "subject": "营业收入",
            "mode": "standard",
            "query": "可比公司E2025年与2024年营业收入对比及变动说明",
            "tier_line": "执行过程(Tier 1（Hermes 受限） · 标准（Hermes lite + Evidence Pack）)",
            "citations": 0,
            "notes": "cdp-unattended; poll_timeout",
            "extract": {
                "hasMoney": True,
                "honestMissing": False,
                "head": head,
                "len": len(head),
                "streamFail": False,
            },
        }
    )
    assert row["checks"]["stream_completed"] is True
    assert row["ok"] is True


def test_standard_tier1_complete_no_cites_passes_stream():
    """Tier1 完成、streamDone、citations 未渲染但正文已稳定 → 视为流式完成。"""
    head = (
        "可比公司E2025年与2024年经营活动产生的现金流量净额对比结论：缺少证据。"
        "知识库中未命中合并现金流量表数据。\n"
        "核心指标\n指标\t2025年度\t2024年度\t变动\n"
        "经营活动产生的现金流量净额\t缺少证据\t缺少证据\t缺少证据\n"
        "已命中的利润表数据（参考）\n"
        "营业收入\t15,965,709,257.73元\t17,440,957,495.58元\n"
    )
    row = validate_row(
        {
            "category": "cf",
            "subject": "经营活动现金流",
            "mode": "standard",
            "query": "可比公司E2025年与2024年经营活动产生的现金流量净额对比",
            "tier_line": "执行过程(Tier 1（Hermes 受限） · 标准（Hermes lite + Evidence Pack）)",
            "citations": 0,
            "streamDone": True,
            "notes": "cdp-unattended",
            "extract": {
                "hasMoney": True,
                "honestMissing": True,
                "head": head,
                "len": len(head),
                "streamFail": False,
            },
        }
    )
    assert row["checks"]["stream_completed"] is True


def test_deep_citations_zero_with_long_money_fails_stream():
    head = "结论：投资活动现金流量净额 -9,231,582.65 元\n" + ("说明行\n" * 80)
    row = validate_row(
        {
            "category": "cf",
            "subject": "投资活动现金流",
            "mode": "deep",
            "query": "可比E2025年与2024年投资活动现金流量对比",
            "tier_line": "执行过程(Tier 2（Hermes 深度） · 深度（Hermes 全编排）)",
            "citations": 0,
            "streamDone": False,
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


def test_note_rd_deep_breakdown_table_passes_without_narrative_reason():
    head = (
        "根据附注说明，可比公司E两年研发支出构成变化如下：\n"
        "项目\t本期金额 (元)\t上期金额 (元)\t变动额 (元)\n"
        "工资薪金\t96,128,672.18\t131,830,431.38\t-35,701,759.20\n"
        "员工保险\t22,803,701.06\t37,465,592.45\t-14,661,891.39\n"
        "福利费\t1,636,693.01\t2,978,012.88\t-1,341,319.87\n"
        "合计\t123,448,492.22\t176,499,977.92\t-53,051,485.70\n"
        "变动原因\n证据未提供变动原因说明，仅列示金额与分项对比。"
    )
    row = validate_row(
        {
            "category": "note",
            "subject": "附注-研发",
            "mode": "deep",
            "query": "根据附注说明可比公司E两年研发支出构成变化",
            "tier_line": "执行过程(Tier 2（Hermes 深度） · 深度（Hermes 全编排）)",
            "citations": 12,
            "streamDone": True,
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
            "query": "可比E2025年末与2024年末货币资金对比",
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


PERSONNEL_QUERY = "对比分析YYCQ和可比公司A25年的人员结构"

BROWSER_FAIL_HERMES = (
    "结论：证据中缺乏可比公司A2025年的人员结构数据，无法进行对比分析。\n"
    "YYCQ在职员工 139 人；1.1信息-人员 运营 61 研发 70。\n"
    "可比公司A 2025年人员结构数据 缺失证据。\n"
    "YYCQ研发人员数量存在两组数据（95人 vs 1,378人），1,378人数据疑似归属其他主体。"
)

GOOD_PERSONNEL_EXCERPT = (
    "## YYCQ vs 可比公司A · 2025 人员结构对比\n\n"
    "### 人员结构对照\n\n"
    "| 职能归属 | 可比公司A | YYCQ |\n"
    "| --- | --- | --- |\n"
    "| 研发 | 1378 人（占员工 43.91%） | 70 人 |\n"
    "| 运营 | 242 人 | 61 人 |\n"
    "| 管理 | 36 人 | 33.15 人 |\n"
    "| 支持 | 312 人 | 45.85 人 |\n"
    "| 销售 | 946 人 | 证据未覆盖 |\n\n"
    "### 对比分析\n\n"
    "- **结构差异**：YYCQ为 excel 职能四分项；可比公司A为年报员工专节。\n"
    "- **口径差异**：两侧披露口径不同，不可直接混比总人数。\n"
)


def _personnel_row(head: str, *, honest: bool = False) -> dict:
    return {
        "category": "personnel",
        "subject": "A3-横比-深度",
        "mode": "deep",
        "query": PERSONNEL_QUERY,
        "tier_line": (
            "●完成：Tier 2（Hermes 深度编排） · Orient-G 网关 KB ×1 · "
            "Hermes 内 orientg_kb_ask ×2"
        ),
        "citations": 12,
        "notes": "cdp-unattended",
        "streamDone": True,
        "orientg_kb_ask_calls": 3,
        "hermes_kb_ask_calls": 2,
        "gateway_kb_ask_calls": 1,
        "extract": {
            "hasMoney": False,
            "honestMissing": honest,
            "head": head,
            "body_sample": head,
            "len": len(head),
            "streamFail": False,
            "processInAnswer": False,
        },
    }


def test_personnel_compare_browser_fail_hermes_fails_validate():
    row = validate_row(_personnel_row(BROWSER_FAIL_HERMES))
    assert row["ok"] is False


def test_personnel_compare_excerpt_passes_validate():
    from finance_matrix_personnel_cases import personnel_case_spec
    from finance_matrix_personnel_validate import validate_personnel_case_spec

    spec = personnel_case_spec("A3-横比-深度")
    ok, checks = validate_personnel_case_spec(
        GOOD_PERSONNEL_EXCERPT,
        spec=spec,
        mode="deep",
        hermes_kb_ask_calls=3,
        hermes_only_kb_ask_calls=2,
        hermes_mcp_retry_count=0,
        user_query=PERSONNEL_QUERY,
    )
    assert ok is True
    assert checks.get("sanqi_roles_in_table_ok") is True
    row = validate_row(_personnel_row(GOOD_PERSONNEL_EXCERPT))
    assert row["ok"] is True


def test_personnel_structured_final_stream_ok_without_citations():
    """Orient-G structured replace 终稿：citations=0 但对照表完整仍算 stream_completed。"""
    from finance_matrix_personnel_validate import GOOD_PERSONNEL_COMPARE_EXCERPT

    head = GOOD_PERSONNEL_COMPARE_EXCERPT + (
        "\n\n### 补充说明\n\n"
        + "- 两侧披露口径不同，对照表仅并列展示已覆盖字段。\n" * 50
    )
    row = validate_row(
        {
            "category": "personnel",
            "subject": "A3-横比-深度",
            "mode": "deep",
            "query": PERSONNEL_QUERY,
            "tier_line": (
                "●完成：Tier 2（Hermes 深度编排） · Orient-G 网关 KB ×1 · "
                "Hermes 内 orientg_kb_ask ×2"
            ),
            "citations": 0,
            "streamDone": True,
            "reply_source": "hermes",
            "hermes_kb_ask_calls": 2,
            "gateway_kb_ask_calls": 1,
            "hermes_mcp_retry_count": 0,
            "notes": "personnel_early_structured",
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
    assert row["checks"]["tier2"] is True
    assert row["ok"] is True


def test_personnel_hermes_short_skeleton_stream_fails_as_final():
    """新尺子 C：主气泡「成稿骨架」短模板不得算 A3 通过（骨架≠Hermes 主写）。"""
    head = (
        "成稿骨架（请原样采用下列数字写入终稿；禁止改写为员工总数倍数对照）\n"
        "人员结构对照\n"
        "职能归属\t可比公司A\tYYCQ\n"
        "研发\t1378 人\t70 人\n"
        "销售\t946 人\t证据未覆盖\n"
        "运营\t242 人\t61 人\n"
        "对比分析\n"
        "结构差异：两家披露口径不同（年报专业构成 vs excel 职能分项），不可直接比员工总数。\n"
        "口径说明\n"
        "可比公司A=年报节选；YYCQ=excel「1.1信息-人员」。"
    )
    row = validate_row(
        {
            "category": "personnel",
            "subject": "A3-横比-深度",
            "mode": "deep",
            "query": PERSONNEL_QUERY,
            "tier_line": (
                "●完成：Tier 2（Hermes 深度编排） · Evidence Pack：任务 compare · "
                "终稿出处：Hermes · Hermes 内 orientg_kb_ask ×2 · Orient-G 网关 KB ×1"
            ),
            "citations": 0,
            "streamDone": True,
            "reply_source": "hermes",
            "hermes_kb_ask_calls": 2,
            "gateway_kb_ask_calls": 1,
            "orientg_kb_ask_calls": 3,
            "hermes_mcp_retry_count": 0,
            "kb_supplemental": False,
            "structured_gate_applied": False,
            "notes": "cdp-unattended; skeleton_must_fail",
            "extract": {
                "hasMoney": False,
                "honestMissing": False,
                "hasTable": False,
                "badEst": False,
                "head": head,
                "body_sample": head,
                "len": len(head),
                "streamFail": False,
            },
        }
    )
    assert row["ok"] is False


def test_personnel_thin_salvage_without_title_fails_a3():
    """剥掉「成稿骨架」标题后的短 salvage 仍不得刷绿 A3。"""
    head = (
        "人员结构对照\n"
        "职能归属\t可比公司A\tYYCQ\n"
        "研发\t1378 人\t70 人\n"
        "销售\t946 人\t证据未覆盖\n"
        "运营\t242 人\t61 人\n"
        "对比分析\n"
        "结构差异：两家披露口径不同（年报专业构成 vs excel 职能分项），不可直接比员工总数。\n"
        "口径说明\n"
        "可比公司A=年报节选；YYCQ=excel「1.1信息-人员」。"
    )
    row = validate_row(
        {
            "category": "personnel",
            "subject": "A3-横比-深度",
            "mode": "deep",
            "query": PERSONNEL_QUERY,
            "tier_line": (
                "●完成：Tier 2 · 覆盖率 90% · 终稿出处：Hermes · "
                "Hermes 内 orientg_kb_ask ×3 · Orient-G 网关 KB ×1"
            ),
            "citations": 41,
            "streamDone": True,
            "reply_source": "hermes",
            "hermes_kb_ask_calls": 3,
            "gateway_kb_ask_calls": 1,
            "orientg_kb_ask_calls": 4,
            "hermes_mcp_retry_count": 0,
            "kb_supplemental": False,
            "structured_gate_applied": False,
            "extract": {
                "hasMoney": False,
                "honestMissing": False,
                "hasTable": True,
                "badEst": False,
                "head": head,
                "body_sample": head,
                "len": len(head),
                "streamFail": False,
            },
        }
    )
    assert row["ok"] is False
    assert (row.get("checks") or {}).get("hermes_authorship_fail") == "thin_mcp_salvage_final"


def test_personnel_hermes_good_draft_with_员工总数_口径_ok():
    """口径说明含「员工总数」不得被当成规模错稿；须保住长对照稿。"""
    head = (
        "YYCQ vs 可比公司A · 2025 人员结构对比\n"
        "结论：两家数据来源与统计口径不同，不可将YYCQ excel 分项合计与可比公司A员工总数直接比规模。\n"
        "### 人员结构对照\n"
        "| 职能归属 | 可比公司A | YYCQ |\n"
        "| --- | --- | --- |\n"
        "| 研发 | 1378 人 | 70 人 |\n"
        "| 运营 | 242 人 | 61 人 |\n"
        "| 销售 | 946 人 | 证据未覆盖 |\n"
        "### 对比分析\n"
        "YYCQ：excel 职能四分项；可比公司A：年报研发 1378（占 43.91%），另含销售 946、运营 242。\n"
        "结构差异与可比性：仅研发维度可参照；缺失写证据未覆盖。\n"
        "### 口径说明\n"
        "可比公司A=年报节选；YYCQ=excel「1.1信息-人员」。\n"
    )
    row = validate_row(
        {
            "category": "personnel",
            "subject": "A3-横比-深度",
            "mode": "deep",
            "query": PERSONNEL_QUERY,
            "tier_line": (
                "●完成：Tier 2（Hermes 深度编排） · Evidence Pack：任务 compare · 覆盖率 90% · "
                "终稿出处：Hermes · Hermes 内 orientg_kb_ask ×2 · Orient-G 网关 KB ×1"
            ),
            "citations": 4,
            "streamDone": True,
            "reply_source": "hermes",
            "hermes_kb_ask_calls": 2,
            "gateway_kb_ask_calls": 1,
            "orientg_kb_ask_calls": 3,
            "hermes_mcp_retry_count": 0,
            "kb_supplemental": False,
            "structured_gate_applied": False,
            "notes": "cdp-unattended",
            "extract": {
                "hasMoney": False,
                "honestMissing": False,
                "hasTable": True,
                "badEst": False,
                "head": head,
                "body_sample": head,
                "len": len(head),
                "streamFail": False,
            },
        }
    )
    assert row["ok"] is True
    assert "成稿骨架" not in head


def test_personnel_structured_footer_cite_not_inline_violation():
    """DOM 渲染无 ### 的引用说明 + citations 计数不应判 badInlineCite。"""
    head = (
        "YYCQ vs 可比公司A · 2025 人员结构对比\n\n"
        "### 人员结构对照\n\n"
        "| 职能归属 | 可比公司A | YYCQ |\n"
        "| --- | --- | --- |\n"
        "| 研发 | 1378 人 | 70 人 |\n"
        "| 运营 | 242 人 | 61 人 |\n"
        "| 销售 | 946 人 | 证据未覆盖 |\n"
        "| 管理 | 36 人 | 33.15 人 |\n\n"
        "### 对比分析\n\n"
        "口径差异：不可直接混比。\n\n"
        "引用说明\n"
        "数据均来自权限范围内 citations；深度档应通过 Hermes MCP `orientg_kb_ask` 核实上述节选。\n"
        "citations（12）"
    )
    row = validate_row(
        {
            "category": "personnel",
            "subject": "A2-横比-标准",
            "mode": "standard",
            "query": "对比分析YYCQ和可比公司A25年的人员结构",
            "tier_line": "执行过程(Tier 1（Hermes 受限） · 标准（Hermes lite + Evidence Pack）)",
            "citations": 12,
            "notes": "cdp-unattended",
            "extract": {
                "hasMoney": False,
                "honestMissing": False,
                "hasTable": True,
                "badInlineCite": True,
                "head": head,
                "body_sample": head,
                "len": len(head),
                "streamFail": False,
            },
        }
    )
    assert row["checks"]["no_inline_cite_in_answer"] is True
    assert row["ok"] is True
