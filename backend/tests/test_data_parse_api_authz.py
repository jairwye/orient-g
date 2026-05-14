import io

import jwt
import pytest
from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app
from backend.services.data_parse_session import create_session


def _minimal_xlsx_bytes() -> bytes:
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["A", "B"])
    ws.append([1, 2])
    buf = io.BytesIO()
    wb.save(buf)
    data = buf.getvalue()
    assert len(data) >= 100
    return data


def _headers(username: str) -> dict[str, str]:
    token = jwt.encode({"sub": username}, settings.auth_secret, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def test_session_access_requires_owner():
    client = TestClient(app)
    upload = client.post(
        "/api/data-parse/upload",
        headers=_headers("alice"),
        files={"file": ("fixture_min.xlsx", _minimal_xlsx_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert upload.status_code == 200, upload.text
    sid = upload.json()["session_id"]

    unauthorized = client.get(f"/api/data-parse/session/{sid}")
    assert unauthorized.status_code == 401, unauthorized.text

    forbidden = client.get(f"/api/data-parse/session/{sid}", headers=_headers("bob"))
    assert forbidden.status_code == 403, forbidden.text

    ok = client.get(f"/api/data-parse/session/{sid}", headers=_headers("alice"))
    assert ok.status_code == 200, ok.text


def test_legacy_session_is_claimed_once_when_enabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "data_parse_legacy_session_claim_enabled", True)
    sid = create_session(
        {
            "tables": {"Sheet1": {"headers": ["A"], "rows": [[1]]}},
            "table_schemas": [{"sheet_name": "Sheet1", "headers": ["A"], "row_count": 1}],
        },
        owner_username=None,
    )
    client = TestClient(app)
    first = client.get(f"/api/data-parse/session/{sid}", headers=_headers("alice"))
    assert first.status_code == 200, first.text
    second = client.get(f"/api/data-parse/session/{sid}", headers=_headers("bob"))
    assert second.status_code == 403, second.text

