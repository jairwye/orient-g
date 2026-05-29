"""RAG 包导出：中文文件名 Content-Disposition 与 zip 下载。"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from starlette.responses import Response

from backend.services.rag_packages import _attachment_content_disposition, export_package_zip


def test_attachment_content_disposition_supports_unicode():
    header = _attachment_content_disposition("三七互娱-2024年_cn_kb.zip")
    # Starlette 响应头必须是 latin-1；含 filename* 供现代浏览器显示中文
    Response(content=b"x", headers={"Content-Disposition": header})
    assert "filename*=" in header
    assert "attachment" in header


def test_export_package_zip_with_chinese_name(tmp_path, monkeypatch):
    from backend.services import rag_packages as rp

    tenant_id = "tenant1"
    package_id = "rp_test_cn"
    root = tmp_path / "uploads" / "kb_bigpdf_tasks" / tenant_id / "t1"
    (root / "kb" / "sections").mkdir(parents=True)
    (root / "kb" / "sections" / "s0001.md").write_text("# hi", encoding="utf-8")
    (root / "kb" / "manifest.json").write_text("{}", encoding="utf-8")

    storage_rel = str(root.relative_to(tmp_path / "uploads")).replace("\\", "/")

    def fake_pkg_row(tid: str, pid: str):
        return {
            "package_id": pid,
            "name": "三七互娱-2024年",
            "storage_path": storage_rel,
        }

    monkeypatch.setattr(rp, "_pkg_row", fake_pkg_row)
    monkeypatch.setattr(rp.settings, "upload_dir", str(tmp_path / "uploads"))

    data, filename = export_package_zip(tenant_id, package_id, "cn_kb")
    assert filename.endswith("_cn_kb.zip")
    assert "三七" in filename
    assert len(data) > 0
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = z.namelist()
        assert any(n.endswith("s0001.md") for n in names)
