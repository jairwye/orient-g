"""
Orient-G MCP 工具实现（Hermes / orientg_server 共用）。

所有 KB 写操作校验 writable_*；读操作校验 allowed_*。
审计 channel: hermes.mcp.<tool_name>
"""

from __future__ import annotations

import base64
import logging
from typing import Any, Optional

from sqlalchemy import text

from backend.database import get_db
from backend.services import kb_documents as kb_docs
from backend.services.kb_acl_store import set_resource_assignments
from backend.services.kb_folders import bind_resource_to_folder
from backend.services.knowledge_acl import compute_acl_scope, load_fixtures
from backend.services.knowledge_audit import write_event
from backend.services.knowledge_pipeline import ask_knowledge
from backend.services.task_queue import enqueue_user_doc_task

logger = logging.getLogger(__name__)

MCP_CHANNEL_PREFIX = "hermes.mcp"


def resolve_user_token(user_token: str | None, hermes_session_key: str | None = None) -> str:
    """
    解析 MCP 调用使用的 JWT：
    1. 显式 user_token（CLI / 测试）
    2. hermes_session_key → hermes_token_bridge（同进程 /agent）
    3. hermes_session_key → HTTP internal bridge（MCP stdio 子进程）
    4. 环境变量 ORIENTG_USER_TOKEN（开发 Hermes CLI）
    """
    direct = (user_token or "").strip()
    if direct:
        return direct
    from backend.services.hermes_token_bridge import resolve as bridge_resolve

    bridged = bridge_resolve(hermes_session_key)
    if bridged:
        return bridged
    from backend.services.hermes_bridge_http import fetch_remote_session

    remote = fetch_remote_session(hermes_session_key)
    if remote and remote.user_token:
        return str(remote.user_token).strip()
    from backend.services.hermes_shared_session import load_session

    row = load_session(hermes_session_key)
    if row and row.get("user_token"):
        return str(row["user_token"])
    import os

    from backend.config import settings

    env_tok = (os.environ.get("ORIENTG_USER_TOKEN") or "").strip()
    if env_tok and (settings.app_env or "").strip().lower() == "production":
        logger.warning(
            "MCP resolve_user_token fell back to ORIENTG_USER_TOKEN; "
            "use Hermes session_key bridge for per-user ACL in production"
        )
    return env_tok


def _require_mcp_user_token(
    effective_token: str,
    hermes_session_key: str | None,
    *,
    tool: str,
    tenant_id: str,
    username: str | None,
) -> dict[str, Any] | None:
    """MCP 子进程须解析到 JWT；禁止 silent empty ACL（表现为「权限为空」）。"""
    if (effective_token or "").strip():
        return None
    if hermes_session_key:
        return _deny(
            tool,
            "session_token_unresolved",
            tenant_id=tenant_id,
            username=username,
            extra={"hermes_session_key": (hermes_session_key or "")[:32]},
        )
    return _deny(tool, "user_token_required", tenant_id=tenant_id, username=username)


def _audit(
    tenant_id: str,
    *,
    username: str | None,
    tool: str,
    meta: dict[str, Any] | None = None,
    query: str | None = None,
) -> None:
    m = dict(meta or {})
    m["channel"] = f"{MCP_CHANNEL_PREFIX}.{tool}"
    try:
        write_event(tenant_id, username=username, event_type=f"hermes.mcp.{tool}", query=query, meta=m)
    except Exception:
        logger.debug("mcp audit write failed for %s", tool, exc_info=True)


def _username_from_token(user_token: str) -> str | None:
    if not user_token:
        return None
    try:
        import jwt
        from backend.config import settings

        payload = jwt.decode(user_token, settings.auth_secret, algorithms=["HS256"])
        return (payload.get("sub") or "").strip() or None
    except Exception:
        return None


def _scope(user_token: str, fixtures: dict[str, Any] | None = None) -> dict[str, Any]:
    return compute_acl_scope(user_token, fixtures=fixtures or load_fixtures())


