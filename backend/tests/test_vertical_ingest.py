"""vertical zip ingest API（mock Docling）与 PDF 仅存档。"""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from unittest.mock import patch

import jwt
import pytest
from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app
from backend.services.vertical_company_resolve import reset_filename_rules_cache
from backend.services.vertical_ingest import run_vertical_ingest_job

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"

CN_PDF_NAMES = [
    "三七互娱2025年度报告分析解读.pdf",
    "掌趣科技2025年度报告分析解读.pdf",
    "完美世界2025年度报告分析解读.pdf",
    "塔人网络2025年度报告分析解读.pdf",
    "华清飞扬2025年度报告分析解读.pdf",
    "像素软件2025年度报告分析解读.pdf",
    "绿岸网络2025年度报告分析解读.pdf",
]


def _token(username: str) -> str:
    return jwt.encode({"sub": username}, settings.auth_secret, algorithm="HS256")


def _headers(username: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(username)}"}


def _make_zip(*pdfs: tuple[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in pdfs:
            zf.writestr(name, data)
    return buf.getvalue()


def _make_gbk_zip(name_proper: str, data: bytes) -> bytes:
    """模拟 Windows 资源管理器：zip 内文件名为 GBK 字节、无 UTF-8 flag。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zi = zipfile.ZipInfo(filename=name_proper.encode("gbk").decode("cp437"))
        zi.flag_bits = 0
        zi.compress_type = zipfile.ZIP_DEFLATED
        zf.writestr(zi, data)
    return buf.getvalue()


@pytest.fixture
def client():
    return TestClient(app)


def test_vertical_ingest_requires_zip(client: TestClient):
    r = client.post(
        "/api/competitor/admin/vertical-ingest",
        headers=_headers("admin"),
        files={"file": ("x.md", b"x", "text/markdown")},
    )
    assert r.status_code == 400


def test_vertical_ingest_gbk_zip_filenames(tmp_path, monkeypatch):
    """Windows 资源管理器 zip：中文文件名 GBK → cp437 乱码后应能识别公司。"""
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))

    def fake_convert(source_path: Path, *, output_dir: Path, **kwargs):
        output_dir.mkdir(parents=True, exist_ok=True)
        md_path = output_dir / "full.md"
        json_path = output_dir / "full.json"
        md_path.write_text("### 一、公司简介\n\n正文\n", encoding="utf-8")
        json_path.write_text("{}", encoding="utf-8")
        from backend.services.docling_runner import DoclingResult

        return DoclingResult(markdown_path=md_path, json_path=json_path, docling_version="test")

    proper = "wm2025年度报告分析解读.pdf"
    zip_bytes = _make_gbk_zip(proper, b"%PDF-1.4 fake")

    with patch("backend.services.vertical_ingest.convert_to_md_and_json", fake_convert):
        from backend.services.vertical_ingest import (
            _extract_pdfs_from_zip,
            _job_dir,
            _write_job_status,
            run_vertical_ingest_job,
        )
        from datetime import datetime, timezone

        job_id = "ving_gbk_test"
        job_dir = _job_dir(job_id)
        entries = _extract_pdfs_from_zip(zip_bytes, job_dir)
        assert entries[0][0] == proper
        _write_job_status(
            job_id,
            {
                "job_id": job_id,
                "status": "queued",
                "stage": "queued",
                "progress": 0,
                "source_filename": "7pdf.zip",
                "uploaded_by": "admin",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "warnings": [],
            },
        )
        run_vertical_ingest_job(job_id, uploaded_by="admin", source_filename="7pdf.zip")

    job = json.loads((tmp_path / "competitor" / "vertical" / "ingest" / job_id / "status.json").read_text(encoding="utf-8"))
    assert job["status"] == "completed", job.get("error")


def test_vertical_ingest_job_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))

    md_sample = """
## 一、公司简介
测试公司。

## 五、核心财务表现

| 指标 | 2025 | 2024 |
| --- | --- | --- |
| 收入 | 1 | 2 |
"""

    def fake_convert(source_path: Path, *, output_dir: Path, **kwargs):
        output_dir.mkdir(parents=True, exist_ok=True)
        md_path = output_dir / "full.md"
        json_path = output_dir / "full.json"
        md_path.write_text(md_sample, encoding="utf-8")
        json_path.write_text("{}", encoding="utf-8")
        from backend.services.docling_runner import DoclingResult

        return DoclingResult(markdown_path=md_path, json_path=json_path, docling_version="test")

    zip_bytes = _make_zip(("wm2025_report.pdf", b"%PDF-1.4 fake"))

    with patch("backend.services.vertical_ingest.convert_to_md_and_json", fake_convert):
        from backend.services.vertical_ingest import (
            _extract_pdfs_from_zip,
            _job_dir,
            _write_job_status,
            run_vertical_ingest_job,
        )
        from datetime import datetime, timezone

        job_id = "ving_test123"
        job_dir = _job_dir(job_id)
        _extract_pdfs_from_zip(zip_bytes, job_dir)
        _write_job_status(
            job_id,
            {
                "job_id": job_id,
                "status": "queued",
                "stage": "queued",
                "progress": 0,
                "source_filename": "vertical.zip",
                "uploaded_by": "admin",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "warnings": [],
            },
        )
        run_vertical_ingest_job(job_id, uploaded_by="admin", source_filename="vertical.zip")

    job = json.loads((tmp_path / "competitor" / "vertical" / "ingest" / job_id / "status.json").read_text(encoding="utf-8"))
    assert job["status"] == "completed"
    snap_path = tmp_path / "competitor" / "vertical.snapshot.json"
    assert snap_path.is_file()
    snap = json.loads(snap_path.read_text(encoding="utf-8"))
    assert len(snap.get("companies") or []) >= 1


def test_vertical_pdf_zip_cn_filenames(client: TestClient, tmp_path, monkeypatch):
    """POST vertical-pdf-zip：内网中文 PDF 文件名须全部识别。"""
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(settings, "vertical_builtin_filename_rules", None)
    reset_filename_rules_cache()
    pdfs = tuple((name, b"%PDF-1.4 x") for name in CN_PDF_NAMES)
    zip_bytes = _make_zip(*pdfs)
    r = client.post(
        "/api/competitor/admin/vertical-pdf-zip",
        headers=_headers("admin"),
        files={"file": ("7pdf.zip", zip_bytes, "application/zip")},
    )
    reset_filename_rules_cache()
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("ok") is True
    assert data.get("companies_parsed") == 7
    meta_path = tmp_path / "competitor" / "vertical" / "pdfs" / "meta.json"
    assert meta_path.is_file()
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta.get("company_count") == 7
