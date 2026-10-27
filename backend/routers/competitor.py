"""竞品财报：MD 上传 → Snapshot；多期次（1.2.3.e）；展示 API（view_business_dashboard）。"""
from __future__ import annotations

import jwt
import zipfile
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from backend.config import settings
from backend.routers.settings import _require_admin, _require_view_business_dashboard
from backend.services.competitor_edition_store import (
    ensure_edition,
    get_current,
    list_editions,
    migrate_legacy_competitor_layout,
    save_edition_meta,
    set_current,
    validate_edition_id,
)
from backend.services.competitor_report_parser import (
    CompetitorParseError,
    collect_sec09_anchor_stats,
    parse_markdown,
)
from backend.services.competitor_report_store import load_meta, save_snapshot, snapshot_for_api
from backend.services.vertical_ingest import (
    get_ingest_job,
    start_vertical_ingest_from_zip,
    start_vertical_pdf_only_from_zip,
)
from backend.services.vertical_pdf_store import load_vertical_pdf_meta, vertical_pdf_path
from backend.services.vertical_report_store import (
    VerticalNotAllowedError,
    load_vertical_meta,
    load_vertical_report,
    save_vertical_report,
)

router = APIRouter()


class CreateEditionBody(BaseModel):
    edition_id: str
    kind: str = "annual"
    period_label: Optional[str] = None
    has_vertical: Optional[bool] = None
    notes: Optional[str] = None


class SetCurrentBody(BaseModel):
    edition_id: str = Field(..., min_length=1)


def _get_username_from_request(request: Request) -> str:
    auth = request.headers.get("Authorization") or ""
    token = ""
    if auth.startswith("Bearer "):
        token = auth[7:].strip()
    token = token or (request.headers.get("X-Auth-Token") or "").strip()
    if not token:
        return ""
    try:
        payload = jwt.decode(token, settings.auth_secret, algorithms=["HS256"])
        return (payload.get("sub") or "").strip()
    except Exception:
        return ""


@router.get("/editions")
def competitor_editions(request: Request):
    """期次列表（含 is_current / has_vertical）。"""
    _require_view_business_dashboard(request)
    migrate_legacy_competitor_layout()
    return JSONResponse(
        content={"editions": list_editions(), "current": get_current()},
        headers={"Cache-Control": "no-store, no-cache"},
    )


@router.post("/admin/editions")
def competitor_admin_create_edition(request: Request, body: CreateEditionBody):
    """创建或更新期次 meta（不上传蓝本）。"""
    _require_admin(request)
    try:
        eid = validate_edition_id(body.edition_id)
        meta = ensure_edition(
            eid,
            kind=body.kind,
            period_label=body.period_label,
            has_vertical=body.has_vertical,
        )
        if body.notes is not None or body.period_label or body.has_vertical is not None:
            patch = dict(meta)
            if body.period_label:
                patch["period_label"] = body.period_label
            if body.has_vertical is not None:
                patch["has_vertical"] = body.has_vertical
            if body.notes is not None:
                patch["notes"] = body.notes
            meta = save_edition_meta(patch)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "edition": meta}


@router.post("/admin/current")
def competitor_admin_set_current(request: Request, body: SetCurrentBody):
    """设置侧栏默认期次（current.json）。"""
    _require_admin(request)
    try:
        eid = set_current(body.edition_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "edition_id": eid}


