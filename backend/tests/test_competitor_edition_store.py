"""competitor_edition_store 单测（1.2.3.e）。"""
from __future__ import annotations

import json

import pytest

from backend.services import competitor_edition_store as ed
from backend.services.competitor_report_store import load_snapshot, save_snapshot


@pytest.fixture
def upload_root(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "backend.services.competitor_report_store.settings.upload_dir",
        str(tmp_path),
    )
    monkeypatch.setattr(
        "backend.services.competitor_edition_store.settings.upload_dir",
        str(tmp_path),
    )
    return tmp_path


def test_validate_edition_id():
    assert ed.validate_edition_id("2025-annual") == "2025-annual"
    assert ed.validate_edition_id("2026-h1") == "2026-h1"
    with pytest.raises(ValueError):
        ed.validate_edition_id("Bad ID")
    with pytest.raises(ValueError):
        ed.validate_edition_id("")


def test_save_list_current(upload_root):
    ed.save_edition_meta(
        {
            "edition_id": "2025-annual",
            "kind": "annual",
            "period_label": "2025 年报",
            "has_vertical": True,
        }
    )
    ed.save_edition_meta(
        {
            "edition_id": "2026-h1",
            "kind": "interim",
            "period_label": "2026 半年报",
            "has_vertical": False,
        }
    )
    ed.set_current("2026-h1")
    assert ed.get_current() == "2026-h1"
    rows = ed.list_editions()
    assert len(rows) == 2
    by_id = {r["edition_id"]: r for r in rows}
    assert by_id["2026-h1"]["is_current"] is True
    assert by_id["2025-annual"]["is_current"] is False
    assert by_id["2026-h1"]["has_vertical"] is False


def test_migrate_legacy_singleton(upload_root):
    root = upload_root / "competitor"
    root.mkdir(parents=True)
    snap = {
        "version": 1,
        "meta": {"title": "旧单例", "period": "2025", "currency_unit": "万元"},
        "companies": [],
        "sections": [],
        "warnings": [],
    }
    (root / "report.snapshot.json").write_text(json.dumps(snap), encoding="utf-8")
    (root / "report.md").write_bytes(b"# legacy\n")
    (root / "vertical.snapshot.json").write_text("{}", encoding="utf-8")

    result = ed.migrate_legacy_competitor_layout()
    assert result["migrated"] is True
    assert ed.get_current() == "2025-annual"
    target = root / "editions" / "2025-annual"
    assert (target / "report.snapshot.json").is_file()
    assert (target / "report.md").is_file()
    # e-3：纵向一并迁入 2025-annual
    assert (target / "vertical.snapshot.json").is_file()
    assert not (root / "vertical.snapshot.json").exists()
    assert not (root / "report.snapshot.json").exists()

    # 幂等
    again = ed.migrate_legacy_competitor_layout()
    assert again["migrated"] is False

    loaded = load_snapshot()
    assert loaded is not None
    assert loaded["meta"]["title"] == "旧单例"
    assert loaded["meta"].get("edition_id") == "2025-annual"


def test_save_snapshot_scoped_to_edition(upload_root):
    snap_a = {
        "version": 1,
        "meta": {"title": "A", "period": "2025", "currency_unit": "万元", "company_count": 1},
        "companies": [],
        "sections": [],
        "warnings": [],
    }
    snap_b = {
        "version": 1,
        "meta": {"title": "B", "period": "2026", "currency_unit": "万元", "company_count": 1},
        "companies": [],
        "sections": [],
        "warnings": [],
    }
    save_snapshot(b"# a\n", snap_a, edition_id="2025-annual", keep_history=False)
    save_snapshot(b"# b\n", snap_b, edition_id="2026-h1", keep_history=False)
    ed.set_current("2026-h1")

    assert load_snapshot()["meta"]["title"] == "B"
    assert load_snapshot("2025-annual")["meta"]["title"] == "A"
    assert (upload_root / "competitor" / "editions" / "2025-annual" / "report.snapshot.json").is_file()
    assert (upload_root / "competitor" / "editions" / "2026-h1" / "report.snapshot.json").is_file()


def test_load_snapshot_explicit_edition_no_cross_fallback(upload_root, monkeypatch):
    """显式 edition 无快照时不得回退到 current / 根单例 / fixture。"""
    monkeypatch.setattr(
        "backend.services.competitor_report_store.settings.competitor_fixture_fallback",
        True,
    )
    snap = {
        "version": 1,
        "meta": {"title": "current-only", "period": "2025", "currency_unit": "万元"},
        "companies": [],
        "sections": [],
        "warnings": [],
    }
    save_snapshot(b"# cur\n", snap, edition_id="2025-annual", keep_history=False)
    ed.set_current("2025-annual")
    ed.ensure_edition("2026-h1", kind="interim", has_vertical=False)

    assert load_snapshot("2026-h1") is None
    assert load_snapshot("2025-annual")["meta"]["title"] == "current-only"


def test_save_snapshot_infers_annual_kind_from_id(upload_root):
    snap = {
        "version": 1,
        "meta": {"title": "Y2024", "period": "2024", "currency_unit": "万元"},
        "companies": [],
        "sections": [],
        "warnings": [],
    }
    save_snapshot(b"# 2024\n", snap, edition_id="2024-annual", keep_history=False)
    meta = ed.load_edition_meta("2024-annual")
    assert meta is not None
    assert meta["kind"] == "annual"


def test_get_current_multi_without_pointer_is_deterministic(upload_root):
    ed.ensure_edition("2024-h1", kind="interim")
    ed.ensure_edition("2026-h1", kind="interim")
    # 无 current.json、无 legacy：按 edition_id 数字友好降序
    assert ed.get_current() == "2026-h1"
