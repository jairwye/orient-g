"""competitor_report_parser 单测（YYCQ 蓝本）。"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.services.competitor_report_parser import (
    CompetitorParseError,
    parse_cell_value,
    parse_markdown,
    split_dual_values,
)

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
MINIMAL_FIXTURE = FIXTURE_DIR / "competitor_report_minimal.md"
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
    assert len(snap["sections"]) == 10
    ids = [s["id"] for s in snap["sections"]]
    assert ids == [f"sec-{i:02d}" for i in range(1, 11)]
    assert len(snap["companies"]) >= 2
    assert isinstance(warnings, list)


def test_parse_yycq_fixture(yycq_md: str):
    snap, warnings = parse_markdown(
        yycq_md,
        source_filename="行业财报汇析-2025年_数据文档_YYCQ版.md",
        uploaded_by="test",
    )
    assert snap["version"] == 1
    assert len(snap["sections"]) == 10
    ids = [s["id"] for s in snap["sections"]]
    assert ids == [f"sec-{i:02d}" for i in range(1, 11)]
    assert len(snap["companies"]) == 8
    sec01 = next(s for s in snap["sections"] if s["id"] == "sec-01")
    anchors = [b.get("anchor") for b in sec01["blocks"]]
    assert "sec-01-2" in anchors
    tables = [b for b in sec01["blocks"] if b["kind"] == "table" and b["anchor"] == "sec-01-2"]
    assert tables
    assert len(tables[0]["rows"]) >= 8
    assert isinstance(warnings, list)


def test_parse_rejects_empty():
    with pytest.raises(CompetitorParseError):
        parse_markdown("", source_filename="x.md", uploaded_by="test")


def test_parse_cell_value():
    warnings: list[str] = []
    assert parse_cell_value("1,234.5", "sec-01-2", "营收", warnings) == 1234.5
    assert parse_cell_value("(100)", "sec-01-2", "净利", warnings) == -100
    assert parse_cell_value("12%", "sec-01-2", "rate", warnings) == 0.12
    assert parse_cell_value("-", "sec-01-2", "x", warnings) is None


def test_split_dual_values():
    assert split_dual_values("5698 289,895") == ("5698", "289,895")
    assert split_dual_values("100") is None