def _deny(tool: str, reason: str, *, tenant_id: str, username: str | None, extra: dict | None = None) -> dict[str, Any]:
    meta = {"ok": False, "reason": reason, **(extra or {})}
    _audit(tenant_id, username=username, tool=tool, meta=meta)
    out: dict[str, Any] = {"ok": False, "denied": True, "reason": reason}
    if (tool or "").strip() == "orientg_kb_ask":
        from backend.services.kb_ask_mcp_reply import orientg_kb_ask_denied_hermes_reply

        out["reply"] = orientg_kb_ask_denied_hermes_reply(reason)
    return out


def _doc_writable(scope: dict[str, Any], doc_id: str) -> bool:
    did = str(doc_id or "").strip()
    if not did:
        return False
    return did in set(scope.get("writable_doc_ids") or [])


def _folder_collection_ids(tenant_id: str, folder_id: str) -> list[str]:
    fid = (folder_id or "").strip()
    if not fid:
        return []
    from backend.services.kb_folders import list_folders

    for f in list_folders(tenant_id):
        if str(f.get("folder_id") or "").strip() == fid:
            return [str(x).strip() for x in (f.get("collection_ids") or []) if str(x).strip()]
    return []


def _folder_in_session_scope(tenant_id: str, folder_id: str, root_folder_ids: list[str]) -> bool:
    fid = (folder_id or "").strip()
    if not fid or not root_folder_ids:
        return False
    from backend.services.kb_scope_context import _subtree_folder_ids

    allowed = set(_subtree_folder_ids(tenant_id, root_folder_ids))
    return fid in allowed


def _folder_writable(scope: dict[str, Any], tenant_id: str, folder_id: str, *, username: str | None) -> bool:
    fid = (folder_id or "").strip()
    if not fid:
        return False
    writable_cols = set(scope.get("writable_collection_ids") or [])
    fcols = set(_folder_collection_ids(tenant_id, fid))
    if fcols and fcols.intersection(writable_cols):
        return True
    from backend.services.kb_folders import list_folders

    for f in list_folders(tenant_id):
        if str(f.get("folder_id") or "").strip() != fid:
            continue
        owner = str(f.get("owner_username") or "").strip()
        if username and owner and owner == username and writable_cols:
            return True
        break
    return False


def _resolve_hermes_session_context(hermes_session_key: str | None):
    """本地 session context；MCP 子进程未命中时经 HTTP 拉取 kb_scope。"""
    from backend.services.hermes_session_context import HermesSessionContext, resolve as resolve_ctx

    ctx = resolve_ctx(hermes_session_key)
    if ctx:
        return ctx
    from backend.services.hermes_bridge_http import fetch_remote_session

    remote = fetch_remote_session(hermes_session_key)
    if not remote:
        return None
    return HermesSessionContext(
        allow_kb_write=remote.allow_kb_write,
        kb_scope=dict(remote.kb_scope or {}),
        orientg_route=remote.orientg_route,
        native_mcp_reply=bool(remote.native_mcp_reply),
    )


def _effective_native_mcp_reply(hermes_session_key: str | None) -> bool:
    from backend.config import settings

    if settings.hermes_native_mcp_reply:
        return True
    ctx = _resolve_hermes_session_context(hermes_session_key)
    return bool(ctx and ctx.native_mcp_reply)


def _token_acl_collection_ids(user_token: str) -> list[str]:
    if not user_token:
        return []
    scope = _scope(user_token, load_fixtures())
    return [str(x).strip() for x in (scope.get("allowed_collection_ids") or []) if str(x).strip()]


