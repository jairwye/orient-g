"""vertical_report 解析与读取。"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.config import settings
from backend.services.vertical_report_parser import parse_vertical_report
from backend.services.vertical_report_store import load_vertical_report

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "vertical_report_minimal.md"


def test_parse_vertical_report_companies():
    doc = parse_vertical_report(FIXTURE.read_text(encoding="utf-8"))
    assert doc["version"] == 1
    assert len(doc["companies"]) == 7
    names = [c["name"] for c in doc["companies"]]
    assert names[0] == "可比公司A"
    assert names[-1] == "可比公司G"
    assert doc["companies"][0]["snap_id"] == "v-37"
    c0 = doc["companies"][0]
    assert c0.get("sections"), "公司章节应含 sections"
    assert any(b["kind"] == "table" for b in c0["blocks"])


def test_vertical_section_ids_unique():
    doc = parse_vertical_report(FIXTURE.read_text(encoding="utf-8"))
    for company in doc["companies"]:
        ids = [s["id"] for s in company["sections"]]
        assert len(ids) == len(set(ids)), f"{company['name']} 存在重复 section id: {ids}"


def test_load_vertical_report(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(settings, "competitor_fixture_fallback", True)
    doc = load_vertical_report()
    assert doc is not None
    assert len(doc.get("companies") or []) >= 2
    assert doc.get("meta", {}).get("data_source") == "fixture"
