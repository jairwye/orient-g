"""1.2.3.e Phase e-3：纵向报告/PDF 按 edition 绑定与 has_vertical。"""
from __future__ import annotations

import json
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app
from backend.services import competitor_edition_store as ed
from backend.services import vertical_pdf_store as vps
from backend.services import vertical_report_store as vrs

VERTICAL_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "vertical_report_minimal.md"


@pytest.fixture
def client():
    return TestClient(app)


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
    monkeypatch.setattr(
        "backend.services.vertical_report_store.settings.upload_dir",
        str(tmp_path),
    )
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(settings, "competitor_fixture_fallback", False)
    return tmp_path


def _headers(username: str = "admin") -> dict[str, str]:
    token = jwt.encode({"sub": username}, settings.auth_secret, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def test_vertical_paths_prefer_edition_dir(upload_root):
    ed.ensure_edition("2025-annual", kind="annual", has_vertical=True)
    ed.set_current("2025-annual")
    snap = {"version": 1, "meta": {"title": "ed"}, "companies": [], "warnings": []}
    vrs.save_vertical_snapshot(snap, edition_id="2025-annual")
    target = upload_root / "competitor" / "editions" / "2025-annual" / "vertical.snapshot.json"
    assert target.is_file()
    assert not (upload_root / "competitor" / "vertical.snapshot.json").exists()
    loaded = vrs.load_vertical_report(edition_id="2025-annual")
    assert loaded is not None
    assert loaded["meta"]["title"] == "ed"


def test_vertical_legacy_root_fallback_for_2025_annual(upload_root):
    ed.ensure_edition("2025-annual", kind="annual", has_vertical=True)
    ed.set_current("2025-annual")
    root = upload_root / "competitor"
    root.mkdir(parents=True, exist_ok=True)
    (root / "vertical.snapshot.json").write_text(
        json.dumps(
            {"version": 1, "meta": {"title": "legacy-root"}, "companies": [], "warnings": []},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    loaded = vrs.load_vertical_report(edition_id="2025-annual")
    assert loaded is not None
    assert loaded["meta"]["title"] == "legacy-root"


def test_has_vertical_false_blocks_load(upload_root):
    ed.ensure_edition("2026-h1", kind="interim", has_vertical=False)
    ed.set_current("2026-h1")
    with pytest.raises(vrs.VerticalNotAllowedError) as ei:
        vrs.load_vertical_report(edition_id="2026-h1")
    assert ei.value.detail == "no_vertical"


def test_migrate_moves_root_vertical_into_2025_annual(upload_root):
    root = upload_root / "competitor"
    root.mkdir(parents=True)
    (root / "report.snapshot.json").write_text(
        json.dumps(
            {
                "version": 1,
                "meta": {"title": "h", "period": "2025", "currency_unit": "万元"},
                "companies": [],
                "sections": [],
                "warnings": [],
            }
        ),
        encoding="utf-8",
    )
    (root / "vertical.snapshot.json").write_text("{}", encoding="utf-8")
    (root / "vertical_report.md").write_text("# v\n", encoding="utf-8")
    pdf_dir = root / "vertical" / "pdfs"
    pdf_dir.mkdir(parents=True)
    (pdf_dir / "wm.pdf").write_bytes(b"%PDF")
    (pdf_dir / "meta.json").write_text("{}", encoding="utf-8")

    result = ed.migrate_legacy_competitor_layout()
    assert result["migrated"] is True
    target = root / "editions" / "2025-annual"
    assert (target / "vertical.snapshot.json").is_file()
    assert (target / "vertical_report.md").is_file()
    assert (target / "vertical" / "pdfs" / "wm.pdf").is_file()
    assert not (root / "vertical.snapshot.json").exists()
    assert not (root / "vertical_report.md").exists()
    # 幂等：根已无纵向，再次迁移不报错
    again = ed.migrate_legacy_competitor_layout()
    assert (target / "vertical.snapshot.json").is_file()


def test_persist_pdf_scoped_to_edition(upload_root):
    ed.ensure_edition("2025-annual", kind="annual", has_vertical=True)
    pdf = upload_root / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    meta = vps.persist_vertical_pdfs(
        [("wm", pdf, "完美世界")],
        uploaded_by="admin",
        source_filename="x.zip",
        edition_id="2025-annual",
    )
    assert meta["company_count"] == 1
    dest = (
        upload_root
        / "competitor"
        / "editions"
        / "2025-annual"
        / "vertical"
        / "pdfs"
        / "wm.pdf"
    )
    assert dest.is_file()
    assert vps.vertical_pdf_path("wm", edition_id="2025-annual") == dest


def test_api_vertical_no_vertical_404(client: TestClient, upload_root, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(upload_root))
    ed.ensure_edition("2026-h1", kind="interim", has_vertical=False)
    ed.set_current("2026-h1")
    r = client.get(
        "/api/competitor/vertical-report?edition=2026-h1",
        headers=_headers(),
    )
    assert r.status_code == 404
    assert r.json().get("detail") == "no_vertical"

    r2 = client.get(
        "/api/competitor/vertical-pdf/meta?edition=2026-h1",
        headers=_headers(),
    )
    assert r2.status_code == 404
    assert r2.json().get("detail") == "no_vertical"


def test_api_upload_vertical_requires_edition_and_has_vertical(
    client: TestClient, upload_root, monkeypatch
):
    monkeypatch.setattr(settings, "upload_dir", str(upload_root))
    ed.ensure_edition("2026-h1", kind="interim", has_vertical=False)
    ed.ensure_edition("2025-annual", kind="annual", has_vertical=True)
    ed.set_current("2026-h1")

    missing = client.post(
        "/api/competitor/admin/upload-vertical",
        headers=_headers(),
        files={"file": ("vertical.md", VERTICAL_FIXTURE.read_bytes(), "text/markdown")},
    )
    assert missing.status_code == 400
    assert "edition_id" in str(missing.json().get("detail", "")).lower()

    blocked = client.post(
        "/api/competitor/admin/upload-vertical",
        headers=_headers(),
        data={"edition_id": "2026-h1"},
        files={"file": ("vertical.md", VERTICAL_FIXTURE.read_bytes(), "text/markdown")},
    )
    assert blocked.status_code == 400
    detail = blocked.json().get("detail")
    assert detail == "edition_has_no_vertical" or "no_vertical" in str(detail).lower()

    ok = client.post(
        "/api/competitor/admin/upload-vertical",
        headers=_headers(),
        data={"edition_id": "2025-annual"},
        files={"file": ("vertical.md", VERTICAL_FIXTURE.read_bytes(), "text/markdown")},
    )
    assert ok.status_code == 200, ok.text
    get_r = client.get(
        "/api/competitor/vertical-report?edition=2025-annual",
        headers=_headers(),
    )
    assert get_r.status_code == 200
    assert len(get_r.json().get("companies") or []) == 7
    # current 为 2026-h1 无纵向 → 无参默认 current 应 404 no_vertical
    cur = client.get("/api/competitor/vertical-report", headers=_headers())
    assert cur.status_code == 404
    assert cur.json().get("detail") == "no_vertical"