def _apply_session_kb_scope_for_ask(
    tenant_id: str,
    hermes_session_key: str | None,
    *,
    selected_collection_ids: list[str] | None,
    selected_table_ids: list[str] | None,
    attached_doc_ids: list[str] | None,
    limit_to_attached: bool,
) -> tuple[list[str] | None, list[str] | None, list[str] | None, bool]:
    """
    Hermes MCP 须与 /agent 用户会话 scope 一致（与网关预检索同源）。

    模型常误把 folder_id / 臆造 id 塞进 selected_collection_ids；旧逻辑一旦见到显式
    collection/attached 就 early-return，跳过 session → doc allowed scope empty /
    selected_collection_ids not allowed。有 hermes_session_key 时以 session/JWT 为基线，
    仅把模型传入的合法 collection/table/doc 作增量并入，不得短路或覆盖会话文件夹。
    """
    hermes_cols = [str(x).strip() for x in (selected_collection_ids or []) if str(x).strip()]
    hermes_tables = [str(x).strip() for x in (selected_table_ids or []) if str(x).strip()]
    hermes_attached = [str(x).strip() for x in (attached_doc_ids or []) if str(x).strip()]

    if not hermes_session_key:
        return (
            hermes_cols or None,
            hermes_tables or None,
            hermes_attached or None,
            bool(limit_to_attached),
        )

    from backend.services.orientg_agent_presentation import kb_scope_nonempty

    session_cols: list[str] = []
    session_tables: list[str] = []
    session_attached: list[str] = []
    session_limit = False

    ctx = _resolve_hermes_session_context(hermes_session_key)
    if ctx and kb_scope_nonempty(ctx.kb_scope):
        from backend.services.kb_scope_resolve import resolve_kb_scope_for_ask

        resolved = resolve_kb_scope_for_ask(tenant_id, ctx.kb_scope)
        session_cols = list(resolved.get("collection_ids") or [])
        session_tables = list(resolved.get("table_ids") or [])
        session_attached = list(resolved.get("attached_doc_ids") or [])
        session_limit = bool(resolved.get("limit_to_attached"))
        if session_limit and not session_attached and session_cols:
            session_limit = False

    if not (session_cols or session_tables or session_attached):
        effective_token = resolve_user_token("", hermes_session_key)
        session_cols = _token_acl_collection_ids(effective_token)
        session_tables = []
        session_attached = []
        session_limit = False
        if session_cols:
            logger.info(
                "mcp_kb_scope_fallback token_acl session=%s collections=%d",
                hermes_session_key[:24],
                len(session_cols),
            )

    if session_cols or session_tables or session_attached:
        allowed = set(_token_acl_collection_ids(resolve_user_token("", hermes_session_key)))
        extra_cols = [c for c in hermes_cols if c in allowed] if allowed else []
        extra_tables = [t for t in hermes_tables if t in set(session_tables)] if session_tables else []
        out_cols = list(dict.fromkeys([*session_cols, *extra_cols]))
        out_tables = list(dict.fromkeys([*session_tables, *extra_tables]))
        out_attached = list(dict.fromkeys([*session_attached, *hermes_attached]))
        use_limit = bool(session_limit)
        if use_limit and not out_attached and out_cols:
            use_limit = False
        if extra_cols:
            use_limit = False
        logger.info(
            "mcp_kb_scope_session session=%s collections=%d attached=%d limit=%s hermes_extra_cols=%d",
            hermes_session_key[:24],
            len(out_cols),
            len(out_attached),
            use_limit,
            len(extra_cols),
        )
        return (
            out_cols or None,
            out_tables or None,
            out_attached or None,
            use_limit,
        )

    return (
        hermes_cols or None,
        hermes_tables or None,
        hermes_attached or None,
        bool(limit_to_attached) if hermes_attached else False,
    )


def _check_mcp_write_gate(
    *,
    tool: str,
    tenant_id: str,
    username: str | None,
    scope: dict[str, Any],
    hermes_session_key: str | None,
    folder_id: str | None,
    require_folder: bool = False,
) -> dict[str, Any] | None:
    """
    Hermes 会话写库门禁：须 allow_kb_write + folder 在用户 kb_scope 子树且可写。
    无 hermes_session_key 时（CLI/单测直调 token）仍校验 folder 可写性（若提供 folder_id）。
    """
    fid = (folder_id or "").strip()
    if hermes_session_key:
        ctx = _resolve_hermes_session_context(hermes_session_key)
        if not ctx:
            return _deny(tool, "session_context_missing", tenant_id=tenant_id, username=username)
        if not ctx.allow_kb_write:
            return _deny(tool, "kb_write_not_allowed", tenant_id=tenant_id, username=username)
        roots = list(ctx.kb_scope.get("selected_folder_ids") or [])
        if require_folder or fid:
            if not fid:
                return _deny(tool, "folder_id_required", tenant_id=tenant_id, username=username)
            if roots and not _folder_in_session_scope(tenant_id, fid, roots):
                return _deny(tool, "folder_not_in_kb_scope", tenant_id=tenant_id, username=username)
        elif roots:
            return _deny(tool, "folder_id_required", tenant_id=tenant_id, username=username)
    if fid and not _folder_writable(scope, tenant_id, fid, username=username):
        return _deny(tool, "folder_not_writable", tenant_id=tenant_id, username=username)
    return None


