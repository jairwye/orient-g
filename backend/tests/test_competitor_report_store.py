"""competitor_report_store 单测。"""
from __future__ import annotations

import json

from backend.services.competitor_report_store import (
    load_meta,
    load_snapshot,
    save_snapshot,
)


def test_save_and_load_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "backend.services.competitor_report_store.settings.upload_dir",
        str(tmp_path),
    )
    snap = {
        "version": 1,
        "meta": {
            "title": "测试",
            "uploaded_at": "2026-06-08T00:00:00+00:00",
            "source_filename": "t.md",
            "uploaded_by": "admin",
            "company_count": 8,
            "parser_version": "1.0.0",
            "period": "2025",
            "currency_unit": "万元",
        },
        "companies": [],
        "sections": [],
        "warnings": [],
    }
    raw = b"# test\n"
    save_snapshot(raw, snap, keep_history=False)
    loaded = load_snapshot()
    assert loaded is not None
    assert loaded["meta"]["title"] == "测试"
    meta = load_meta()
    assert meta is not None
    assert meta["title"] == "测试"
    assert (tmp_path / "competitor" / "report.snapshot.json").is_file()
