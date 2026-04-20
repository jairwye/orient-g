"""
合同台账（v1.2.2.d）最小实现：
- 上传 PDF 合同（可含图片）→ 走现有 upload_user_document（Docling 解析+分段+chunks）→ 写入 contract_ledger
- 将文档额外归属到 c_contracts_public_1（用于“合同管理”folder 问答）
"""

from __future__ import annotations

import json
from pathlib import Path

import jwt
from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from backend.config import settings
from backend.services.contracts_ledger import create_contract, get_contract, list_my_contracts
from backend.services.knowledge_acl import load_fixtures
from backend.services.kb_acl_store import get_doc_collection_ids, set_resource_assignments
from backend.services import kb_documents


router = APIRouter()
ALGORITHM = "HS256"


def _get_token_from_request(request: Request) -> str | None:
    auth = request.headers.get("Authorization") or ""
    if auth.startswith("Bearer "):
        t = auth[7:].strip()
        if t:
            return t
    return request.headers.get("X-Auth-Token") or None


def _get_username_from_request(request: Request) -> str | None:
    token = _get_token_from_request(request)
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.auth_secret, algorithms=[ALGORITHM])
        return (payload.get("sub") or "").strip() or None
    except Exception:
        return None


@router.get("/list")
def contracts_list(request: Request, limit: int = 50):
    un = _get_username_from_request(request)
    if not un:
        raise HTTPException(status_code=401, detail="not authenticated")
    fixtures = load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    return {"items": list_my_contracts(tenant_id, un, limit=limit)}


@router.get("/{contract_id}")
def contracts_get(contract_id: str, request: Request):
    un = _get_username_from_request(request)
    if not un:
        raise HTTPException(status_code=401, detail="not authenticated")
    fixtures = load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    c = get_contract(tenant_id, contract_id)
    if not c or c.get("owner_username") != un:
        raise HTTPException(status_code=404, detail="not found")
    return c


@router.post("/upload")
async def contracts_upload(request: Request, file: UploadFile = File(...)):
    un = _get_username_from_request(request)
    if not un:
        raise HTTPException(status_code=401, detail="not authenticated")
    fixtures = load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    raw = await file.read()
    if len(raw) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件过大（最大 50MB）")

    info = kb_documents.upload_user_document(tenant_id, un, filename=file.filename or "contract.pdf", raw=raw)
    doc_id = str(info.get("doc_id") or "").strip()
    if not doc_id:
        raise HTTPException(status_code=500, detail="upload failed (missing doc_id)")

    # 将合同文档额外归属到合同管理 collection（保留原 private 归属不移除）
    try:
        existing = set(get_doc_collection_ids(tenant_id, doc_id))
        existing.add("c_contracts_public_1")
        set_resource_assignments(tenant_id, resource_type="doc", resource_id=doc_id, collection_ids=sorted(existing))
    except Exception:
        pass

    # 提取信息（本版先不细化字段，保存最小可追溯信息）
    extracted = {
        "note": "v1.2.2 占位：字段后续细化",
        "original_filename": file.filename or "contract.pdf",
    }
    # 尝试读取 Docling 产物头部，便于后续开发抽取器
    try:
        root = Path(settings.upload_dir).resolve() / "kb_user_documents" / tenant_id / doc_id / "archive" / "full.md"
        if root.exists():
            head = root.read_text(encoding="utf-8", errors="replace")[:4000]
            extracted["md_head"] = head
    except Exception:
        pass

    c = create_contract(
        tenant_id,
        un,
        doc_id=doc_id,
        original_filename=file.filename,
        storage_path=str(info.get("storage_path") or info.get("doc_id") or ""),
        extracted=extracted,
    )
    return {"ok": True, "contract": c, "doc": info}