def orientg_kb_ask(
    user_token: str,
    query: str,
    *,
    selected_collection_ids: list[str] | None = None,
    selected_table_ids: list[str] | None = None,
    attached_doc_ids: list[str] | None = None,
    limit_to_attached: bool = False,
    hermes_session_key: str | None = None,
) -> dict[str, Any]:
    effective_token = resolve_user_token(user_token, hermes_session_key)
    fixtures = load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    username = _username_from_token(effective_token)
    deny_tok = _require_mcp_user_token(
        effective_token,
        hermes_session_key,
        tool="orientg_kb_ask",
        tenant_id=tenant_id,
        username=username,
    )
    if deny_tok:
        return deny_tok
    from backend.services.kb_ask_budget import check_and_consume_ask
    from backend.services.hermes_token_bridge import resolve as bridge_resolve

    budget_deny = check_and_consume_ask(hermes_session_key)
    if budget_deny is None and hermes_session_key and not bridge_resolve(hermes_session_key):
        from backend.services.hermes_bridge_http import consume_remote_kb_ask_budget

        budget_deny = consume_remote_kb_ask_budget(hermes_session_key)
    if budget_deny:
        return _deny("orientg_kb_ask", budget_deny, tenant_id=tenant_id, username=username)
    _audit(
        tenant_id,
        username=username,
        tool="orientg_kb_ask",
        query=query,
        meta={"has_attached": bool(attached_doc_ids)},
    )
    (
        selected_collection_ids,
        selected_table_ids,
        attached_doc_ids,
        limit_to_attached,
    ) = _apply_session_kb_scope_for_ask(
        tenant_id,
        hermes_session_key,
        selected_collection_ids=selected_collection_ids,
        selected_table_ids=selected_table_ids,
        attached_doc_ids=attached_doc_ids,
        limit_to_attached=limit_to_attached,
    )
    from backend.services.kb_retrieval_plan import enhance_kb_ask_query

    effective_query = enhance_kb_ask_query(query)

    def _ask(q: str) -> dict[str, Any]:
        return ask_knowledge(
            effective_token,
            q,
            selected_collection_ids=selected_collection_ids,
            selected_table_ids=selected_table_ids,
            fixtures=fixtures,
            attached_doc_ids=attached_doc_ids,
            limit_to_attached=limit_to_attached,
        )

    from backend.services.kb_ask_mcp_reply import personnel_structure_ask_results

    res = personnel_structure_ask_results(_ask, effective_query)
    if res.get("denied"):
        from backend.services.kb_ask_mcp_reply import orientg_kb_ask_denied_hermes_reply

        reason = str(res.get("deny_reason") or "denied").strip() or "denied"
        return {
            "ok": False,
            "denied": True,
            "reason": reason,
            "citations": [],
            "reply": orientg_kb_ask_denied_hermes_reply(reason),
        }
    from backend.config import settings
    from backend.services.kb_ask_mcp_reply import build_kb_ask_mcp_reply

    tenant_id = fixtures.get("tenant_id") or "tenant1"
    mcp_reply, excerpts = build_kb_ask_mcp_reply(
        res,
        query=effective_query,
        tenant_id=tenant_id,
        fixtures=fixtures,
    )
    agent_payload: dict[str, Any] | None = None
    if _effective_native_mcp_reply(hermes_session_key):
        from backend.services.kb_ask_mcp_agent_native import build_hermes_agent_mcp_reply

        mcp_reply, agent_payload = build_hermes_agent_mcp_reply(
            query=effective_query,
            base_reply=mcp_reply,
            excerpts=excerpts,
            citations=list(res.get("citations") or []),
        )
    out: dict[str, Any] = {
        "ok": True,
        "reply": mcp_reply,
        "citations": res.get("citations") or [],
        "evidence_excerpts": excerpts,
    }
    if agent_payload is not None:
        out["agent_payload"] = agent_payload
    return out


