"""竞品财报：MD 上传 → Snapshot；展示 API（view_business_dashboard）。"""
from __future__ import annotations

import jwt
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from backend.config import settings
from backend.routers.settings import _require_admin, _require_view_business_dashboard
from backend.services.competitor_report_parser import (
    CompetitorParseError,
    collect_sec09_anchor_stats,
    parse_markdown,
)
from backend.services.competitor_report_store import load_meta, save_snapshot, snapshot_for_api
from backend.services.vertical_report_store import load_vertical_report

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


@router.get("/vertical-report")
def competitor_vertical_report(request: Request):
    """返回各公司纵向分析报告（结构化 JSON）。"""
    _require_view_business_dashboard(request)
    doc = load_vertical_report()
    if not doc:
        raise HTTPException(status_code=404, detail="no_vertical_report")
    return JSONResponse(content=doc, headers={"Cache-Control": "no-store, no-cache"})
