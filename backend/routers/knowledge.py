"""
Knowledge：options/ask、用户上传文档、RAG 包列表。
"""

from __future__ import annotations

import re
from typing import Any

import jwt
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy import bindparam, text

from backend.config import settings
from backend.services.kb_acl_store import get_all_resource_assignments
from backend.services import kb_documents as kb_docs
from backend.services import kb_tasks
from backend.services.bigpdf_tasks import prepare_task_input, stage_to_progress
from backend.services.knowledge_acl import compute_acl_scope, load_fixtures
from backend.services.knowledge_pipeline import ask_knowledge
from backend.services.knowledge_audit import write_event as audit_write_event
from backend.services.task_queue import (
    TASK_KIND_BIGPDF_PARSE,
    enqueue_bigpdf_task,
    enqueue_user_doc_task,
    Priority,
    submit,
    TASK_EMBED_AND_INDEX_REFRESH,
)
from backend.services.task_queue import get_stats as get_queue_stats
from backend.services.online_rate_limiter import allow as rate_limit_allow
from backend.services.user_acl_store import get_user
from backend.services import rag_packages
from backend.services.kb_vector_index import index_uploaded_document_task
from backend.services.kb_vector_store import vector_enabled
from backend.services.kb_tables import list_table_instances
from fastapi.responses import Response
from backend.services.kb_folders import (
    add_resource_to_folder_extra,
    bind_resource_to_folder,
    create_folder,
    delete_folder,
    ensure_private_folder,
    get_folder,
    list_folder_resources,
    list_folders,
    set_folder_collections,
    share_folder_to_kb_kind,
    share_folder_scope,
    share_folder_add_scope,
    unlink_doc_from_folder,
    unshare_folder_to_private,
    upsert_folder,
    backfill_uploaded_docs_to_private_folders,
)

router = APIRouter()
ALGORITHM = "HS256"

KB_KIND_CHOICES = [
    "Private",
    "DeptPublic",
    "DeptLead",
    "ProjectPublic",
    "ProjectLead",
    "MultiDeptPublic",
    "MultiDeptLead",
    "MultiProjectPublic",
    "MultiProjectLead",
    "CompanyPublic",
]


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


def _norm_folder_name(name: str) -> str:
    # 名称冲突按“去首尾空白 + 压缩中间空白 + 小写”判定
    return re.sub(r"\s+", " ", (name or "").strip()).lower()


def _is_visible_folder_name_conflict(
    *,
    tenant_id: str,
    username: str,
    allowed_col_ids: set[str],
    target_name: str,
    exclude_folder_id: str | None = None,
) -> bool:
    """
    可见范围同名冲突检测：
    - 包含当前用户自己的私有 folder
    - 包含通过 collection ACL 可见的共享 folder
    """
    tn = _norm_folder_name(target_name)
    if not tn:
        return False
    ex = (exclude_folder_id or "").strip()
    un = (username or "").strip()
    for f in list_folders(tenant_id):
        fid = str(f.get("folder_id") or "").strip()
        if not fid or (ex and fid == ex):
            continue
        cids = [str(x) for x in (f.get("collection_ids") or []) if str(x).strip()]
        visible = any(cid in allowed_col_ids for cid in cids)
        owner = (str(f.get("owner_username") or "").strip() or "")
        # private folder：owner 可见；共享 folder：按 collection ACL 可见
        if not visible and owner != un:
            continue
        if _norm_folder_name(str(f.get("name") or "")) == tn:
            return True
    return False


class OptionsResponse(BaseModel):
    collections: list[dict[str, Any]]
    tables: list[dict[str, Any]]
    folders: list[dict[str, Any]]
    default_selected_collection_ids: list[str]
    default_selected_table_ids: list[str]
    default_selected_folder_ids: list[str]


@router.get("/options", response_model=OptionsResponse)
def knowledge_options(request: Request):
    token = _get_token_from_request(request)
    if not token:
        return OptionsResponse(
            collections=[],
            tables=[],
            folders=[],
            default_selected_collection_ids=[],
            default_selected_table_ids=[],
            default_selected_folder_ids=[],
        )

    fixtures = load_fixtures()
    scope = compute_acl_scope(token, fixtures=fixtures)
    allowed_col_ids = set(scope["allowed_collection_ids"])
    allowed_table_ids = set(scope["allowed_table_ids"])
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    table_to_cids: dict[str, set[str]] = {}
    try:
        assigns = get_all_resource_assignments(tenant_id, resource_type="table")
        for a in assigns:
            rid = a.get("resource_id")
            cid = a.get("collection_id")
            if rid and cid:
                table_to_cids.setdefault(str(rid), set()).add(str(cid))
    except Exception:
        table_to_cids = {}

    fixture_cids = {str(c.get("collection_id")) for c in (fixtures.get("collections") or []) if c.get("collection_id")}

    collections_out: list[dict[str, Any]] = []
    for c in fixtures.get("collections") or []:
        if c.get("collection_id") in allowed_col_ids:
            collections_out.append(
                {
                    "collection_id": c.get("collection_id"),
                    "space_type": c.get("space_type"),
                    "name": c.get("name"),
                    "type": c.get("type"),
                    "department_id": c.get("department_id"),
                    "project_id": c.get("project_id"),
                    "owner_user_id": c.get("owner_user_id"),
                }
            )

    uname = _get_username_from_request(request)
    # folder-first：确保用户有默认私有文件夹（用于 UI 选择范围）
    if uname:
        try:
            ensure_private_folder(tenant_id, username=uname)
        except Exception:
            pass
    for cid in sorted(allowed_col_ids):
        cs = str(cid)
        if cs.startswith("c_private_dyn_") and cs not in fixture_cids:
            collections_out.append(
                {
                    "collection_id": cs,
                    "space_type": "Private",
                    "name": "我的私人知识库",
                    "type": "private",
                    "owner_user_id": uname or "",
                }
            )

    tables_out: list[dict[str, Any]] = []
    for t in fixtures.get("tables") or []:
        if t.get("table_id") in allowed_table_ids:
            table_id = str(t.get("table_id"))
            db_cids = table_to_cids.get(table_id, set()) if table_to_cids else set()
            db_cids_allowed = [cid for cid in db_cids if cid in allowed_col_ids]
            cid = db_cids_allowed[0] if db_cids_allowed else t.get("collection_id")
            cmeta = next(
                (x for x in fixtures.get("collections") or [] if x.get("collection_id") == cid),
                None,
            )
            tables_out.append(
                {
                    "table_id": t.get("table_id"),
                    "collection_id": cid,
                    "space_type": cmeta.get("space_type") if isinstance(cmeta, dict) else None,
                    "name": t.get("name"),
                    "row_count": t.get("rows") and len(t.get("rows") or []) or 0,
                }
            )

    # DB TableInstance：补充输出（用于 2.c 表实例持久化链路）
    try:
        db_tables = list_table_instances(tenant_id, sorted(allowed_table_ids))
        fixture_table_ids = {str(t.get("table_id")) for t in (fixtures.get("tables") or []) if t.get("table_id")}
        for t in db_tables:
            tid = str(t.get("table_id") or "").strip()
            if not tid or tid in fixture_table_ids:
                continue
            # collection_id 从 assignment 推断（取一个可见集合；没有则空）
            cids = sorted(list(table_to_cids.get(tid, set())))
            cid = cids[0] if cids else None
            cmeta = next(
                (x for x in fixtures.get("collections") or [] if x.get("collection_id") == cid),
                None,
            )
            tables_out.append(
                {
                    "table_id": tid,
                    "collection_id": cid,
                    "space_type": cmeta.get("space_type") if isinstance(cmeta, dict) else None,
                    "name": t.get("name") or tid,
                    "row_count": int(t.get("row_count") or 0),
                }
            )
    except Exception:
        pass

    default_collection_ids = [c["collection_id"] for c in collections_out if c.get("type") == "private"]
    if not default_collection_ids:
        default_collection_ids = [
            c["collection_id"] for c in collections_out if c.get("type") in {"project", "public", "department"}
        ]

    default_table_ids = [t["table_id"] for t in tables_out][:3]

    # folders（collection 分组）：仅返回“包含至少一个可见 collection”的 folder
    folders_out: list[dict[str, Any]] = []
    default_folder_ids: list[str] = []
    try:
        for f in list_folders(tenant_id):
            cids = [str(x) for x in (f.get("collection_ids") or []) if str(x).strip()]
            visible = [cid for cid in cids if cid in allowed_col_ids]
            if not visible:
                continue
            folders_out.append(
                {
                    "folder_id": f.get("folder_id"),
                    "name": f.get("name"),
                    "collection_ids": visible,
                }
            )
        # v1.2.2：不默认勾选 folder，避免误扩大范围；由用户选择
        default_folder_ids = []
    except Exception:
        folders_out = []
        default_folder_ids = []

    return OptionsResponse(
        collections=collections_out,
        tables=tables_out,
        folders=folders_out,
        default_selected_collection_ids=default_collection_ids[:5],
        default_selected_table_ids=default_table_ids,
        default_selected_folder_ids=default_folder_ids,
    )


