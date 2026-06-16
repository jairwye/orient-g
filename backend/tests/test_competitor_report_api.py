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
        files={"file": ("minimal.md", md, "text/markdown")},
    )
    assert r.status_code == 403


def test_upload_and_get_flow(client: TestClient, tmp_path, monkeypatch):
    upload_md = _resolve_upload_md()
    if upload_md is None:
        upload_md = MINIMAL_FIXTURE
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))

    upload = client.post(
        "/api/competitor/admin/upload",
        headers=_headers("admin"),
        files={"file": (upload_md.name, upload_md.read_bytes(), "text/markdown")},
    )
    assert upload.status_code == 200, upload.text
    body = upload.json()
    assert body.get("ok") is True
    assert body.get("sections_parsed") == 10

    get_r = client.get("/api/competitor/report", headers=_headers("admin"))
    assert get_r.status_code == 200, get_r.text
    snap = get_r.json()
    assert len(snap.get("sections") or []) == 10

    summary = client.get("/api/competitor/summary", headers=_headers("admin"))
    assert summary.status_code == 200
    assert summary.json().get("has_report") is True


def test_fixture_fallback_when_no_upload(client: TestClient, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(settings, "competitor_fixture_fallback", True)
    r = client.get("/api/competitor/report", headers=_headers("admin"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body.get("sections") or []) == 10
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
