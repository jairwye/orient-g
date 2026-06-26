"""vertical PDF 文件名 → company id（内网中文名 + canonical）。"""
from __future__ import annotations

import json

import pytest

from backend.config import settings
from backend.services.vertical_company_resolve import (
    order_pdf_entries,
    reset_filename_rules_cache,
    resolve_company_id_from_filename,
)
from backend.services.vertical_report_parser import CANONICAL_PEER_IDS

CN_PDF_NAMES = [
    ("三七互娱2025年度报告分析解读.pdf", "37"),
    ("掌趣科技2025年度报告分析解读.pdf", "zq"),
    ("完美世界2025年度报告分析解读.pdf", "wm"),
    ("塔人网络2025年度报告分析解读.pdf", "tr"),
    ("华清飞扬2025年度报告分析解读.pdf", "hq"),
    ("像素软件2025年度报告分析解读.pdf", "xs"),
    ("绿岸网络2025年度报告分析解读.pdf", "la"),
]


@pytest.fixture(autouse=True)
def _clear_rules_cache():
    reset_filename_rules_cache()
    yield
    reset_filename_rules_cache()


@pytest.mark.parametrize("filename,expected_id", CN_PDF_NAMES)
def test_resolve_cn_pdf_names_development_env(filename: str, expected_id: str, monkeypatch, tmp_path):
    """财务后台 zip 常见内网中文 PDF 名；开发机也须可识别（非仅 production）。"""
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "competitor_fixture_fallback", True)
    monkeypatch.setattr(settings, "vertical_company_rules_json", None)
    monkeypatch.setattr(settings, "vertical_builtin_filename_rules", None)
    assert resolve_company_id_from_filename(filename) == expected_id


def test_resolve_all_seven_cn_peers(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "vertical_builtin_filename_rules", None)
    ids = {resolve_company_id_from_filename(name) for name, _ in CN_PDF_NAMES}
    assert ids == set(CANONICAL_PEER_IDS)


def test_custom_rules_json_does_not_disable_builtin_cn(tmp_path, monkeypatch):
    """uploads 卷有 vertical_company_rules.json 时，内建中文规则仍作 fallback。"""
    comp = tmp_path / "competitor"
    comp.mkdir(parents=True)
    (comp / "vertical_company_rules.json").write_text(
        json.dumps([{"id": "37", "patterns": ["peer_alpha"]}]),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "vertical_company_rules_json", None)
    monkeypatch.setattr(settings, "vertical_builtin_filename_rules", None)
    assert resolve_company_id_from_filename("peer_alpha2025.pdf") == "37"
    assert resolve_company_id_from_filename("完美世界2025年度报告分析解读.pdf") == "wm"


def test_order_pdf_entries_cn_zip_names(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "vertical_builtin_filename_rules", None)
    entries = [(name, tmp_path / name) for name, _ in CN_PDF_NAMES]
    for _, path in entries:
        path.write_bytes(b"%PDF")
    ordered = order_pdf_entries(entries)
    assert len(ordered) == 7
    assert [cid for cid, _, _ in ordered] == list(CANONICAL_PEER_IDS)
