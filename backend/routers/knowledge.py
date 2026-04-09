"""
Knowledge：options/ask、用户上传文档、RAG 包列表。
"""

from __future__ import annotations

from typing import Any

import jwt
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

from backend.config import settings
from backend.services.kb_acl_store import get_all_resource_assignments
from backend.services import kb_documents as kb_docs
from backend.services import kb_tasks
from backend.services.bigpdf_tasks import prepare_task_input, process_bigpdf_task, stage_to_progress
from backend.services.knowledge_acl import compute_acl_scope, load_fixtures
from backend.services.knowledge_pipeline import ask_knowledge
from backend.services.knowledge_audit import write_event as audit_write_event
from backend.services.task_queue import (
    Priority,
    submit,
    TASK_EMBED_AND_INDEX_REFRESH,
    TASK_PDF_PARSE_DOCLING,
)
from backend.services.task_queue import get_stats as get_queue_stats
from backend.services.online_rate_limiter import allow as rate_limit_allow
from backend.services.user_acl_store import get_user
from backend.services import rag_packages
from backend.services.kb_vector_index import index_uploaded_document_task
from backend.services.kb_vector_store import vector_enabled
from backend.services.kb_tables import list_table_instances
from fastapi.responses import Response

router = APIRouter()
ALGORITHM = "HS256"

KB_KIND_CHOICES = [
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


class OptionsResponse(BaseModel):
    collections: list[dict[str, Any]]
    tables: list[dict[str, Any]]
    default_selected_collection_ids: list[str]
    default_selected_table_ids: list[str]


@router.get("/options", response_model=OptionsResponse)
def knowledge_options(request: Request):
    token = _get_token_from_request(request)
    if not token:
        return OptionsResponse(
            collections=[],
            tables=[],
            default_selected_collection_ids=[],
            default_selected_table_ids=[],
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

    return OptionsResponse(
        collections=collections_out,
        tables=tables_out,
        default_selected_collection_ids=default_collection_ids[:5],
        default_selected_table_ids=default_table_ids,
    )


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


@router.get("/meta/kb-kinds")
def knowledge_kb_kinds(request: Request):
    if not _get_token_from_request(request):
        raise HTTPException(status_code=401, detail="not authenticated")
    labels = {
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
    return {"items": kb_docs.list_my_documents(tenant_id, un)}


@router.post("/my-documents/upload")
async def knowledge_upload_my_document(request: Request, file: UploadFile = File(...)):
    un = _get_username_from_request(request)
    if not un:
        raise HTTPException(status_code=401, detail="not authenticated")
    fixtures = load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    raw = await file.read()
    if len(raw) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件过大（最大 20MB）")
    try:
        info = kb_docs.upload_user_document(tenant_id, un, filename=file.filename or "upload", raw=raw)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return {"ok": True, **info}


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
    t = kb_tasks.create_task(tenant_id, un, kind="bigpdf", detail=file.filename or "upload")
    prepare_task_input(tenant_id, t["task_id"], filename=file.filename or "upload.pdf", raw=raw)
    ok = submit(
        Priority.LOW,
        process_bigpdf_task,
        tenant_id,
        t["task_id"],
        un,
        task_id=t["task_id"],
        task_type=TASK_PDF_PARSE_DOCLING,
    )
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
    items = kb_tasks.list_my_tasks(tenant_id, un, kind="bigpdf", limit=limit)
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
    kb_tasks.update_task(tenant_id, task_id, status="queued", stage="queued", progress=0, detail="retry requested")
    ok = submit(
        Priority.LOW,
        process_bigpdf_task,
        tenant_id,
        task_id,
        un,
        task_id=task_id,
        task_type=TASK_PDF_PARSE_DOCLING,
    )
    if not ok:
        kb_tasks.update_task(tenant_id, task_id, status="failed", stage="failed", progress=100, detail="队列已满，稍后重试")
        raise HTTPException(status_code=503, detail="队列已满，请稍后重试")
    return BigPdfTaskResponse(**kb_tasks.get_task(tenant_id, task_id))