@router.post("/admin/upload")
async def competitor_admin_upload(
    request: Request,
    file: UploadFile = File(...),
    edition_id: Optional[str] = Form(None),
    set_as_current: Optional[str] = Form(None),
):
    """上传行业财报汇析 MD 到指定期次。仅管理员。edition_id 必填（1.2.3.e）。"""
    _require_admin(request)
    if not edition_id or not str(edition_id).strip():
        raise HTTPException(status_code=400, detail="请指定 edition_id（如 2025-annual、2026-h1）")
    if not file.filename or not file.filename.lower().endswith(".md"):
        raise HTTPException(status_code=400, detail="请上传 .md 文件")
    raw = await file.read()
    if len(raw) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="文件过大")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise HTTPException(status_code=400, detail="文件须为 UTF-8 编码") from e

    username = _get_username_from_request(request)
    if not username:
        raise HTTPException(status_code=401, detail="未登录")
    try:
        eid = validate_edition_id(str(edition_id).strip())
        snapshot, warnings = parse_markdown(
            text,
            source_filename=file.filename,
            uploaded_by=username,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except CompetitorParseError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    saved_eid = save_snapshot(raw, snapshot, edition_id=eid)
    make_current = str(set_as_current or "").strip().lower() in {"1", "true", "yes", "on"}
    if make_current:
        set_current(saved_eid)
    meta = snapshot.get("meta") or {}
    sec09_blocks = next((s.get("blocks") or [] for s in snapshot.get("sections") or [] if s.get("id") == "sec-09"), [])
    sec09_anchor_stats = collect_sec09_anchor_stats(sec09_blocks)
    return {
        "ok": True,
        "edition_id": saved_eid,
        "is_current": get_current() == saved_eid,
        "meta": {
            "title": meta.get("title"),
            "uploaded_at": meta.get("uploaded_at"),
            "uploaded_by": meta.get("uploaded_by"),
            "source_filename": meta.get("source_filename"),
            "edition_id": saved_eid,
            "period_label": meta.get("period_label"),
        },
        "warnings": warnings,
        "sections_parsed": len(snapshot.get("sections") or []),
        "sec09_anchor_stats": sec09_anchor_stats,
    }


@router.get("/report")
def competitor_report(request: Request, edition: Optional[str] = None):
    """返回 Snapshot；默认 current，可用 ?edition= 指定期次。"""
    _require_view_business_dashboard(request)
    migrate_legacy_competitor_layout()
    try:
        eid = validate_edition_id(edition) if edition else None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    snap = snapshot_for_api(eid)
    if not snap:
        raise HTTPException(status_code=404, detail="no_report")
    return JSONResponse(content=snap, headers={"Cache-Control": "no-store, no-cache"})


@router.get("/report/meta")
def competitor_report_meta(request: Request, edition: Optional[str] = None):
    _require_view_business_dashboard(request)
    migrate_legacy_competitor_layout()
    try:
        eid = validate_edition_id(edition) if edition else None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    meta = load_meta(eid)
    if not meta:
        raise HTTPException(status_code=404, detail="no_report")
    return JSONResponse(content=meta, headers={"Cache-Control": "no-store, no-cache"})


@router.get("/summary")
def competitor_summary(request: Request):
    """摘要始终基于 current。"""
    _require_view_business_dashboard(request)
    migrate_legacy_competitor_layout()
    meta = load_meta()
    if not meta:
        return {
            "updatedAt": None,
            "title": None,
            "company_count": 0,
            "has_report": False,
            "edition_id": get_current(),
        }
    return {
        "updatedAt": meta.get("uploaded_at"),
        "title": meta.get("title"),
        "company_count": meta.get("company_count", 0),
        "has_report": True,
        "edition_id": meta.get("edition_id") or get_current(),
        "period_label": meta.get("period_label"),
    }


def _parse_edition_query(edition: Optional[str]) -> Optional[str]:
    if not edition or not str(edition).strip():
        return None
    try:
        return validate_edition_id(str(edition).strip())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


def _require_vertical_edition_id(edition_id: Optional[str]) -> str:
    """上传纵向须指定期次且 has_vertical=true。"""
    if not edition_id or not str(edition_id).strip():
        raise HTTPException(status_code=400, detail="请指定 edition_id（如 2025-annual）")
    try:
        eid = validate_edition_id(str(edition_id).strip())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    from backend.services.competitor_edition_store import load_edition_meta

    meta = load_edition_meta(eid)
    if meta is None:
        raise HTTPException(
            status_code=400,
            detail="期次不存在，请先在财务后台创建期次后再上传纵向",
        )
    if meta.get("has_vertical") is False:
        raise HTTPException(status_code=400, detail="edition_has_no_vertical")
    return eid


@router.post("/admin/vertical-ingest")
async def competitor_admin_vertical_ingest(
    request: Request,
    file: UploadFile = File(...),
    edition_id: Optional[str] = Form(None),
):
    """上传 7 家纵向分析 PDF 的 zip，后台 Docling 解析并写入该期 vertical.snapshot.json。"""
    _require_admin(request)
    eid = _require_vertical_edition_id(edition_id)
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="请上传 .zip（内含各公司 .pdf）")
    raw = await file.read()
    if len(raw) > 120 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="zip 文件过大")
    username = _get_username_from_request(request)
    if not username:
        raise HTTPException(status_code=401, detail="未登录")
    try:
        job_id = start_vertical_ingest_from_zip(
            raw,
            uploaded_by=username,
            source_filename=file.filename,
            edition_id=eid,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except zipfile.BadZipFile as e:
        raise HTTPException(status_code=400, detail="无效的 zip 文件") from e

    return {"ok": True, "job_id": job_id, "status": "queued", "edition_id": eid}


@router.post("/admin/vertical-pdf-zip")
async def competitor_admin_vertical_pdf_zip(
    request: Request,
    file: UploadFile = File(...),
    edition_id: Optional[str] = Form(None),
):
    """上传 7 家纵向 PDF zip，仅存档供纵向页 PDF 直显（不调用 Docling）。"""
    _require_admin(request)
    eid = _require_vertical_edition_id(edition_id)
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="请上传 .zip（内含各公司 .pdf）")
    raw = await file.read()
    if len(raw) > 120 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="zip 文件过大")
    username = _get_username_from_request(request)
    if not username:
        raise HTTPException(status_code=401, detail="未登录")
    try:
        result = start_vertical_pdf_only_from_zip(
            raw,
            uploaded_by=username,
            source_filename=file.filename,
            edition_id=eid,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except zipfile.BadZipFile as e:
        raise HTTPException(status_code=400, detail="无效的 zip 文件") from e
    return {"ok": True, "edition_id": eid, **result}


@router.get("/vertical-pdf/meta")
def competitor_vertical_pdf_meta(request: Request, edition: Optional[str] = None):
    _require_view_business_dashboard(request)
    eid = _parse_edition_query(edition)
    try:
        meta = load_vertical_pdf_meta(eid)
    except VerticalNotAllowedError as e:
        raise HTTPException(status_code=404, detail=e.detail) from e
    if not meta:
        raise HTTPException(status_code=404, detail="no_vertical_pdfs")
    return JSONResponse(content=meta, headers={"Cache-Control": "no-store, no-cache"})


@router.get("/vertical-pdf/{company_id}")
def competitor_vertical_pdf_file(
    request: Request, company_id: str, edition: Optional[str] = None
):
    _require_view_business_dashboard(request)
    eid = _parse_edition_query(edition)
    try:
        path = vertical_pdf_path(company_id, edition_id=eid)
    except VerticalNotAllowedError as e:
        raise HTTPException(status_code=404, detail=e.detail) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not path:
        raise HTTPException(status_code=404, detail="pdf_not_found")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=path.name,
        headers={"Cache-Control": "no-store, no-cache"},
    )


