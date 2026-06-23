"""vertical_docling_adapter 与文件名解析单测。"""
from __future__ import annotations

from pathlib import Path

import json
import pytest

from backend.services.vertical_company_resolve import (
    display_name_for_company,
    resolve_company_id_from_filename,
)
from backend.services.vertical_docling_adapter import (
    build_vertical_snapshot,
    clean_narrative_markdown,
    company_from_docling,
    normalize_docling_markdown,
    repair_docling_markdown,
    _headers_look_like_data,
)

COMPANY_B = "可比公司B"

SAMPLE_DOCLING_MD = """
# wm2025年度报告分析解读

## 一、公司简介

可比公司B是一家游戏公司。

## 五、核心财务表现-盈利稳健

| 指标名称 | 本期(2025) | 上期(2024) | 同比变化 |
| --- | --- | --- | --- |
| 营业总收入 | 66.60亿元 | 55.70亿元 | +19.55% |
| 归母净利润 | 7.31亿元 | -12.88亿元 | 改善 |
"""


def test_resolve_company_id_from_filename():
    assert resolve_company_id_from_filename("wm2025_report.pdf") == "wm"
    assert resolve_company_id_from_filename("37.pdf") == "37"
    assert resolve_company_id_from_filename("peer_37_2025.pdf") == "37"
    assert resolve_company_id_from_filename("unknown.pdf") is None


def test_display_name_for_company():
    assert display_name_for_company("wm", "wm2025_report.pdf") == "wm_report"


