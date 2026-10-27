"""竞品财报 API 集成测。"""
from __future__ import annotations

from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
MINIMAL_FIXTURE = FIXTURE_DIR / "competitor_report_minimal.md"
YYCQ_FIXTURE = FIXTURE_DIR / "competitor_report_yycq.md"
YYCQ_UPLOAD = (
    Path(__file__).resolve().parents[2]
    / "uploads"
    / "行业财报汇析-2025年_数据文档_YYCQ版.md"
)


def _resolve_upload_md() -> Path | None:
    for p in (YYCQ_UPLOAD, YYCQ_FIXTURE):
        if p.is_file():
            return p
    return None


def _token(username: str) -> str:
    return jwt.encode({"sub": username}, settings.auth_secret, algorithm="HS256")


def _headers(username: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(username)}"}


@pytest.fixture
def client():
    return TestClient(app)


def test_report_requires_auth(client: TestClient):
    r = client.get("/api/competitor/report")
    assert r.status_code == 401


def test_report_forbidden_without_dashboard(client: TestClient):
    r = client.get("/api/competitor/report", headers=_headers("nobody_no_access"))
    assert r.status_code == 403


def test_upload_forbidden_non_admin(client: TestClient, monkeypatch):
    from backend.routers import settings as settings_mod

    monkeypatch.setattr(settings_mod, "_is_admin_user", lambda _u: False)
    md = MINIMAL_FIXTURE.read_bytes()
    r = client.post(
        "/api/competitor/admin/upload",
        headers=_headers("finance_user"),
        data={"edition_id": "2025-annual"},
        files={"file": ("minimal.md", md, "text/markdown")},
    )
    assert r.status_code == 403


def test_upload_requires_edition_id(client: TestClient, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    md = MINIMAL_FIXTURE.read_bytes()
    r = client.post(
        "/api/competitor/admin/upload",
        headers=_headers("admin"),
        files={"file": ("minimal.md", md, "text/markdown")},
    )
    assert r.status_code == 400
    assert "edition_id" in (r.json().get("detail") or "")


def test_upload_and_get_flow(client: TestClient, tmp_path, monkeypatch):
    upload_md = _resolve_upload_md()
    if upload_md is None:
        upload_md = MINIMAL_FIXTURE
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))

    upload = client.post(
        "/api/competitor/admin/upload",
        headers=_headers("admin"),
        data={"edition_id": "2025-annual", "set_as_current": "true"},
        files={"file": (upload_md.name, upload_md.read_bytes(), "text/markdown")},
    )
    assert upload.status_code == 200, upload.text
    body = upload.json()
    assert body.get("ok") is True
    assert body.get("sections_parsed") == 9
    assert body.get("edition_id") == "2025-annual"

    get_r = client.get("/api/competitor/report", headers=_headers("admin"))
    assert get_r.status_code == 200, get_r.text
    snap = get_r.json()
    assert len(snap.get("sections") or []) == 9
    assert snap.get("meta", {}).get("edition_id") == "2025-annual"

    summary = client.get("/api/competitor/summary", headers=_headers("admin"))
    assert summary.status_code == 200
    assert summary.json().get("has_report") is True