@router.get("/admin/vertical-ingest/{job_id}")
def competitor_admin_vertical_ingest_status(request: Request, job_id: str):
    _require_admin(request)
    job = get_ingest_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job_not_found")
    return JSONResponse(content=job, headers={"Cache-Control": "no-store, no-cache"})


@router.post("/admin/upload-vertical")
async def competitor_admin_upload_vertical(
    request: Request,
    file: UploadFile = File(...),
    edition_id: Optional[str] = Form(None),
):
    """上传各公司纵向分析 MD，写入 editions/{edition_id}/vertical_report.md。仅管理员。"""
    _require_admin(request)
    eid = _require_vertical_edition_id(edition_id)
    if not file.filename or not file.filename.lower().endswith(".md"):
        raise HTTPException(status_code=400, detail="请上传 .md 文件")
    raw = await file.read()
    if len(raw) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="文件过大")
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise HTTPException(status_code=400, detail="文件须为 UTF-8 编码") from e

    username = _get_username_from_request(request)
    if not username:
        raise HTTPException(status_code=401, detail="未登录")
    try:
        doc = save_vertical_report(
            raw,
            source_filename=file.filename,
            uploaded_by=username,
            edition_id=eid,
        )
    except VerticalNotAllowedError as e:
        raise HTTPException(status_code=400, detail="edition_has_no_vertical") from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    meta = doc.get("meta") or {}
    return {
        "ok": True,
        "edition_id": eid,
        "meta": {
            "title": meta.get("title"),
            "uploaded_at": meta.get("uploaded_at"),
            "uploaded_by": meta.get("uploaded_by"),
            "source_filename": meta.get("source_filename"),
            "company_count": meta.get("company_count"),
            "edition_id": eid,
        },
        "warnings": list(doc.get("warnings") or []),
        "companies_parsed": len(doc.get("companies") or []),
    }


@router.get("/vertical-report")
def competitor_vertical_report(request: Request, edition: Optional[str] = None):
    """返回各公司纵向分析报告（结构化 JSON）；默认 current，?edition= 指定。"""
    _require_view_business_dashboard(request)
    eid = _parse_edition_query(edition)
    try:
        doc = load_vertical_report(eid)
    except VerticalNotAllowedError as e:
        raise HTTPException(status_code=404, detail=e.detail) from e
    if not doc:
        raise HTTPException(status_code=404, detail="no_vertical_report")
    return JSONResponse(content=doc, headers={"Cache-Control": "no-store, no-cache"})


@router.get("/vertical-report/meta")
def competitor_vertical_report_meta(request: Request, edition: Optional[str] = None):
    _require_view_business_dashboard(request)
    eid = _parse_edition_query(edition)
    try:
        meta = load_vertical_meta(eid)
    except VerticalNotAllowedError as e:
        raise HTTPException(status_code=404, detail=e.detail) from e
    if not meta:
        raise HTTPException(status_code=404, detail="no_vertical_report")
    return JSONResponse(content=meta, headers={"Cache-Control": "no-store, no-cache"})
