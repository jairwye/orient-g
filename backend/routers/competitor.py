"""竞品财报：MD 上传 → Snapshot；展示 API（view_business_dashboard）。"""
from __future__ import annotations

import jwt
import zipfile
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from backend.config import settings
from backend.routers.settings import _require_admin, _require_view_business_dashboard
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
from backend.services.vertical_report_store import load_vertical_meta, load_vertical_report, save_vertical_report

router = APIRouter()


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


@router.post("/admin/upload")
async def competitor_admin_upload(request: Request, file: UploadFile = File(...)):
    """上传行业财报汇析 MD，覆盖当前 Snapshot。仅管理员。"""
    _require_admin(request)
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
        snapshot, warnings = parse_markdown(
            text,
            source_filename=file.filename,
            uploaded_by=username,
        )
    except CompetitorParseError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    save_snapshot(raw, snapshot)
    meta = snapshot.get("meta") or {}
    sec09_blocks = next((s.get("blocks") or [] for s in snapshot.get("sections") or [] if s.get("id") == "sec-09"), [])
    sec09_anchor_stats = collect_sec09_anchor_stats(sec09_blocks)
    return {
        "ok": True,
        "meta": {
            "title": meta.get("title"),
            "uploaded_at": meta.get("uploaded_at"),
            "uploaded_by": meta.get("uploaded_by"),
            "source_filename": meta.get("source_filename"),
        },
        "warnings": warnings,
        "sections_parsed": len(snapshot.get("sections") or []),
        "sec09_anchor_stats": sec09_anchor_stats,
    }


@router.get("/report")
def competitor_report(request: Request):
    """返回当前生效 Snapshot。"""
    _require_view_business_dashboard(request)
    snap = snapshot_for_api()
    if not snap:
        raise HTTPException(status_code=404, detail="no_report")
    return JSONResponse(content=snap, headers={"Cache-Control": "no-store, no-cache"})


@router.get("/report/meta")
def competitor_report_meta(request: Request):
    _require_view_business_dashboard(request)
    meta = load_meta()
    if not meta:
        raise HTTPException(status_code=404, detail="no_report")
    return JSONResponse(content=meta, headers={"Cache-Control": "no-store, no-cache"})


@router.get("/summary")
def competitor_summary(request: Request):
    _require_view_business_dashboard(request)
    meta = load_meta()
    if not meta:
        return {
            "updatedAt": None,
            "title": None,
            "company_count": 0,
            "has_report": False,
        }
    return {
        "updatedAt": meta.get("uploaded_at"),
        "title": meta.get("title"),
        "company_count": meta.get("company_count", 0),
        "has_report": True,
    }


@router.post("/admin/vertical-ingest")
async def competitor_admin_vertical_ingest(request: Request, file: UploadFile = File(...)):
    """上传 7 家纵向分析 PDF 的 zip，后台 Docling 解析并写入 vertical.snapshot.json。"""
    _require_admin(request)
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
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except zipfile.BadZipFile as e:
        raise HTTPException(status_code=400, detail="无效的 zip 文件") from e

    return {"ok": True, "job_id": job_id, "status": "queued"}


@router.post("/admin/vertical-pdf-zip")
async def competitor_admin_vertical_pdf_zip(request: Request, file: UploadFile = File(...)):
    """上传 7 家纵向 PDF zip，仅存档供纵向页 PDF 直显（不调用 Docling）。"""
    _require_admin(request)
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
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except zipfile.BadZipFile as e:
        raise HTTPException(status_code=400, detail="无效的 zip 文件") from e
    return {"ok": True, **result}


@router.get("/vertical-pdf/meta")
def competitor_vertical_pdf_meta(request: Request):
    _require_view_business_dashboard(request)
    meta = load_vertical_pdf_meta()
    if not meta:
        raise HTTPException(status_code=404, detail="no_vertical_pdfs")
    return JSONResponse(content=meta, headers={"Cache-Control": "no-store, no-cache"})


@router.get("/vertical-pdf/{company_id}")
def competitor_vertical_pdf_file(request: Request, company_id: str):
    _require_view_business_dashboard(request)
    path = vertical_pdf_path(company_id)
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
async def competitor_admin_upload_vertical(request: Request, file: UploadFile = File(...)):
    """上传各公司纵向分析 MD，写入 uploads/competitor/vertical_report.md。仅管理员。"""
    _require_admin(request)
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
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    meta = doc.get("meta") or {}
    return {
        "ok": True,
        "meta": {
            "title": meta.get("title"),
            "uploaded_at": meta.get("uploaded_at"),
            "uploaded_by": meta.get("uploaded_by"),
            "source_filename": meta.get("source_filename"),
            "company_count": meta.get("company_count"),
        },
        "warnings": list(doc.get("warnings") or []),
        "companies_parsed": len(doc.get("companies") or []),
    }


@router.get("/vertical-report")
def competitor_vertical_report(request: Request):
    """返回各公司纵向分析报告（结构化 JSON）。"""
    _require_view_business_dashboard(request)
    doc = load_vertical_report()
    if not doc:
        raise HTTPException(status_code=404, detail="no_vertical_report")
    return JSONResponse(content=doc, headers={"Cache-Control": "no-store, no-cache"})


@router.get("/vertical-report/meta")
def competitor_vertical_report_meta(request: Request):
    _require_view_business_dashboard(request)
    meta = load_vertical_meta()
    if not meta:
        raise HTTPException(status_code=404, detail="no_vertical_report")
    return JSONResponse(content=meta, headers={"Cache-Control": "no-store, no-cache"})
