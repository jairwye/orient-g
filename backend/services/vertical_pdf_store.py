"""纵向对比：原 PDF 存档与读取（PDF 直显模式，不经 Docling）。"""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.services.competitor_report_store import competitor_dir

VERTICAL_PDF_DIRNAME = "vertical/pdfs"
META_FILENAME = "meta.json"
_COMPANY_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


def vertical_pdfs_dir() -> Path:
    return competitor_dir() / "vertical" / "pdfs"


def _meta_path() -> Path:
    return vertical_pdfs_dir() / META_FILENAME


def _safe_company_id(company_id: str) -> str:
    cid = (company_id or "").strip().lower()
    if not cid or not _COMPANY_ID_RE.fullmatch(cid):
        raise ValueError(f"invalid company_id: {company_id!r}")
    return cid


def persist_vertical_pdfs(
    entries: list[tuple[str, Path, str]],
    *,
    uploaded_by: str,
    source_filename: str,
) -> dict[str, Any]:
    """将 (company_id, pdf_path, display_name) 写入 uploads/competitor/vertical/pdfs/{id}.pdf。"""
    d = vertical_pdfs_dir()
    d.mkdir(parents=True, exist_ok=True)
    companies: list[dict[str, str]] = []
    new_ids: set[str] = set()
    for cid, src, display_name in entries:
        safe = _safe_company_id(cid)
        new_ids.add(safe)
        dest = d / f"{safe}.pdf"
        shutil.copy2(src, dest)
        companies.append({"id": safe, "name": display_name, "filename": dest.name})
    for stale in d.glob("*.pdf"):
        if stale.stem not in new_ids:
            stale.unlink(missing_ok=True)
    meta = {
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "uploaded_by": uploaded_by,
        "source_filename": source_filename,
        "company_count": len(companies),
        "companies": companies,
    }
    _meta_path().write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def load_vertical_pdf_meta() -> dict[str, Any] | None:
    path = _meta_path()
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def list_vertical_pdf_ids() -> list[str]:
    d = vertical_pdfs_dir()
    if not d.is_dir():
        return []
    return sorted(p.stem for p in d.glob("*.pdf") if p.is_file())


def vertical_pdf_path(company_id: str) -> Path | None:
    safe = _safe_company_id(company_id)
    path = vertical_pdfs_dir() / f"{safe}.pdf"
    return path if path.is_file() else None


def has_vertical_pdfs() -> bool:
    return bool(list_vertical_pdf_ids())