class FolderItem(BaseModel):
    folder_id: str
    name: str
    kind: str | None = None
    scope: dict[str, Any] = {}
    owner_username: str | None = None
    created_by: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    collection_ids: list[str] = []
    resource_counts: dict[str, int] = {}


@router.get("/folders")
def kb_list_folders(request: Request):
    un = _get_username_from_request(request)
    if not un:
        raise HTTPException(status_code=401, detail="not authenticated")
    fixtures = load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    # folder 本身可见性：按 options 的 allowed_col_ids 过滤其 collection_ids；若 folder 无 collection 映射则仅 owner 可见
    token = _get_token_from_request(request) or ""
    scope = compute_acl_scope(token, fixtures=fixtures)
    allowed_col_ids = set(scope["allowed_collection_ids"])
    items: list[dict[str, Any]] = []
    for f in list_folders(tenant_id):
        cids = [str(x) for x in (f.get("collection_ids") or []) if str(x).strip()]
        visible = [cid for cid in cids if cid in allowed_col_ids]
        # private folder：允许 owner 看（即使 collection_ids 空）
        if not visible:
            if (str(f.get("owner_username") or "").strip() or "") != un:
                continue
        ff = dict(f)
        ff["collection_ids"] = visible
        items.append(ff)
    return {"items": items}


class CreateFolderBody(BaseModel):
    name: str


@router.post("/folders")
def kb_create_folder(request: Request, body: CreateFolderBody):
    un = _get_username_from_request(request)
    if not un:
        raise HTTPException(status_code=401, detail="not authenticated")
    token = _get_token_from_request(request) or ""
    fixtures = load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    scope = compute_acl_scope(token, fixtures=fixtures)
    allowed_col_ids = set(scope["allowed_collection_ids"])
    if _is_visible_folder_name_conflict(
        tenant_id=tenant_id,
        username=un,
        allowed_col_ids=allowed_col_ids,
        target_name=body.name,
    ):
        raise HTTPException(status_code=409, detail="文件夹名称已存在（含共享到你可见范围的知识库）。请使用其他名称。")
    info = create_folder(tenant_id, name=body.name, created_by=un, kind="Private", scope={}, owner_username=un)
    # 默认绑定动态私有 collection，保证 folder 可用于问答范围过滤
    pcid = kb_docs.dynamic_private_collection_id(un)
    set_folder_collections(tenant_id, folder_id=info["folder_id"], collection_ids=[pcid])
    return {"ok": True, **info}


class PatchFolderBody(BaseModel):
    name: str | None = None


@router.patch("/folders/{folder_id}")
def kb_rename_folder(folder_id: str, request: Request, body: PatchFolderBody):
    un = _get_username_from_request(request)
    if not un:
        raise HTTPException(status_code=401, detail="not authenticated")
    token = _get_token_from_request(request) or ""
    fixtures = load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    f = get_folder(tenant_id, folder_id=folder_id)
    if not f:
        raise HTTPException(status_code=404, detail="not found")
    owner = str(f.get("owner_username") or "").strip()
    if owner and owner != un:
        raise HTTPException(status_code=403, detail="forbidden")
    new_name = (body.name or "").strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="name required")
    scope = compute_acl_scope(token, fixtures=fixtures)
    allowed_col_ids = set(scope["allowed_collection_ids"])
    if _is_visible_folder_name_conflict(
        tenant_id=tenant_id,
        username=un,
        allowed_col_ids=allowed_col_ids,
        target_name=new_name,
        exclude_folder_id=folder_id,
    ):
        raise HTTPException(status_code=409, detail="文件夹名称已存在（含共享到你可见范围的知识库）。请使用其他名称。")
    upsert_folder(
        tenant_id,
        folder_id=folder_id,
        name=new_name,
        created_by=None,
        collection_ids=None,
        kind=str(f.get("kind") or "").strip() or None,
        scope=f.get("scope") or {},
        owner_username=owner or None,
    )
    return {"ok": True}


@router.delete("/folders/{folder_id}")
def kb_delete_folder(folder_id: str, request: Request):
    un = _get_username_from_request(request)
    if not un:
        raise HTTPException(status_code=401, detail="not authenticated")
    fixtures = load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    f = get_folder(tenant_id, folder_id=folder_id)
    if not f:
        raise HTTPException(status_code=404, detail="not found")
    owner = str(f.get("owner_username") or "").strip()
    if owner and owner != un:
        raise HTTPException(status_code=403, detail="forbidden")
    ok = delete_folder(tenant_id, folder_id=folder_id)
    return {"ok": bool(ok)}