def test_runtime_rules_from_uploads_json(tmp_path, monkeypatch):
    from backend.config import settings
    from backend.services.vertical_company_resolve import reset_filename_rules_cache

    comp = tmp_path / "competitor"
    comp.mkdir(parents=True)
    (comp / "vertical_company_rules.json").write_text(
        json.dumps([{"id": "37", "patterns": ["peer_alpha"]}]),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(settings, "vertical_company_rules_json", None)
    reset_filename_rules_cache()
    assert resolve_company_id_from_filename("peer_alpha2025_report.pdf") == "37"
    reset_filename_rules_cache()


def test_normalize_docling_markdown_headings():
    import re

    out = normalize_docling_markdown(SAMPLE_DOCLING_MD)
    assert "### 一、公司简介" in out
    assert "### 五、核心财务表现" in out
    assert not re.search(r"^##\s+一、", out, re.MULTILINE)


def test_company_from_docling_parses_table():
    warnings: list[str] = []
    co = company_from_docling(
        company_id="wm",
        company_name=COMPANY_B,
        company_index=1,
        md_text=SAMPLE_DOCLING_MD,
        warnings=warnings,
    )
    assert co["id"] == "wm"
    assert co["snap_id"] == "v-wm"
    tables = [b for b in co["blocks"] if b.get("kind") == "table"]
    assert len(tables) >= 1
    assert "指标名称" in (tables[0].get("headers") or [])


def test_normalize_docling_nfkc_compatibility_chars():
    md = "## ⼀、公司简介\n\n正文\n\n## ⼆、分析目的\n\n目的"
    out = normalize_docling_markdown(md)
    assert "### 一、公司简介" in out
    assert "### 二、分析目的" in out


def test_normalize_docling_subsection_to_bold():
    md = "### 四、核心结论\n\n## 亮点\n\n- item"
    out = normalize_docling_markdown(md)
    assert "**亮点**" in out
    assert "## 亮点" not in out


def test_company_from_docling_splits_subsection_narratives():
    md = """
### 四、核心结论

## 亮点

- 第一条
- 第二条

## 风险点

- 风险一
"""
    co = company_from_docling(
        company_id="wm",
        company_name=COMPANY_B,
        company_index=1,
        md_text=md,
    )
    sec4 = next(s for s in co["sections"] if (s.get("title") or "").startswith("四、"))
    narratives = [b for b in sec4["blocks"] if b.get("kind") == "narrative"]
    assert len(narratives) >= 2
    assert any("亮点" in n.get("markdown", "") for n in narratives)
    assert any("风险" in n.get("markdown", "") for n in narratives)


def test_build_vertical_snapshot():
    co = company_from_docling(
        company_id="wm",
        company_name=COMPANY_B,
        company_index=1,
        md_text=SAMPLE_DOCLING_MD,
    )
    snap = build_vertical_snapshot([co], uploaded_by="admin", source_filename="test.zip")
    assert snap["meta"]["company_count"] == 1
    assert snap["meta"]["data_source"] == "docling"


def test_repair_docling_merges_orphan_after_table_cell():
    md = """
| 指标 | 说明 |
| --- | --- |
| 经营活动现金流净额 | 销售回款改善及成本控制提升现金生 |

成能力

## 洞察 ：
"""
    out = repair_docling_markdown(md)
    assert "成能力" not in out.split("##")[0] or "现金生成能力" in out
    assert "现金生成能力" in out.replace(" ", "")


def test_repair_docling_strips_orphan_number_line():
    md = """## 洞察 ：

1.

1. 游戏业务是绝对核心支柱。
2. 电竞业务正从成本中心转向价值中心。
"""
    out = repair_docling_markdown(md)
    assert "\n1.\n" not in out
    assert "1. 游戏业务" in out


def test_repair_docling_merges_cross_page_table_orphan():
    md = """
| 产品类型 | 生命周期阶段 | 代表产品 | 业务表现与贡献 |
| --- | --- | --- | --- |
| 长青经典产品 | 成熟/持续焕新期 | 《游戏A》系列 | 长线运营维持稳态贡献 |

开辟新赛道，贡献增量收

| 潮流创新爆款 | 新品爆发/成长期 | 《游戏B》 | 入与用户，是业绩弹性的主要来源 |
"""
    out = repair_docling_markdown(md)
    compact = out.replace(" ", "").replace("，", ",")
    assert "开辟新赛道,贡献增量收" not in compact.split("|潮流创新爆款|")[0]
    assert "开辟新赛道,贡献增量收入与用户" in compact


def test_company_from_docling_no_orphan_cheng_neng_li():
    md = """
### 五、核心财务表现

| 指标名称 | 本期 | 上期 | 同比 | 说明 |
| --- | --- | --- | --- | --- |
| 经营活动现金流净额 | 10.93亿元 | 5.77亿元 | +89.57% | 销售回款改善及成本控制提升现金生 |

成能力

## 洞察 ：

1.

1. 盈利能力全面复苏。
"""
    co = company_from_docling(
        company_id="wm",
        company_name=COMPANY_B,
        company_index=1,
        md_text=md,
    )
    narratives = [b for b in co["blocks"] if b.get("kind") == "narrative"]
    assert not any(n.get("markdown", "").strip() in ("成能力", "成能⼒") for n in narratives)
    tables = [b for b in co["blocks"] if b.get("kind") == "table"]
    assert tables
    last_row = tables[0]["rows"][-1]
    note = last_row.get("说明") or last_row.get(list(last_row.keys())[-1])
    assert "成能力" in str(note).replace(" ", "")


def test_repair_docling_cross_page_produces_single_table():
    md = """
### 六、主营业务

| 产品类型 | 生命周期阶段 | 代表产品 | 业务表现与贡献 |
| --- | --- | --- | --- |
| 长青经典产品 | 成熟/持续焕新期 | 《游戏A》系列 | 长线运营维持稳态贡献 |

开辟新赛道，贡献增量收

| 潮流创新爆款 | 新品爆发/成长期 | 《游戏B》 | 入与用户，是业绩弹性的主要来源 |
| 新兴潜力品类 | 探索/孵化期 | SLG、休闲游戏 | 小规模投入试水 |
"""
    co = company_from_docling(
        company_id="wm",
        company_name=COMPANY_B,
        company_index=1,
        md_text=md,
    )
    sec = next(s for s in co["sections"] if "六、" in (s.get("title") or ""))
    tables = [b for b in sec["blocks"] if b.get("kind") == "table"]
    assert len(tables) == 1
    assert len(tables[0]["rows"]) == 3
    last_cell = tables[0]["rows"][1]["业务表现与贡献"]
    assert "开辟新赛道" in last_cell.replace(" ", "")
    assert "入与用户" in last_cell.replace(" ", "")


def test_repair_docling_does_not_merge_conclusion_into_table():
    md = """
| 指标 | 说明 |
| --- | --- |
| 经营活动现金流净额 | 销售回款改善及成本控制提升现金生 |

成能力

## 洞察 ：

1. 盈利能力全面复苏。
2. 收入与现金流同步改善。

结论 ：可比公司B2025年实现全面业绩反转。
"""
    co = company_from_docling(
        company_id="wm",
        company_name=COMPANY_B,
        company_index=1,
        md_text=md,
    )
    tables = [b for b in co["blocks"] if b.get("kind") == "table"]
    narratives = [b for b in co["blocks"] if b.get("kind") == "narrative"]
    note = tables[0]["rows"][-1].get("说明", "")
    assert "结论" not in str(note)
    assert any("结论" in n.get("markdown", "") for n in narratives)


def test_clean_narrative_markdown():
    assert "1. 第一条" in clean_narrative_markdown("1.\n\n1. 第一条")
    assert "1." not in clean_narrative_markdown("1.\n\n1. 第一条").split("1. 第一条")[0]


def test_repair_displaced_bold_in_conclusion():
    md = (
        "结论 :可比公司B主营业务呈现清晰的结构性变革。 依然来自 ,尤其以《游戏X》 核心贡献 游戏业务 "
        "等经典IP的长线运营。"
    )
    out = clean_narrative_markdown(md)
    assert "核心贡献依然来自游戏业务" in out.replace(" ", "")
    assert "**" not in out
    assert "依然来自 ,尤其" not in out


def test_section9_accounting_policy_row_cells():
    md = """
### 九、风险扫描

| 风险类别 | 风险描述 | 具体内容 |
| --- | --- | --- |
| 审计意见风险 | 描述 | 内容 |
|  | 采用新会计准则且记账本位币为人民币,会计政策一致性好,但需关 | 2024-2025年均使用新会计准则,记账本位币为人民币,会计年结日为 |

会计政策风险 注行业会计准则变动对游戏业务收入确认的潜在影响 1231,政策执行连续性和可比性较强

洞察 :传媒行业资产
"""
    co = company_from_docling(company_id="wm", company_name=COMPANY_B, company_index=1, md_text=md)
    sec = next(s for s in co["sections"] if "九、" in (s.get("title") or ""))
    tbl = next(b for b in sec["blocks"] if b.get("kind") == "table")
    last = tbl["rows"][-1]
    assert last["风险类别"] == "会计政策风险"
    assert "注行业" in last["风险描述"]
    assert "但需关" in last["风险描述"]
    assert "1231" in last["具体内容"]
    assert "会计年结日为" in last["具体内容"]


def test_section13_collapses_duplicate_indicator_columns():
    md = """
### 十三、成长能力分析

| 指标 | 指标 | 2023年 | 2024年 | 2025年 |
| --- | --- | --- | --- | --- |
| 营业总收入同比增⻓率 | 营业总收入同比增⻓率 | 1.57% | -28.50% | 19.55% |
| 总资产(相对年初增⻓ | 率) | -7.34% | -21.55% | -7.89% |
"""
    co = company_from_docling(company_id="wm", company_name=COMPANY_B, company_index=1, md_text=md)
    sec = next(s for s in co["sections"] if "十三" in (s.get("title") or ""))
    tbl = next(b for b in sec["blocks"] if b.get("kind") == "table")
    assert tbl["headers"] == ["指标", "2023年", "2024年", "2025年"]
    assert len(tbl["rows"]) == 2
    assert tbl["rows"][0]["指标"] == "营业总收入同比增⻓率"
    assert "相对年初增⻓率" in tbl["rows"][1]["指标"].replace(" ", "")


LOCAL_WM_MD = Path("uploads/competitor/vertical/ingest/ving_wm_test/archive/wm/full.md")


def test_section9_insight_not_in_table():
    if not LOCAL_WM_MD.is_file():
        pytest.skip("local docling artifact missing")
    md = LOCAL_WM_MD.read_text(encoding="utf-8")
    co = company_from_docling(company_id="wm", company_name=COMPANY_B, company_index=1, md_text=md)
    sec9 = next(s for s in co["sections"] if (s.get("title") or "").startswith("九、"))
    for b in sec9["blocks"]:
        if b.get("kind") == "table":
            for row in b.get("rows") or []:
                for v in row.values():
                    assert "洞察" not in str(v)
                    assert "总结" not in str(v)
    insights = [b for b in sec9["blocks"] if b.get("kind") == "narrative" and "洞察" in b.get("markdown", "")]
    assert insights


def test_section10_balance_sheet_has_proper_header():
    if not LOCAL_WM_MD.is_file():
        pytest.skip("local docling artifact missing")
    md = LOCAL_WM_MD.read_text(encoding="utf-8")
    co = company_from_docling(company_id="wm", company_name=COMPANY_B, company_index=1, md_text=md)
    sec10 = next(s for s in co["sections"] if (s.get("title") or "").startswith("十、"))
    tables = [b for b in sec10["blocks"] if b.get("kind") == "table"]
    assert tables
    first = tables[0]
    assert "报表项目" in (first.get("headers") or [])
    assert not _headers_look_like_data(first["headers"])
    for row in first.get("rows") or []:
        for v in row.values():
            assert "洞察" not in str(v)