def orientg_kb_list_docs(
    user_token: str,
    *,
    folder_id: str | None = None,
    limit: int = 50,
    hermes_session_key: str | None = None,
) -> dict[str, Any]:
    effective_token = resolve_user_token(user_token, hermes_session_key)
    fixtures = load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    username = _username_from_token(effective_token)
    deny_tok = _require_mcp_user_token(
        effective_token,
        hermes_session_key,
        tool="orientg_kb_list_docs",
        tenant_id=tenant_id,
        username=username,
    )
    if deny_tok:
        return deny_tok
    scope = _scope(effective_token, fixtures)
    allowed = set(scope.get("allowed_doc_ids") or [])
    _audit(tenant_id, username=username, tool="orientg_kb_list_docs", meta={"folder_id": folder_id, "limit": limit})

    if not folder_id and hermes_session_key:
        ctx = _resolve_hermes_session_context(hermes_session_key)
        roots = list((ctx.kb_scope if ctx else {}).get("selected_folder_ids") or [])
        if len(roots) == 1:
            folder_id = roots[0]

    if folder_id:
        from backend.services.kb_folders import list_folder_user_doc_ids

        doc_ids = [d for d in list_folder_user_doc_ids(tenant_id, folder_id=folder_id) if d in allowed]
    else:
        doc_ids = sorted(allowed)[: max(1, min(int(limit or 50), 200))]

    if not doc_ids:
        return {"ok": True, "items": []}

    placeholders = ", ".join([f":d{i}" for i in range(len(doc_ids))])
    params: dict[str, Any] = {"t": tenant_id}
    for i, did in enumerate(doc_ids):
        params[f"d{i}"] = did
    with get_db() as db:
        rows = db.execute(
            text(
                f"""
                SELECT doc_id, title, original_filename, status, owner_username, created_at
                FROM kb_user_documents
                WHERE tenant_id=:t AND doc_id IN ({placeholders})
                ORDER BY created_at DESC
                """
            ),
            params,
        ).fetchall()
    items = [
        {
            "doc_id": str(r[0]),
            "title": str(r[1] or ""),
            "original_filename": str(r[2] or ""),
            "status": str(r[3] or ""),
            "owner_username": str(r[4] or ""),
            "created_at": r[5].isoformat() if r[5] else None,
        }
        for r in rows
    ]
    return {"ok": True, "items": items}


def orientg_kb_upload(
    user_token: str,
    *,
    filename: str,
    content_base64: str,
    folder_id: str | None = None,
    hermes_session_key: str | None = None,
) -> dict[str, Any]:
    effective_token = resolve_user_token(user_token, hermes_session_key)
    fixtures = load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    username = _username_from_token(effective_token)
    if not username:
        return _deny("orientg_kb_upload", "invalid_token", tenant_id=tenant_id, username=None)

    scope = _scope(effective_token, fixtures)
    writable_cols = set(scope.get("writable_collection_ids") or [])
    private_cid = kb_docs.dynamic_private_collection_id(username)
    if private_cid not in writable_cols and not writable_cols:
        return _deny("orientg_kb_upload", "no_writable_collection", tenant_id=tenant_id, username=username)

    fid = (folder_id or "").strip()
    gate = _check_mcp_write_gate(
        tool="orientg_kb_upload",
        tenant_id=tenant_id,
        username=username,
        scope=scope,
        hermes_session_key=hermes_session_key,
        folder_id=fid or None,
        require_folder=bool(hermes_session_key),
    )
    if gate:
        return gate

    try:
        raw = base64.b64decode(content_base64 or "", validate=True)
    except Exception:
        return _deny("orientg_kb_upload", "invalid_base64", tenant_id=tenant_id, username=username)

    if len(raw) > 20 * 1024 * 1024:
        return _deny("orientg_kb_upload", "file_too_large", tenant_id=tenant_id, username=username)

    info = kb_docs.upload_user_document_async(tenant_id, username, filename=filename or "upload", raw=raw)
    did = str(info.get("doc_id") or "")
    if not did:
        return {"ok": False, "reason": "upload_failed"}

    ok, _ = enqueue_user_doc_task(tenant_id, username, did)
    if not ok:
        kb_docs.mark_document_failed(tenant_id, did, "队列已满")
        return _deny("orientg_kb_upload", "queue_full", tenant_id=tenant_id, username=username)

    if fid:
        bind_resource_to_folder(tenant_id, folder_id=fid, resource_type="doc", resource_id=did)

    _audit(tenant_id, username=username, tool="orientg_kb_upload", meta={"doc_id": did, "folder_id": fid})
    return {"ok": True, "doc_id": did, "status": "queued", "queued": True}


