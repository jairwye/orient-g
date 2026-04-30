"""HTTP 层：/api/data-parse/upload 返回 session_id（可用手动或 CI 联调）。"""

import io

import pytest
from fastapi.testclient import TestClient

from backend.main import app


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


def test_upload_excel_returns_session_id():
    client = TestClient(app)
    content = _minimal_xlsx_bytes()
    res = client.post(
        "/api/data-parse/upload",
        files={"file": ("fixture_min.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert isinstance(body.get("session_id"), str) and len(body["session_id"]) >= 8
    assert "table_schemas" in body
