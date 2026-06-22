"""competitor_report_parser 单测（YYCQ 蓝本）。"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.services.competitor_report_parser import (
    CompetitorParseError,
    _is_wide_company_table,
    _looks_like_metric_header,
    _parse_table,
    _split_table_cells,
    collect_sec09_anchor_stats,
    parse_cell_value,
    parse_markdown,
    split_dual_values,
)

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
MINIMAL_FIXTURE = FIXTURE_DIR / "competitor_report_minimal.md"
LABELS_FIXTURE = FIXTURE_DIR / "competitor_report_labels.md"
YYCQ_FIXTURE = FIXTURE_DIR / "competitor_report_yycq.md"
YYCQ_UPLOAD = (
    Path(__file__).resolve().parents[2]
    / "uploads"
    / "行业财报汇析-2025年_数据文档_YYCQ版.md"
)


def _resolve_yycq_md() -> Path | None:
    for p in (YYCQ_FIXTURE, YYCQ_UPLOAD):
        if p.is_file():
            return p
    return None


@pytest.fixture
def minimal_md() -> str:
    return MINIMAL_FIXTURE.read_text(encoding="utf-8")


@pytest.fixture
def yycq_md() -> str:
    path = _resolve_yycq_md()
    if path is None:
        pytest.skip("YYCQ fixture missing (copy MD to backend/tests/fixtures/ or uploads/)")
    return path.read_text(encoding="utf-8")


def test_parse_minimal_fixture(minimal_md: str):
    snap, warnings = parse_markdown(
        minimal_md,
        source_filename="competitor_report_minimal.md",
        uploaded_by="test",
    )
    assert snap["version"] == 1
    assert len(snap["sections"]) == 9
    ids = [s["id"] for s in snap["sections"]]
    assert ids == [f"sec-{i:02d}" for i in range(1, 10)]
    assert len(snap["companies"]) >= 2
    assert isinstance(warnings, list)


def test_parse_yycq_fixture(yycq_md: str):
    snap, warnings = parse_markdown(
        yycq_md,
        source_filename="行业财报汇析-2025年_数据文档_YYCQ版.md",
        uploaded_by="test",
    )
    assert snap["version"] == 1
    assert len(snap["sections"]) == 9
    ids = [s["id"] for s in snap["sections"]]
    assert ids == [f"sec-{i:02d}" for i in range(1, 10)]
    assert len(snap["companies"]) == 8
    sec01 = next(s for s in snap["sections"] if s["id"] == "sec-01")
    anchors = [b.get("anchor") for b in sec01["blocks"]]
    assert "sec-01-2" in anchors
    tables = [b for b in sec01["blocks"] if b["kind"] == "table" and b["anchor"] == "sec-01-2"]
    assert tables
    assert len(tables[0]["rows"]) >= 8
    assert isinstance(warnings, list)


def test_company_labels_skip_long_table_metrics():
    """长表 KPI 列不得误映射为公司 label；宽表表头优先。"""
    md = LABELS_FIXTURE.read_text(encoding="utf-8")
    snap, _ = parse_markdown(
        md,
        source_filename="competitor_report_labels.md",
        uploaded_by="test",
    )
    by_id = {c["id"]: c for c in snap["companies"]}
    assert by_id["yycq"]["label"] == "YYCQ"
    assert by_id["37"]["label"] == "可比公司A"
    assert by_id["wm"]["label"] == "可比公司B"
    assert all("亿" not in c["label"] for c in snap["companies"])


def test_wide_vs_long_table_header_detection():
    assert _is_wide_company_table(["公司", "营收(亿)", "营收同比", "净利(亿)"]) is False
    assert _is_wide_company_table(["指标", "YYCQ", "可比公司A"]) is True
    assert _looks_like_metric_header("营收(亿)") is True
    assert _looks_like_metric_header("可比公司A") is False


def test_parse_yycq_sec05_product_table(yycq_md: str):
    snap, _ = parse_markdown(
        yycq_md,
        source_filename="行业财报汇析-2025年_数据文档_YYCQ版.md",
        uploaded_by="test",
    )
    sec05 = next(s for s in snap["sections"] if s["id"] == "sec-05")
    tables = [b for b in sec05["blocks"] if b.get("anchor") == "sec-05-1" and b.get("kind") == "table"]
    assert tables
    table = max(tables, key=lambda t: len(t["rows"]))
    assert len(table["rows"]) >= 20
    headers = table["headers"]
    assert "收入占比" in headers
    assert "毛利率" in headers
    assert "毛利率变动" in headers
    yycq_row = next(
        r for r in table["rows"]
        if r.get("收入占比") is not None and r.get("毛利率") is not None
    )
    assert yycq_row.get("公司")


def test_parse_yycq_sec04_labor_cost_sections(yycq_md: str):
    snap, _ = parse_markdown(
        yycq_md,
        source_filename="行业财报汇析-2025年_数据文档_YYCQ版.md",
        uploaded_by="test",
    )
    sec04 = next(s for s in snap["sections"] if s["id"] == "sec-04")
    tables = [b for b in sec04["blocks"] if b.get("anchor") == "sec-04-3" and b.get("kind") == "table"]
    assert tables
    table = max(tables, key=lambda t: len(t["rows"]))
    metrics = [r.get("指标") for r in table["rows"]]
    assert any("职工福利" in str(m) for m in metrics)
    assert any("工会经费" in str(m) for m in metrics)
    per_cap_yuan = [r for r in table["rows"] if str(r.get("指标", "")).strip() == "人均(元/年)"]
    assert len(per_cap_yuan) >= 2
    peer_label = next(
        k for k, v in per_cap_yuan[0].items() if k != "指标" and v == 18180.0
    )
    assert per_cap_yuan[0].get(peer_label) == 18180.0
    assert per_cap_yuan[1].get(peer_label) == 1200.0


def test_parse_yycq_sec09_block_anchors(yycq_md: str):
    snap, _ = parse_markdown(
        yycq_md,
        source_filename="行业财报汇析-2025年_数据文档_YYCQ版.md",
        uploaded_by="test",
    )
    sec09 = next(s for s in snap["sections"] if s["id"] == "sec-09")
    anchors = {b.get("anchor") for b in sec09["blocks"]}
    for anchor in ("sec-09-10", "sec-09-11", "sec-09-12", "sec-09-13", "sec-09-14", "sec-09-15"):
        assert anchor in anchors, f"missing {anchor}"
    games = [b for b in sec09["blocks"] if b.get("anchor") == "sec-09-10" and b.get("kind") == "table"]
    assert len(games) >= 2
    gov = [b for b in sec09["blocks"] if b.get("anchor") == "sec-09-3" and b.get("kind") == "table"]
    assert len(gov) >= 2, "sec-09-3 应含汇总表 + 补助明细表"


def test_parse_yycq_sec09_truncation_warnings(yycq_md: str):
    snap, warnings = parse_markdown(
        yycq_md,
        source_filename="行业财报汇析-2025年_数据文档_YYCQ版.md",
        uploaded_by="test",
    )
    sec09 = next(s for s in snap["sections"] if s["id"] == "sec-09")
    stats = collect_sec09_anchor_stats(sec09["blocks"])
    assert stats.get("sec-09-3", {}).get("table", 0) >= 2
    assert stats.get("sec-09-10", {}).get("table", 0) >= 2
    assert not any("截断版" in w for w in warnings)


def test_parse_minimal_sec09_truncation_warning(minimal_md: str):
    _, warnings = parse_markdown(
        minimal_md,
        source_filename="competitor_report_minimal.md",
        uploaded_by="test",
    )
    assert any("截断版" in w for w in warnings)
    assert any("sec-09-3" in w and "明细" in w for w in warnings)


def test_parse_rejects_empty():
    with pytest.raises(CompetitorParseError):
        parse_markdown("", source_filename="x.md", uploaded_by="test")


def test_parse_cell_value():
    warnings: list[str] = []
    assert parse_cell_value("1,234.5", "sec-01-2", "营收", warnings) == 1234.5
    assert parse_cell_value("(100)", "sec-01-2", "净利", warnings) == -100
    assert parse_cell_value("12%", "sec-01-2", "rate", warnings) == 12
    assert parse_cell_value("-214.6%", "sec-08-2", "经营CF增长率", warnings) == -214.6
    assert parse_cell_value("41.4%", "sec-08-2", "经营CF/净利", warnings) == 41.4
    assert parse_cell_value("-", "sec-01-2", "x", warnings) is None


def test_split_dual_values():
    assert split_dual_values("5698 289,895") == ("5698", "289,895")
    assert split_dual_values("100") is None


def test_split_table_cells_preserves_merged_empty_columns():
    """|| 开头行表示合并单元格前的空列，不可丢弃否则整表串列。"""
    assert _split_table_cells("| 公司 | 项目 | 金额 |") == ["公司", "项目", "金额"]
    assert _split_table_cells("|| 项目B | 100 |") == ["", "项目B", "100"]
    assert _split_table_cells("| | 续行 | 200 |") == ["", "续行", "200"]


def test_parse_table_with_leading_empty_cells():
    warnings: list[str] = []
    table = _parse_table(
        [
            "| 公司 | 项目 | 金额 |",
            "| --- | --- | --- |",
            "| 可比公司A | 项目A | 100 |",
            "|| 项目B | 200 |",
        ],
        "test-anchor",
        warnings,
    )
    assert table is not None
    assert table["headers"] == ["公司", "项目", "金额"]
    assert len(table["rows"]) == 2
    assert table["rows"][1]["公司"] in (None, "", "—")
    assert table["rows"][1]["项目"] == "项目B"
    assert table["rows"][1]["金额"] == 200


def test_parse_two_col_table_with_double_pipe_rows():
    """sec-01-1：|| 开头但只有两列，应去掉多余前导空列。"""
    warnings: list[str] = []
    table = _parse_table(
        [
            "| 指标 | 值 |",
            "| --- | --- |",
            "|| 7家公司合计营收 | 约 243.62亿 |",
            "|| 板块总盘变动 | 约 -6.5% |",
        ],
        "sec-01-1",
        warnings,
    )
    assert table is not None
    assert table["rows"][0]["指标"] == "7家公司合计营收"
    assert "243" in str(table["rows"][0]["值"])
    assert table["rows"][1]["指标"] == "板块总盘变动"