@router.get("/folders/{folder_id}/resources")
def kb_folder_resources(folder_id: str, request: Request):
    un = _get_username_from_request(request)
    if not un:
        raise HTTPException(status_code=401, detail="not authenticated")
    fixtures = load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    f = get_folder(tenant_id, folder_id=folder_id)
    if not f:
        raise HTTPException(status_code=404, detail="not found")
    owner = str(f.get("owner_username") or "").strip()
    # 可见性：若 folder 有 owner，则仅 owner；否则按其 collection_ids 是否在 allowed_col_ids
    token = _get_token_from_request(request) or ""
    scope = compute_acl_scope(token, fixtures=fixtures)
    allowed_col_ids = set(scope["allowed_collection_ids"])
    if owner and owner != un:
        raise HTTPException(status_code=403, detail="forbidden")
    if not owner:
        cids = [str(x) for x in (f.get("collection_ids") or []) if str(x).strip()]
        if not any(cid in allowed_col_ids for cid in cids):
            raise HTTPException(status_code=403, detail="forbidden")

    resources = list_folder_resources(tenant_id, folder_id=folder_id)
    # 目前先输出 doc 的基本信息（table 后续补齐）
    doc_ids = [r["resource_id"] for r in resources if r.get("resource_type") == "doc" and str(r.get("resource_id") or "").strip()]
    docs_map: dict[str, dict[str, Any]] = {}
    if doc_ids:
        from backend.database import get_db

        with get_db() as db:
            rows = db.execute(
                text(
                    """
                    SELECT doc_id, title, original_filename, size_bytes, status, last_error, created_at
                    FROM kb_user_documents
                    WHERE tenant_id=:t AND doc_id IN :ids
                    """
                ).bindparams(bindparam("ids", expanding=True)),
                {"t": tenant_id, "ids": doc_ids},
            ).fetchall()
        for r in rows:
            did = str(r[0])
            docs_map[did] = {
                "doc_id": did,
                "title": str(r[1] or ""),
                "original_filename": str(r[2] or ""),
                "size_bytes": int(r[3] or 0),
                "status": str(r[4] or ""),
                "last_error": str(r[5] or "") if r[5] else None,
                "created_at": r[6].isoformat() if r[6] else None,
            }
    docs_out = [docs_map.get(did) for did in doc_ids if docs_map.get(did)]
    return {"folder": f, "resources": resources, "docs": docs_out}


class MoveResourcesBody(BaseModel):
    target_folder_id: str
    doc_ids: list[str] = []


@router.post("/folders/{folder_id}/move-resources")
def kb_move_folder_resources(folder_id: str, request: Request, body: MoveResourcesBody):
    un = _get_username_from_request(request)
    if not un:
        raise HTTPException(status_code=401, detail="not authenticated")
    fixtures = load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    src = get_folder(tenant_id, folder_id=folder_id)
    dst = get_folder(tenant_id, folder_id=body.target_folder_id)
    if not src or not dst:
        raise HTTPException(status_code=404, detail="not found")
    # 简化：仅允许 owner/created_by 操作私有 folder；共享 folder 的移动后续补细粒度
    for f in (src, dst):
        owner = str(f.get("owner_username") or "").strip()
        if owner and owner != un:
            raise HTTPException(status_code=403, detail="forbidden")
    moved = 0
    for did in [str(x).strip() for x in (body.doc_ids or []) if str(x).strip()]:
        # move 语义：从源文件夹解绑，再绑定到目标文件夹
        try:
            unlink_doc_from_folder(tenant_id, folder_id=folder_id, doc_id=did)
        except Exception:
            # 若源文件夹本就无绑定，保持幂等
            pass
        bind_resource_to_folder(tenant_id, folder_id=body.target_folder_id, resource_type="doc", resource_id=did)
        moved += 1
    return {"ok": True, "moved": moved}


class LinkDocBody(BaseModel):
    doc_id: str


@router.post("/folders/{folder_id}/link-doc")
def kb_link_doc_to_folder(folder_id: str, request: Request, body: LinkDocBody):
    """将文档额外绑定到目标文件夹（复制到文件夹：保留原文件夹绑定）。"""
    un = _get_username_from_request(request)
    if not un:
        raise HTTPException(status_code=401, detail="not authenticated")
    fixtures = load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    dst = get_folder(tenant_id, folder_id=folder_id)
    if not dst:
        raise HTTPException(status_code=404, detail="not found")
    owner = str(dst.get("owner_username") or "").strip()
    if owner and owner != un:
        raise HTTPException(status_code=403, detail="forbidden")
    did = (body.doc_id or "").strip()
    if not did:
        raise HTTPException(status_code=400, detail="doc_id required")
    if kb_docs.get_document_owner(tenant_id, did) != un:
        raise HTTPException(status_code=403, detail="forbidden")
    try:
        add_resource_to_folder_extra(tenant_id, folder_id=folder_id, resource_type="doc", resource_id=did)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    return {"ok": True}


@router.post("/folders/{folder_id}/unlink-doc")
def kb_unlink_doc_from_folder(folder_id: str, request: Request, body: LinkDocBody):
    """从当前文件夹移除文档绑定（不删除文档；若无其它绑定则回到私有文件夹）。"""
    un = _get_username_from_request(request)
    if not un:
        raise HTTPException(status_code=401, detail="not authenticated")
    fixtures = load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    f = get_folder(tenant_id, folder_id=folder_id)
    if not f:
        raise HTTPException(status_code=404, detail="not found")
    owner = str(f.get("owner_username") or "").strip()
    if owner and owner != un:
        raise HTTPException(status_code=403, detail="forbidden")
    did = (body.doc_id or "").strip()
    if not did:
        raise HTTPException(status_code=400, detail="doc_id required")
    if kb_docs.get_document_owner(tenant_id, did) != un:
        raise HTTPException(status_code=403, detail="forbidden")
    try:
        unlink_doc_from_folder(tenant_id, folder_id=folder_id, doc_id=did, owner_username=un)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    return {"ok": True}


class ShareFolderBody(BaseModel):
    kb_kind: str
    department_ids: list[str] = []
    project_ids: list[str] = []
    company_public: bool = False


@router.post("/folders/{folder_id}/share")
def kb_share_folder(folder_id: str, request: Request, body: ShareFolderBody):
    un = _get_username_from_request(request)
    if not un:
        raise HTTPException(status_code=401, detail="not authenticated")
    fixtures = load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    f = get_folder(tenant_id, folder_id=folder_id)
    if not f:
        raise HTTPException(status_code=404, detail="not found")
    owner = str(f.get("owner_username") or "").strip()
    if owner and owner != un:
        raise HTTPException(status_code=403, detail="forbidden")
    # 共享：更新 folder_collections（folder-first 权威），并将 folder 内 doc assignment 覆盖为该集合（folder-only）
    cids = share_folder_to_kb_kind(
        tenant_id,
        fixtures,
        folder_id=folder_id,
        kb_kind=body.kb_kind,
        department_ids=list(body.department_ids or []),
        project_ids=list(body.project_ids or []),
        company_public=bool(body.company_public) or body.kb_kind == "CompanyPublic",
    )
    # 同步 folder 内文档的 resource→collection assignment
    resources = list_folder_resources(tenant_id, folder_id=folder_id)
    doc_ids = [r["resource_id"] for r in resources if r.get("resource_type") == "doc"]
    for did in doc_ids:
        from backend.services.kb_acl_store import set_resource_assignments

        set_resource_assignments(tenant_id, resource_type="doc", resource_id=str(did), collection_ids=cids)
    return {"ok": True, "collection_ids": cids, "doc_count": len(doc_ids)}