def orientg_kb_assign(
    user_token: str,
    *,
    doc_id: str,
    collection_ids: list[str],
    folder_id: str | None = None,
    hermes_session_key: str | None = None,
) -> dict[str, Any]:
    effective_token = resolve_user_token(user_token, hermes_session_key)
    fixtures = load_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    username = _username_from_token(effective_token)
    if not username:
        return _deny("orientg_kb_assign", "invalid_token", tenant_id=tenant_id, username=None)

    scope = _scope(effective_token, fixtures)
    did = str(doc_id or "").strip()
    if did not in set(scope.get("allowed_doc_ids") or []):
        return _deny("orientg_kb_assign", "doc_not_readable", tenant_id=tenant_id, username=username)
    if not _doc_writable(scope, did):
        return _deny("orientg_kb_assign", "doc_not_writable", tenant_id=tenant_id, username=username)

    fid = (folder_id or "").strip()
    gate = _check_mcp_write_gate(
        tool="orientg_kb_assign",
        tenant_id=tenant_id,
        username=username,
        scope=scope,
        hermes_session_key=hermes_session_key,
        folder_id=fid or None,
        require_folder=False,
    )
    if gate:
        return gate

    cids = [str(x).strip() for x in (collection_ids or []) if str(x).strip()]
    writable_cols = set(scope.get("writable_collection_ids") or [])
    if cids and not set(cids).issubset(writable_cols):
        return _deny("orientg_kb_assign", "collection_not_writable", tenant_id=tenant_id, username=username)

    if cids:
        set_resource_assignments(tenant_id, resource_type="doc", resource_id=did, collection_ids=cids)
    if fid:
        bind_resource_to_folder(tenant_id, folder_id=fid, resource_type="doc", resource_id=did)

    _audit(
        tenant_id,
        username=username,
        tool="orientg_kb_assign",
        meta={"doc_id": did, "collection_ids": cids, "folder_id": fid},
    )
    return {"ok": True, "doc_id": did, "collection_ids": cids}


def orientg_kb_import_artifact(
    user_token: str,
    *,
    filename: str,
    content_base64: str,
    title: str | None = None,
    folder_id: str | None = None,
    hermes_session_key: str | None = None,
) -> dict[str, Any]:
    """Agent 产物落库（md/xlsx/csv 等），语义同 upload；Hermes 路径须 folder_id 且在 kb_scope 内。"""
    name = (filename or "artifact.md").strip()
    if title:
        stem = name.rsplit(".", 1)[0] if "." in name else name
        ext = name.rsplit(".", 1)[-1] if "." in name else "md"
        safe_title = "".join(c for c in title if c not in '\\/:*?"<>|')[:80]
        if safe_title:
            name = f"{safe_title}.{ext}" if ext else safe_title
    if hermes_session_key and not (folder_id or "").strip():
        fixtures = load_fixtures()
        tenant_id = fixtures.get("tenant_id") or "tenant1"
        username = _username_from_token(resolve_user_token(user_token, hermes_session_key))
        return _deny(
            "orientg_kb_import_artifact",
            "folder_id_required",
            tenant_id=tenant_id,
            username=username,
        )
    return orientg_kb_upload(
        user_token,
        filename=name,
        content_base64=content_base64,
        folder_id=folder_id,
        hermes_session_key=hermes_session_key,
    )
