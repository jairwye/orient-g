"""纵向对比：原 PDF 存档与读取（按 edition；兼容根目录旧路径）。"""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.services.competitor_edition_store import (
    LEGACY_EDITION_ID,
    edition_dir,
    get_current,
    load_edition_meta,
    validate_edition_id,
)
from backend.services.competitor_report_store import competitor_dir
from backend.services.vertical_report_store import VerticalNotAllowedError

VERTICAL_PDF_DIRNAME = "vertical/pdfs"
META_FILENAME = "meta.json"
_COMPANY_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


def _resolve_eid(edition_id: str | None) -> str | None:
    if edition_id:
        return validate_edition_id(edition_id)
    return get_current()


def _assert_allows(edition_id: str | None) -> str | None:
    eid = _resolve_eid(edition_id)
    if not eid:
        return None
    meta = load_edition_meta(eid)
    if meta is not None and meta.get("has_vertical") is False:
        raise VerticalNotAllowedError("no_vertical", edition_id=eid)
    return eid


def vertical_pdfs_dir(edition_id: str | None = None) -> Path:
    eid = _resolve_eid(edition_id)
    if eid:
        return edition_dir(eid) / "vertical" / "pdfs"
    return competitor_dir() / "vertical" / "pdfs"


def _legacy_pdfs_dir() -> Path:
    return competitor_dir() / "vertical" / "pdfs"


def _meta_path(edition_id: str | None = None) -> Path:
    return vertical_pdfs_dir(edition_id) / META_FILENAME


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
    edition_id: str | None = None,
) -> dict[str, Any]:
    """将 (company_id, pdf_path, display_name) 写入 editions/{id}/vertical/pdfs/。"""
    eid = _assert_allows(edition_id)
    if not eid:
        raise ValueError("请指定 edition_id（或先设置 current 期次）")
    d = vertical_pdfs_dir(eid)
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
        "edition_id": eid,
    }
    _meta_path(eid).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def load_vertical_pdf_meta(edition_id: str | None = None) -> dict[str, Any] | None:
    eid = _assert_allows(edition_id)
    path = _meta_path(eid)
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    if eid == LEGACY_EDITION_ID:
        legacy = _legacy_pdfs_dir() / META_FILENAME
        if legacy.is_file():
            return json.loads(legacy.read_text(encoding="utf-8"))
    return None


def list_vertical_pdf_ids(edition_id: str | None = None) -> list[str]:
    eid = _assert_allows(edition_id)
    d = vertical_pdfs_dir(eid)
    if d.is_dir():
        ids = sorted(p.stem for p in d.glob("*.pdf") if p.is_file())
        if ids:
            return ids
    if eid == LEGACY_EDITION_ID:
        legacy = _legacy_pdfs_dir()
        if legacy.is_dir():
            return sorted(p.stem for p in legacy.glob("*.pdf") if p.is_file())
    return []


def vertical_pdf_path(company_id: str, edition_id: str | None = None) -> Path | None:
    eid = _assert_allows(edition_id)
    safe = _safe_company_id(company_id)
    path = vertical_pdfs_dir(eid) / f"{safe}.pdf"
    if path.is_file():
        return path
    if eid == LEGACY_EDITION_ID:
        legacy = _legacy_pdfs_dir() / f"{safe}.pdf"
        if legacy.is_file():
            return legacy
    return None


def has_vertical_pdfs(edition_id: str | None = None) -> bool:
    return bool(list_vertical_pdf_ids(edition_id))