def _sync_folder_doc_collection_assignments(tenant_id: str, folder_id: str, collection_ids: list[str]) -> int:
    resources = list_folder_resources(tenant_id, folder_id=folder_id)
    doc_ids = [r["resource_id"] for r in resources if r.get("resource_type") == "doc"]
    from backend.services.kb_acl_store import set_resource_assignments

    for did in doc_ids:
        set_resource_assignments(tenant_id, resource_type="doc", resource_id=str(did), collection_ids=collection_ids)
    return len(doc_ids)


@router.post("/folders/{folder_id}/move-to-kb")
def kb_move_folder_to_kb(folder_id: str, request: Request, body: ShareFolderBody):
    """
    将文件夹「移动」到目标知识库范围：先从当前共享范围撤回为私有绑定，再按目标 kb_kind 重新共享（与「复制」不同）。
    """
    un = _get_username_from_request(request)
    if not un:
        raise HTTPException(status_code=401, detail="not authenticated")
    fixtures = load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    f = get_folder(tenant_id, folder_id=folder_id)
    if not f:
        raise HTTPException(status_code=404, detail="not found")
    owner = str(f.get("owner_username") or "").strip()
    if owner and owner != un:
        raise HTTPException(status_code=403, detail="forbidden")

    kk = (body.kb_kind or "").strip()
    if not kk:
        raise HTTPException(status_code=400, detail="kb_kind required")
    if kk not in KB_KIND_CHOICES:
        raise HTTPException(status_code=400, detail="invalid kb_kind")

    try:
        cids_private = unshare_folder_to_private(tenant_id, folder_id=folder_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None

    if kk == "Private":
        n = _sync_folder_doc_collection_assignments(tenant_id, folder_id, cids_private)
        return {"ok": True, "collection_ids": cids_private, "doc_count": n, "moved": True}

    cids = share_folder_to_kb_kind(
        tenant_id,
        fixtures,
        folder_id=folder_id,
        kb_kind=kk,
        department_ids=list(body.department_ids or []),
        project_ids=list(body.project_ids or []),
        company_public=bool(body.company_public) or kk == "CompanyPublic",
    )
    n = _sync_folder_doc_collection_assignments(tenant_id, folder_id, cids)
    return {"ok": True, "collection_ids": cids, "doc_count": n, "moved": True}


class ShareFolderScopeBody(BaseModel):
    target: str  # company|department|project
    access_kind: str = "public"  # public|lead（仅 department/project 生效）
    department_ids: list[str] = []
    project_ids: list[str] = []


@router.post("/folders/{folder_id}/share-scope")
def kb_share_folder_scope(folder_id: str, request: Request, body: ShareFolderScopeBody):
    un = _get_username_from_request(request)
    if not un:
        raise HTTPException(status_code=401, detail="not authenticated")
    fixtures = load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    f = get_folder(tenant_id, folder_id=folder_id)
    if not f:
        raise HTTPException(status_code=404, detail="not found")
    owner = str(f.get("owner_username") or "").strip()
    if owner and owner != un:
        raise HTTPException(status_code=403, detail="forbidden")

    try:
        cids = share_folder_scope(
            tenant_id,
            fixtures,
            folder_id=folder_id,
            target=body.target,
            department_ids=list(body.department_ids or []),
            project_ids=list(body.project_ids or []),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None

    # 同步 folder 内文档的 resource→collection assignment（folder-only）
    resources = list_folder_resources(tenant_id, folder_id=folder_id)
    doc_ids = [r["resource_id"] for r in resources if r.get("resource_type") == "doc"]
    from backend.services.kb_acl_store import set_resource_assignments

    for did in doc_ids:
        set_resource_assignments(tenant_id, resource_type="doc", resource_id=str(did), collection_ids=cids)
    return {"ok": True, "collection_ids": cids, "doc_count": len(doc_ids)}


@router.post("/folders/{folder_id}/share-add-scope")
def kb_share_folder_add_scope(folder_id: str, request: Request, body: ShareFolderScopeBody):
    """
    共享（加法）：追加可见范围，但不产生两份文件夹/文档。
    """
    un = _get_username_from_request(request)
    if not un:
        raise HTTPException(status_code=401, detail="not authenticated")
    fixtures = load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    f = get_folder(tenant_id, folder_id=folder_id)
    if not f:
        raise HTTPException(status_code=404, detail="not found")
    owner = str(f.get("owner_username") or "").strip()
    if owner and owner != un:
        raise HTTPException(status_code=403, detail="forbidden")

    try:
        cids = share_folder_add_scope(
            tenant_id,
            fixtures,
            folder_id=folder_id,
            target=body.target,
            access_kind=body.access_kind,
            department_ids=list(body.department_ids or []),
            project_ids=list(body.project_ids or []),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None

    n = _sync_folder_doc_collection_assignments(tenant_id, folder_id, cids)
    return {"ok": True, "collection_ids": cids, "doc_count": n, "shared": True}


@router.post("/folders/{folder_id}/unshare")
def kb_unshare_folder(folder_id: str, request: Request):
    un = _get_username_from_request(request)
    if not un:
        raise HTTPException(status_code=401, detail="not authenticated")
    fixtures = load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    f = get_folder(tenant_id, folder_id=folder_id)
    if not f:
        raise HTTPException(status_code=404, detail="not found")
    owner = str(f.get("owner_username") or "").strip()
    if owner and owner != un:
        raise HTTPException(status_code=403, detail="forbidden")
    try:
        cids = unshare_folder_to_private(tenant_id, folder_id=folder_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None

    resources = list_folder_resources(tenant_id, folder_id=folder_id)
    doc_ids = [r["resource_id"] for r in resources if r.get("resource_type") == "doc"]
    from backend.services.kb_acl_store import set_resource_assignments

    for did in doc_ids:
        set_resource_assignments(tenant_id, resource_type="doc", resource_id=str(did), collection_ids=cids)
    return {"ok": True, "collection_ids": cids, "doc_count": len(doc_ids)}


class AskBody(BaseModel):
    query: str
    selected_collection_ids: list[str] | None = None
    selected_table_ids: list[str] | None = None


@router.post("/ask")
def knowledge_ask(request: Request, body: AskBody):
    token = _get_token_from_request(request)
    if not token:
        raise HTTPException(status_code=401, detail="not authenticated")

    fixtures = load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    uname = _get_username_from_request(request)

    # 2.e：队列堆积降级（高优先级堆积过多时，在线路径快速失败，避免系统不可恢复）
    try:
        qs = get_queue_stats()
        if int(qs.get("queue_size_high") or 0) >= int(settings.queue_degrade_high_threshold):
            try:
                audit_write_event(
                    tenant_id,
                    username=uname,
                    event_type="ai.answer.deny",
                    query=body.query,
                    meta={"reason": "queue_backpressure", "queue_size_high": qs.get("queue_size_high")},
                )
            except Exception:
                pass
            raise HTTPException(status_code=503, detail="系统繁忙（队列堆积），请稍后重试")
    except HTTPException:
        raise
    except Exception:
        # 观测失败不影响主流程
        pass

    # 2.e：在线互动按用户限速（token bucket）
    key = f"knowledge.ask:{tenant_id}:{uname or 'anonymous'}"
    if not rate_limit_allow(key=key):
        try:
            audit_write_event(
                tenant_id,
                username=uname,
                event_type="ai.answer.deny",
                query=body.query,
                meta={"reason": "rate_limited"},
            )
        except Exception:
            pass
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")

    # 审计：attempt（不记录 query 明文，仅 hash+len；meta 不含敏感明文）
    try:
        audit_write_event(
            tenant_id,
            username=uname,
            event_type="knowledge.retrieve.attempt",
            query=body.query,
            meta={
                "selected_collection_ids": list(body.selected_collection_ids or []),
                "selected_table_ids": list(body.selected_table_ids or []),
            },
        )
    except Exception:
        pass
    res = ask_knowledge(
        token,
        body.query,
        selected_collection_ids=body.selected_collection_ids,
        selected_table_ids=body.selected_table_ids,
        fixtures=fixtures,
    )

    if res.get("denied"):
        try:
            audit_write_event(
                tenant_id,
                username=uname,
                event_type="knowledge.retrieve.deny",
                query=body.query,
                meta={"reason": res.get("deny_reason") or "denied"},
            )
        except Exception:
            pass
        raise HTTPException(status_code=403, detail=res.get("deny_reason") or "denied")

    try:
        citations = res.get("citations") or []
        audit_write_event(
            tenant_id,
            username=uname,
            event_type="ai.answer.generate",
            query=body.query,
            meta={
                "citation_count": len(citations),
                "doc_ids": sorted({str(c.get("doc_id")) for c in citations if c.get("doc_id")}),
                "table_ids": sorted({str(c.get("table_id")) for c in citations if c.get("table_id")}),
            },
        )
    except Exception:
        pass
    return res


class ReindexBody(BaseModel):
    doc_ids: list[str] | None = None


@router.post("/admin/reindex")
def kb_admin_reindex(request: Request, body: ReindexBody):
    """
    管理接口：手动触发向量重建（异步队列）。
    默认仅当 KB 向量开关开启时有效；否则返回提示。
    """
    un = _get_username_from_request(request)
    if not un:
        raise HTTPException(status_code=401, detail="not authenticated")
    u = get_user(un) or {}
    roles = [str(x).strip().lower() for x in (u.get("roles") or [])]
    if "admin" not in roles and "管理层" not in roles:
        raise HTTPException(status_code=403, detail="forbidden")
    fixtures = load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    if not vector_enabled():
        return {"ok": False, "detail": "KB 向量检索未开启（kb_vector_enabled=false）", "accepted": 0}

    doc_ids = [str(x).strip() for x in (body.doc_ids or []) if str(x).strip()]
    if not doc_ids:
        doc_ids = kb_docs.list_all_uploaded_doc_ids(tenant_id)

    accepted = 0
    for did in doc_ids:
        ok = submit(
            Priority.LOW,
            index_uploaded_document_task,
            tenant_id,
            did,
            task_id=f"reindex_{did}",
            task_type=TASK_EMBED_AND_INDEX_REFRESH,
        )
        if ok:
            accepted += 1
    return {"ok": True, "accepted": accepted, "requested": len(doc_ids)}


@router.post("/admin/folders/backfill")
def kb_admin_backfill_folders(request: Request):
    """
    一次性回填：把历史用户上传文档绑定到“owner 的私有文件夹”。
    仅回填 folder→resource 关系，不改文档内容。
    """
    un = _get_username_from_request(request)
    if not un:
        raise HTTPException(status_code=401, detail="not authenticated")
    u = get_user(un) or {}
    roles = [str(x).strip().lower() for x in (u.get("roles") or [])]
    if "admin" not in roles and "管理层" not in roles:
        raise HTTPException(status_code=403, detail="forbidden")
    fixtures = load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    try:
        res = backfill_uploaded_docs_to_private_folders(tenant_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return {"ok": True, **res}


@router.get("/meta/kb-kinds")
def knowledge_kb_kinds(request: Request):
    if not _get_token_from_request(request):
        raise HTTPException(status_code=401, detail="not authenticated")
    labels = {
        "Private": "私人知识库",
        "DeptPublic": "部门公共库",
        "DeptLead": "部门负责人库",
        "ProjectPublic": "项目公共库",
        "ProjectLead": "项目负责人库",
        "MultiDeptPublic": "多部门公共库",
        "MultiDeptLead": "多部门负责人库",
        "MultiProjectPublic": "多项目公共库",
        "MultiProjectLead": "多项目负责人库",
        "CompanyPublic": "公司公共库",
    }
    return {"items": [{"kb_kind": k, "label": labels.get(k, k)} for k in KB_KIND_CHOICES]}


@router.get("/my-documents")
def knowledge_my_documents(request: Request):
    un = _get_username_from_request(request)
    if not un:
        raise HTTPException(status_code=401, detail="not authenticated")
    fixtures = load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    items = kb_docs.list_my_documents(tenant_id, un)
    return {"items": items}


@router.post("/my-documents/upload")
async def knowledge_upload_my_document(
    request: Request,
    file: UploadFile = File(...),
    folder_id: str | None = Form(None),
):
    un = _get_username_from_request(request)
    if not un:
        raise HTTPException(status_code=401, detail="not authenticated")
    fixtures = load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    raw = await file.read()
    if len(raw) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件过大（最大 20MB）")
    try:
        info = kb_docs.upload_user_document_async(tenant_id, un, filename=file.filename or "upload", raw=raw)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    did = str(info.get("doc_id") or "")
    if not did:
        raise HTTPException(status_code=500, detail="上传失败：缺少 doc_id")
    ok, _ = enqueue_user_doc_task(tenant_id, un, did)
    if not ok:
        kb_docs.mark_document_failed(tenant_id, did, "队列已满，稍后重试")
        raise HTTPException(status_code=503, detail="队列已满，请稍后重试")

    # folder-first：若前端指定 folder_id，则绑定到该文件夹（覆盖默认私有文件夹绑定）
    fid = (folder_id or "").strip()
    if fid:
        f = get_folder(tenant_id, folder_id=fid)
        if not f:
            raise HTTPException(status_code=404, detail="folder not found")
        owner = str(f.get("owner_username") or "").strip()
        if owner and owner != un:
            raise HTTPException(status_code=403, detail="forbidden")
        bind_resource_to_folder(tenant_id, folder_id=fid, resource_type="doc", resource_id=str(info.get("doc_id") or ""))
    return {"ok": True, **info, "queued": True}


@router.delete("/my-documents/{doc_id}")
def knowledge_delete_my_document(doc_id: str, request: Request):
    un = _get_username_from_request(request)
    if not un:
        raise HTTPException(status_code=401, detail="not authenticated")
    fixtures = load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    if not kb_docs.delete_user_document(tenant_id, un, doc_id):
        raise HTTPException(status_code=403, detail="无权删除或文档不存在")
    return {"ok": True}


class ShareBody(BaseModel):
    kb_kind: str
    department_ids: list[str] = []
    project_ids: list[str] = []
    company_public: bool = False


@router.post("/my-documents/{doc_id}/share")
def knowledge_share_my_document(doc_id: str, body: ShareBody, request: Request):
    un = _get_username_from_request(request)
    if not un:
        raise HTTPException(status_code=401, detail="not authenticated")
    fixtures = load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    u = get_user(un) or {}
    dept_ids = list(body.department_ids or [])
    proj_ids = list(body.project_ids or [])
    if body.kb_kind in {"DeptPublic", "DeptLead"} and not dept_ids:
        d = str(u.get("department") or "").strip()
        if d:
            dept_ids = [d]
    if body.kb_kind in {"ProjectPublic", "ProjectLead"} and not proj_ids:
        proj_ids = [str(p.get("project_id") or "").strip() for p in (u.get("projects") or []) if str(p.get("project_id") or "").strip()]
    if body.kb_kind in {"MultiDeptPublic", "MultiDeptLead"} and not dept_ids:
        d = str(u.get("department") or "").strip()
        if d:
            dept_ids = [d]
    if body.kb_kind in {"MultiProjectPublic", "MultiProjectLead"} and not proj_ids:
        proj_ids = [str(p.get("project_id") or "").strip() for p in (u.get("projects") or []) if str(p.get("project_id") or "").strip()]
    company_public = bool(body.company_public) or body.kb_kind == "CompanyPublic"
    try:
        res = kb_docs.share_document(
            tenant_id,
            un,
            doc_id,
            fixtures,
            kb_kind=body.kb_kind,
            department_ids=dept_ids,
            project_ids=proj_ids,
            company_public=company_public,
        )
    except PermissionError:
        raise HTTPException(status_code=403, detail="仅文档拥有者可共享") from None
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("detail") or "共享失败")
    return res


@router.get("/rag-packages")
def knowledge_rag_packages(request: Request):
    if not _get_username_from_request(request):
        raise HTTPException(status_code=401, detail="not authenticated")
    fixtures = load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    return {"items": kb_docs.list_rag_packages(tenant_id)}


@router.post("/folders/{folder_id}/parse")
def kb_parse_folder(folder_id: str, request: Request):
    """
    批量解析文件夹内文档（多文档处理 MVP）：
    - 对 folder 中的 doc 资源逐个入队 enqueue_user_doc_task（与上传后的异步解析同链路）
    - 只做“触发解析/索引”，不强制结构化抽取
    """
    un = _get_username_from_request(request)
    if not un:
        raise HTTPException(status_code=401, detail="not authenticated")
    fixtures = load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    f = get_folder(tenant_id, folder_id=folder_id)
    if not f:
        raise HTTPException(status_code=404, detail="not found")

    # 可见性：与 kb_folder_resources 一致
    owner = str(f.get("owner_username") or "").strip()
    token = _get_token_from_request(request) or ""
    scope = compute_acl_scope(token, fixtures=fixtures)
    allowed_col_ids = set(scope["allowed_collection_ids"])
    if owner and owner != un:
        raise HTTPException(status_code=403, detail="forbidden")
    if not owner:
        cids = [str(x) for x in (f.get("collection_ids") or []) if str(x).strip()]
        if not any(cid in allowed_col_ids for cid in cids):
            raise HTTPException(status_code=403, detail="forbidden")

    resources = list_folder_resources(tenant_id, folder_id=folder_id)
    doc_ids = [str(r.get("resource_id") or "").strip() for r in (resources or []) if r.get("resource_type") == "doc"]
    doc_ids = [x for x in doc_ids if x]
    if not doc_ids:
        return {"ok": True, "queued": 0, "skipped": 0, "detail": "folder has no docs"}
    queued = 0
    skipped = 0
    for did in doc_ids:
        ok, _ = enqueue_user_doc_task(tenant_id, un, did)
        if ok:
            queued += 1
        else:
            skipped += 1
    return {"ok": True, "queued": queued, "skipped": skipped, "doc_count": len(doc_ids)}


@router.get("/rag-packages/{package_id}")
def rag_package_detail(package_id: str, request: Request):
    if not _get_username_from_request(request):
        raise HTTPException(status_code=401, detail="not authenticated")
    fixtures = load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    d = rag_packages.get_package_detail(tenant_id, package_id)
    if not d:
        raise HTTPException(status_code=404, detail="not found")
    return d


@router.delete("/rag-packages/{package_id}")
def rag_package_delete(package_id: str, request: Request):
    if not _get_username_from_request(request):
        raise HTTPException(status_code=401, detail="not authenticated")
    fixtures = load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    ok = rag_packages.delete_package(tenant_id, package_id)
    if not ok:
        raise HTTPException(status_code=404, detail="not found")
    return {"ok": True}


@router.get("/rag-packages/{package_id}/export")
def rag_package_export(package_id: str, request: Request, profile: str = "standard"):
    if not _get_username_from_request(request):
        raise HTTPException(status_code=401, detail="not authenticated")
    fixtures = load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    prof = (profile or "standard").strip()
    try:
        data, filename = rag_packages.export_package_zip(tenant_id, package_id, prof)  # type: ignore[arg-type]
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="not found") from None
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/rag-packages/{package_id}/preview")
def rag_package_preview(package_id: str, request: Request, kind: str = "merged", filename: str | None = None):
    if not _get_username_from_request(request):
        raise HTTPException(status_code=401, detail="not authenticated")
    fixtures = load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    k = (kind or "").strip()
    if k not in {"merged", "section"}:
        raise HTTPException(status_code=400, detail="invalid kind")
    try:
        return rag_packages.preview_text(tenant_id, package_id, kind=k, filename=filename)  # type: ignore[arg-type]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="not found") from None


class BigPdfTaskResponse(BaseModel):
    task_id: str
    kind: str
    status: str
    stage: str
    progress: int
    detail: str | None = None
    result_package_id: str | None = None


@router.post("/bigpdf/tasks", response_model=BigPdfTaskResponse)
async def bigpdf_create_task(request: Request, file: UploadFile = File(...)):
    un = _get_username_from_request(request)
    if not un:
        raise HTTPException(status_code=401, detail="not authenticated")
    fixtures = load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    raw = await file.read()
    if len(raw) > 200 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件过大（最大 200MB）")
    t = kb_tasks.create_task(tenant_id, un, kind=TASK_KIND_BIGPDF_PARSE, detail=file.filename or "upload")
    prepare_task_input(tenant_id, t["task_id"], filename=file.filename or "upload.pdf", raw=raw)
    ok = enqueue_bigpdf_task(tenant_id, un, t["task_id"])
    if not ok:
        kb_tasks.update_task(tenant_id, t["task_id"], status="failed", stage="failed", progress=100, detail="队列已满，稍后重试")
        raise HTTPException(status_code=503, detail="队列已满，请稍后重试")
    return BigPdfTaskResponse(**kb_tasks.get_task(tenant_id, t["task_id"]))


@router.get("/bigpdf/tasks/{task_id}", response_model=BigPdfTaskResponse)
def bigpdf_get_task(task_id: str, request: Request):
    un = _get_username_from_request(request)
    if not un:
        raise HTTPException(status_code=401, detail="not authenticated")
    fixtures = load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    t = kb_tasks.get_task(tenant_id, task_id)
    if not t:
        raise HTTPException(status_code=404, detail="task not found")
    return BigPdfTaskResponse(**t)


@router.get("/bigpdf/tasks", response_model=dict)
def bigpdf_list_my_tasks(request: Request, limit: int = 30):
    un = _get_username_from_request(request)
    if not un:
        raise HTTPException(status_code=401, detail="not authenticated")
    fixtures = load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    items = kb_tasks.list_my_tasks(tenant_id, un, kind=TASK_KIND_BIGPDF_PARSE, limit=limit)
    return {"items": items}


@router.post("/bigpdf/tasks/{task_id}/retry", response_model=BigPdfTaskResponse)
def bigpdf_retry_task(task_id: str, request: Request):
    """
    仅做站内重试：复用同一个 task_id 的 raw 输入，重新执行 worker。
   （外部端导入/审计暂不在 2.c 范围内）
    """
    un = _get_username_from_request(request)
    if not un:
        raise HTTPException(status_code=401, detail="not authenticated")
    fixtures = load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    t = kb_tasks.get_task(tenant_id, task_id)
    if not t:
        raise HTTPException(status_code=404, detail="task not found")
    # 仅允许本人重试
    # 这里 kb_tasks.get_task 不返回 owner_username；以“能提交任务的人 = token 用户”作为简化约束
    kb_tasks.update_task(
        tenant_id,
        task_id,
        status="queued",
        stage="queued",
        progress=0,
        detail="retry requested",
        payload={"task_id": task_id, "owner_username": un},
    )
    ok = enqueue_bigpdf_task(tenant_id, un, task_id)
    if not ok:
        kb_tasks.update_task(tenant_id, task_id, status="failed", stage="failed", progress=100, detail="队列已满，稍后重试")
        raise HTTPException(status_code=503, detail="队列已满，请稍后重试")
    return BigPdfTaskResponse(**kb_tasks.get_task(tenant_id, task_id))


@router.post("/bigpdf/tasks/{task_id}/cancel")
def bigpdf_cancel_task(task_id: str, request: Request):
    """
    取消一个大 PDF 任务（如果仍在排队或运行中）。
    取消后会立即释放 worker 租约，下次心跳检测到 cancelled 状态后会停止处理。
    """
    un = _get_username_from_request(request)
    if not un:
        raise HTTPException(status_code=401, detail="not authenticated")
    fixtures = load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    t = kb_tasks.get_task(tenant_id, task_id)
    if not t:
        raise HTTPException(status_code=404, detail="task not found")
    # 仅允许本人取消（简化约束：能提交任务的人 = token 用户）
    ok = kb_tasks.cancel_bigpdf_task(tenant_id, task_id)
    if not ok:
        # 任务已经不是 queued/running 状态（比如已经完成或失败），也算"取消不了"
        raise HTTPException(status_code=409, detail="任务无法取消（已结束或正在结束）")
    return {"ok": True, "task_id": task_id, "status": "cancelled"}


# ---------------------------------------------------------------------------
# Phase 1: bigpdf refactor new endpoints
# ---------------------------------------------------------------------------


class BigPdfStatusResponse(BaseModel):
    has_running_task: bool
    running_task: dict[str, Any] | None = None
    queue_position: int | None = None
    queue_length: int = 0


@router.get("/bigpdf/status", response_model=BigPdfStatusResponse)
def bigpdf_get_status(request: Request):
    """Get current bigpdf system status: running task, queue info."""
    un = _get_username_from_request(request)
    if not un:
        raise HTTPException(status_code=401, detail="not authenticated")
    fixtures = load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"

    running = kb_tasks.get_running_task(tenant_id)
    queue_length = kb_tasks.get_queue_length(tenant_id)
    my_queued = kb_tasks.get_user_queued_task(tenant_id, un)

    running_task_out = None
    if running:
        # Calculate estimated remaining time
        estimated_remaining = 0
        if running.get("started_at") and running.get("estimated_duration"):
            from datetime import datetime, timezone
            try:
                started = datetime.fromisoformat(running["started_at"])
                elapsed = (datetime.now(timezone.utc) - started).total_seconds()
                estimated_remaining = max(0, int(running["estimated_duration"] - elapsed))
            except Exception:
                estimated_remaining = running.get("estimated_duration", 0) or 0

        running_task_out = {
            "task_id": running["task_id"],
            "owner": running["owner_username"],
            "is_mine": running["owner_username"] == un,
            "status": running["status"],
            "stage": running["stage"],
            "progress": running["progress"],
            "estimated_remaining": estimated_remaining,
            "file_name": running.get("file_name") or running.get("detail") or "",
            "file_size": running.get("file_size") or 0,
            "page_count": running.get("page_count") or 0,
            "started_at": running.get("started_at") or "",
        }

    return BigPdfStatusResponse(
        has_running_task=running is not None,
        running_task=running_task_out,
        queue_position=my_queued.get("position") if my_queued else None,
        queue_length=queue_length,
    )


class BigPdfCreateTaskResponse(BaseModel):
    task_id: str
    status: str
    estimated_duration: int
    message: str


@router.post("/bigpdf/tasks/enhanced", response_model=BigPdfCreateTaskResponse)
async def bigpdf_create_task_enhanced(
    request: Request,
    file: UploadFile = File(...),
    queue_if_busy: bool = Form(True),
):
    """
    Enhanced create task with queue support.
    If system is busy and queue_if_busy=True, task is queued.
    If queue_if_busy=False, returns 503.
    """
    un = _get_username_from_request(request)
    if not un:
        raise HTTPException(status_code=401, detail="not authenticated")
    fixtures = load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    raw = await file.read()
    if len(raw) > 200 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件过大（最大 200MB）")

    # Check if system is busy
    running = kb_tasks.get_running_task(tenant_id)
    if running and not queue_if_busy:
        raise HTTPException(status_code=503, detail="系统正忙，请稍后重试或选择排队")

    t = kb_tasks.create_task(tenant_id, un, kind=TASK_KIND_BIGPDF_PARSE, detail=file.filename or "upload")
    prepare_task_input(tenant_id, t["task_id"], filename=file.filename or "upload.pdf", raw=raw)

    # Update with file metadata
    kb_tasks.update_task_with_file_info(
        tenant_id,
        t["task_id"],
        file_name=file.filename or "upload.pdf",
        file_size=len(raw),
        page_count=0,  # Frontend will provide this via pdf.js; default to 0 for now
        estimated_duration=kb_tasks.estimate_duration(len(raw)),
    )

    ok = enqueue_bigpdf_task(tenant_id, un, t["task_id"])
    if not ok:
        kb_tasks.update_task(tenant_id, t["task_id"], status="failed", stage="failed", progress=100, detail="队列已满，稍后重试")
        raise HTTPException(status_code=503, detail="队列已满，请稍后重试")

    updated_task = kb_tasks.get_task(tenant_id, t["task_id"])
    est_duration = updated_task.get("estimated_duration", 0) or 0

    return BigPdfCreateTaskResponse(
        task_id=t["task_id"],
        status=updated_task.get("status", "queued") if updated_task else "queued",
        estimated_duration=est_duration,
        message=f"任务已创建，预计解析时间 {est_duration // 60}-{est_duration // 60 + 15} 分钟",
    )


class BigPdfTaskDetailResponse(BaseModel):
    task_id: str
    status: str
    stage: str
    progress: int
    estimated_remaining: int
    elapsed_time: int
    file_name: str | None = None
    file_size: int | None = None
    page_count: int | None = None
    docling_task_id: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None


@router.get("/bigpdf/tasks/{task_id}/detail", response_model=BigPdfTaskDetailResponse)
def bigpdf_get_task_detail(task_id: str, request: Request):
    """Get enhanced task details with file metadata and result info."""
    un = _get_username_from_request(request)
    if not un:
        raise HTTPException(status_code=401, detail="not authenticated")
    fixtures = load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    t = kb_tasks.get_task(tenant_id, task_id)
    if not t:
        raise HTTPException(status_code=404, detail="task not found")

    # Calculate elapsed and remaining
    elapsed_time = 0
    estimated_remaining = 0
    if t.get("started_at"):
        from datetime import datetime, timezone
        try:
            started = datetime.fromisoformat(t["started_at"])
            elapsed_time = int((datetime.now(timezone.utc) - started).total_seconds())
            if t.get("estimated_duration"):
                estimated_remaining = max(0, t["estimated_duration"] - elapsed_time)
        except Exception:
            pass

    result = None
    if t.get("result_package_id"):
        result = {
            "package_id": t["result_package_id"],
            "document_count": t.get("page_count") or 0,
            "folder_path": t.get("detail") or "",
        }

    return BigPdfTaskDetailResponse(
        task_id=t["task_id"],
        status=t["status"],
        stage=t["stage"],
        progress=t["progress"],
        estimated_remaining=estimated_remaining,
        elapsed_time=elapsed_time,
        file_name=t.get("file_name"),
        file_size=t.get("file_size"),
        page_count=t.get("page_count"),
        docling_task_id=t.get("docling_task_id"),
        result=result,
        error=t.get("last_error") or t.get("detail") if t["status"] == "failed" else None,
    )


class BigPdfCancelResponse(BaseModel):
    success: bool
    message: str
    task_status: str


@router.post("/bigpdf/tasks/{task_id}/cancel-enhanced", response_model=BigPdfCancelResponse)
def bigpdf_cancel_task_enhanced(task_id: str, request: Request, force: bool = False):
    """
    Enhanced cancel with soft/force options.
    force=False: soft cancel (mark as user_abandoned, task continues in background)
    force=True: force cancel (restart docling container)
    """
    un = _get_username_from_request(request)
    if not un:
        raise HTTPException(status_code=401, detail="not authenticated")
    fixtures = load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    t = kb_tasks.get_task(tenant_id, task_id)
    if not t:
        raise HTTPException(status_code=404, detail="task not found")

    if force:
        # Force cancel: same as force-cancel endpoint logic
        running = kb_tasks.get_running_task(tenant_id)
        if not running or running["task_id"] != task_id:
            raise HTTPException(status_code=409, detail="该任务不在运行中，无法强制终止")

        # Check permission: admin or owner
        u = get_user(un) or {}
        roles = [str(x).strip().lower() for x in (u.get("roles") or [])]
        is_admin = "admin" in roles or "管理层" in roles
        if not is_admin and running["owner_username"] != un:
            raise HTTPException(status_code=403, detail="无权操作")

        kb_tasks.force_cancel_task(tenant_id, task_id, cancelled_by=un)
        return BigPdfCancelResponse(
            success=True,
            message="已强制终止解析进程",
            task_status="force_cancelled",
        )
    else:
        # Soft cancel: mark as user_abandoned (task continues but user stops tracking)
        ok = kb_tasks.soft_cancel_task(tenant_id, task_id, cancelled_by=un, cancel_type="user_abandoned")
        if not ok:
            raise HTTPException(status_code=409, detail="任务无法取消（已结束或正在结束）")
        return BigPdfCancelResponse(
            success=True,
            message="已取消任务跟踪，解析将在后台继续完成",
            task_status="user_abandoned",
        )


class BigPdfForceCancelResponse(BaseModel):
    success: bool
    message: str
    restarted_at: str


@router.post("/bigpdf/force-cancel", response_model=BigPdfForceCancelResponse)
def bigpdf_force_cancel(request: Request):
    """
    Force cancel current running task by restarting docling container.
    Only admin or task owner can perform this action.
    """
    un = _get_username_from_request(request)
    if not un:
        raise HTTPException(status_code=401, detail="not authenticated")
    fixtures = load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"

    running = kb_tasks.get_running_task(tenant_id)
    if not running:
        raise HTTPException(status_code=404, detail="没有运行中的任务")

    # Permission check: admin or owner
    u = get_user(un) or {}
    roles = [str(x).strip().lower() for x in (u.get("roles") or [])]
    is_admin = "admin" in roles or "管理层" in roles
    if not is_admin and running["owner_username"] != un:
        raise HTTPException(status_code=403, detail="无权操作")

    # Mark task as force_cancelled
    kb_tasks.force_cancel_task(tenant_id, running["task_id"], cancelled_by=un)

    # Execute docker restart
    import subprocess
    from datetime import datetime, timezone
    try:
        subprocess.run(
            ["docker", "restart", "orient-g-docling-1"],
            check=True,
            timeout=30,
        )
        return BigPdfForceCancelResponse(
            success=True,
            message="已强制终止解析进程，docling 容器正在重启",
            restarted_at=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error("Failed to restart docling: %s", e)
        raise HTTPException(status_code=500, detail=f"终止失败: {e}")


class BigPdfQueueResponse(BaseModel):
    running_task: dict[str, Any] | None = None
    queued_tasks: list[dict[str, Any]] = []
    total_queue_length: int = 0


@router.get("/bigpdf/queue", response_model=BigPdfQueueResponse)
def bigpdf_get_queue(request: Request):
    """Get current queue status: running task and queued tasks with positions."""
    un = _get_username_from_request(request)
    if not un:
        raise HTTPException(status_code=401, detail="not authenticated")
    fixtures = load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"

    running = kb_tasks.get_running_task(tenant_id)
    queued = kb_tasks.get_queued_tasks(tenant_id)
    queue_length = kb_tasks.get_queue_length(tenant_id)

    running_out = None
    if running:
        estimated_remaining = 0
        if running.get("started_at") and running.get("estimated_duration"):
            from datetime import datetime, timezone
            try:
                started = datetime.fromisoformat(running["started_at"])
                elapsed = (datetime.now(timezone.utc) - started).total_seconds()
                estimated_remaining = max(0, int(running["estimated_duration"] - elapsed))
            except Exception:
                estimated_remaining = running.get("estimated_duration", 0) or 0

        running_out = {
            "task_id": running["task_id"],
            "owner": running["owner_username"],
            "file_name": running.get("file_name") or running.get("detail") or "",
            "started_at": running.get("started_at") or "",
            "estimated_remaining": estimated_remaining,
        }

    return BigPdfQueueResponse(
        running_task=running_out,
        queued_tasks=queued,
        total_queue_length=queue_length + (1 if running else 0),
    )