def test_multi_edition_current_and_query(client: TestClient, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    md = MINIMAL_FIXTURE.read_bytes()

    r1 = client.post(
        "/api/competitor/admin/upload",
        headers=_headers("admin"),
        data={"edition_id": "2025-annual", "set_as_current": "true"},
        files={"file": ("a.md", md, "text/markdown")},
    )
    assert r1.status_code == 200, r1.text

    client.post(
        "/api/competitor/admin/editions",
        headers=_headers("admin"),
        json={
            "edition_id": "2026-h1",
            "kind": "interim",
            "period_label": "2026 半年报",
            "has_vertical": False,
        },
    )
    r2 = client.post(
        "/api/competitor/admin/upload",
        headers=_headers("admin"),
        data={"edition_id": "2026-h1"},
        files={"file": ("b.md", md, "text/markdown")},
    )
    assert r2.status_code == 200, r2.text

    # 未切 current：默认仍是 2025
    cur = client.get("/api/competitor/report", headers=_headers("admin"))
    assert cur.json()["meta"]["edition_id"] == "2025-annual"

    set_c = client.post(
        "/api/competitor/admin/current",
        headers=_headers("admin"),
        json={"edition_id": "2026-h1"},
    )
    assert set_c.status_code == 200, set_c.text

    cur2 = client.get("/api/competitor/report", headers=_headers("admin"))
    assert cur2.json()["meta"]["edition_id"] == "2026-h1"

    hist = client.get("/api/competitor/report?edition=2025-annual", headers=_headers("admin"))
    assert hist.status_code == 200
    assert hist.json()["meta"]["edition_id"] == "2025-annual"

    editions = client.get("/api/competitor/editions", headers=_headers("admin"))
    assert editions.status_code == 200
    body = editions.json()
    assert body.get("current") == "2026-h1"
    assert len(body.get("editions") or []) == 2


def test_explicit_edition_missing_snapshot_is_404(client: TestClient, tmp_path, monkeypatch):
    """显式 ?edition= 无快照时 404，不得返回 current 或 fixture。"""
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(settings, "competitor_fixture_fallback", True)
    md = MINIMAL_FIXTURE.read_bytes()

    up = client.post(
        "/api/competitor/admin/upload",
        headers=_headers("admin"),
        data={"edition_id": "2025-annual", "set_as_current": "true"},
        files={"file": ("a.md", md, "text/markdown")},
    )
    assert up.status_code == 200, up.text

    client.post(
        "/api/competitor/admin/editions",
        headers=_headers("admin"),
        json={
            "edition_id": "2026-h1",
            "kind": "interim",
            "period_label": "2026 半年报",
            "has_vertical": False,
        },
    )

    missing = client.get(
        "/api/competitor/report?edition=2026-h1",
        headers=_headers("admin"),
    )
    assert missing.status_code == 404
    assert missing.json().get("detail") == "no_report"

    # current 仍可读
    cur = client.get("/api/competitor/report", headers=_headers("admin"))
    assert cur.status_code == 200
    assert cur.json()["meta"]["edition_id"] == "2025-annual"


def test_vertical_upload_rejects_unknown_edition(client: TestClient, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    r = client.post(
        "/api/competitor/admin/upload-vertical",
        headers=_headers("admin"),
        data={"edition_id": "2099-ghost"},
        files={"file": ("v.md", b"# none\n", "text/markdown")},
    )
    assert r.status_code == 400
    detail = r.json().get("detail") or ""
    assert "期次不存在" in detail


def test_fixture_fallback_when_no_upload(client: TestClient, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(settings, "competitor_fixture_fallback", True)
    r = client.get("/api/competitor/report", headers=_headers("admin"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body.get("sections") or []) == 9
    assert body.get("meta", {}).get("data_source") == "fixture"


def test_fixture_fallback_off_in_production(client: TestClient, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "competitor_fixture_fallback", None)
    r = client.get("/api/competitor/report", headers=_headers("admin"))
    assert r.status_code == 404


def test_report_404_when_empty(client: TestClient, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(settings, "competitor_fixture_fallback", False)
    r = client.get("/api/competitor/report", headers=_headers("admin"))
    assert r.status_code == 404
    assert r.json().get("detail") == "no_report"


VERTICAL_FIXTURE = FIXTURE_DIR / "vertical_report_minimal.md"


def test_vertical_upload_forbidden_non_admin(client: TestClient, monkeypatch):
    from backend.routers import settings as settings_mod

    monkeypatch.setattr(settings_mod, "_is_admin_user", lambda _u: False)
    r = client.post(
        "/api/competitor/admin/upload-vertical",
        headers=_headers("finance_user"),
        files={"file": ("vertical.md", VERTICAL_FIXTURE.read_bytes(), "text/markdown")},
    )
    assert r.status_code == 403


def test_vertical_report_requires_auth(client: TestClient):
    r = client.get("/api/competitor/vertical-report")
    assert r.status_code == 401


def test_vertical_fixture_fallback_when_no_upload(client: TestClient, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(settings, "competitor_fixture_fallback", True)
    r = client.get("/api/competitor/vertical-report", headers=_headers("admin"))
    assert r.status_code == 200, r.text
    assert r.json().get("meta", {}).get("data_source") == "fixture"


def test_vertical_upload_and_get_flow(client: TestClient, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(settings, "competitor_fixture_fallback", False)

    from backend.services import competitor_edition_store as ed

    ed.ensure_edition("2025-annual", kind="annual", has_vertical=True)
    ed.set_current("2025-annual")

    upload = client.post(
        "/api/competitor/admin/upload-vertical",
        headers=_headers("admin"),
        data={"edition_id": "2025-annual"},
        files={"file": ("vertical.md", VERTICAL_FIXTURE.read_bytes(), "text/markdown")},
    )
    assert upload.status_code == 200, upload.text
    body = upload.json()
    assert body.get("ok") is True
    assert body.get("companies_parsed") == 7
    assert body.get("edition_id") == "2025-annual"

    get_r = client.get("/api/competitor/vertical-report", headers=_headers("admin"))
    assert get_r.status_code == 200, get_r.text
    doc = get_r.json()
    assert len(doc.get("companies") or []) == 7

    meta_r = client.get("/api/competitor/vertical-report/meta", headers=_headers("admin"))
    assert meta_r.status_code == 200
    assert meta_r.json().get("company_count") == 7


def test_vertical_report_404_when_empty(client: TestClient, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "competitor_fixture_fallback", None)
    r = client.get("/api/competitor/vertical-report", headers=_headers("admin"))
    assert r.status_code == 404
    assert r.json().get("detail") == "no_vertical_report"
