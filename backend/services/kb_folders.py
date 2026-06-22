from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import text

from backend.database import get_db
from backend.services.kb_collections import (
    dynamic_private_collection_id,
    resolve_share_collection_ids,
    share_kinds_for_collection_ids,
)


def _new_folder_id(prefix: str = "f") -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _safe_name(name: str, default: str) -> str:
    nm = (name or "").strip()
    return (nm[:200] or default).strip() or default


def compute_subtree_doc_counts(folders: list[dict[str, Any]]) -> dict[str, int]:
    """本文件夹 + 所有后代文件夹的文档数（基于 resource_counts.doc 递归求和）。"""
    direct_counts: dict[str, int] = {}
    children_map: dict[str, list[str]] = {}
    for f in folders:
        fid = str(f.get("folder_id") or "").strip()
        if not fid:
            continue
        direct_counts[fid] = int((f.get("resource_counts") or {}).get("doc") or 0)
        pfid = str(f.get("parent_folder_id") or "").strip() or None
        if pfid:
            children_map.setdefault(pfid, []).append(fid)
    cache: dict[str, int] = {}

    def total(fid: str) -> int:
        if fid in cache:
            return cache[fid]
        n = direct_counts.get(fid, 0)
        for child in children_map.get(fid, []):
            n += total(child)
        cache[fid] = n
        return n

    return {fid: total(fid) for fid in direct_counts}


def list_folders(tenant_id: str) -> list[dict[str, Any]]:
    tid = (tenant_id or "").strip() or "tenant1"
    with get_db() as db:
        rows = db.execute(
            text(
                """
                SELECT f.folder_id, f.name, f.kind, f.scope_json, f.owner_username, f.created_by, f.created_at, f.updated_at, f.parent_folder_id
                FROM kb_folders f
                WHERE f.tenant_id=:t
                ORDER BY f.name
                """
            ),
            {"t": tid},
        ).fetchall()
        maps = db.execute(
            text(
                """
                SELECT folder_id, collection_id
                FROM kb_folder_collections
                WHERE tenant_id=:t
                """
            ),
            {"t": tid},
        ).fetchall()
        rmap = db.execute(
            text(
                """
                SELECT folder_id, resource_type, resource_id
                FROM kb_folder_resources
                WHERE tenant_id=:t
                """
            ),
            {"t": tid},
        ).fetchall()
        doc_count_rows = db.execute(
            text(
                """
                SELECT fr.folder_id, COUNT(DISTINCT fr.resource_id) AS cnt
                FROM kb_folder_resources fr
                INNER JOIN kb_user_documents d
                  ON d.tenant_id = fr.tenant_id AND d.doc_id = fr.resource_id
                WHERE fr.tenant_id = :t AND fr.resource_type = 'doc'
                GROUP BY fr.folder_id
                """
            ),
            {"t": tid},
        ).fetchall()
    folder_to_cols: dict[str, list[str]] = {}
    for r in maps:
        fid = str(r[0] or "").strip()
        cid = str(r[1] or "").strip()
        if fid and cid:
            folder_to_cols.setdefault(fid, []).append(cid)
    folder_to_counts: dict[str, dict[str, int]] = {}
    for r in doc_count_rows:
        fid = str(r[0] or "").strip()
        if fid:
            folder_to_counts[fid] = {"doc": int(r[1] or 0)}
    for r in rmap:
        fid = str(r[0] or "").strip()
        rt = str(r[1] or "").strip()
        rid = str(r[2] or "").strip()
        if not fid or not rt or not rid or rt == "doc":
            continue
        d = folder_to_counts.setdefault(fid, {})
        d[rt] = int(d.get(rt) or 0) + 1
    out: list[dict[str, Any]] = []
    for r in rows:
        fid = str(r[0] or "").strip()
        if not fid:
            continue
        scope_raw = str(r[3] or "").strip()
        try:
            scope = json.loads(scope_raw) if scope_raw else {}
        except Exception:
            scope = {}
        if not isinstance(scope, dict):
            scope = {}
        out.append(
            {
                "folder_id": fid,
                "name": str(r[1] or "").strip() or fid,
                "kind": str(r[2] or "").strip() or None,
                "scope": scope,
                "owner_username": str(r[4] or "").strip() or None,
                "created_by": str(r[5] or "").strip() or None,
                "created_at": r[6].isoformat() if getattr(r[6], "isoformat", None) else None,
                "updated_at": r[7].isoformat() if getattr(r[7], "isoformat", None) else None,
                "parent_folder_id": str(r[8] or "").strip() or None,
                "collection_ids": sorted(set(folder_to_cols.get(fid, []))),
                "resource_counts": folder_to_counts.get(fid, {}),
            }
        )
    subtree_counts = compute_subtree_doc_counts(out)
    try:
        from backend.services.knowledge_acl import load_fixtures

        fixtures = load_fixtures()
    except Exception:
        fixtures = {}
    for item in out:
        fid = str(item.get("folder_id") or "").strip()
        item["subtree_doc_count"] = subtree_counts.get(fid, 0)
        cids = list(item.get("collection_ids") or [])
        sk = share_kinds_for_collection_ids(fixtures, cids)
        primary = str(item.get("kind") or "").strip() or "Private"
        merged_kinds: list[str] = []
        seen_k: set[str] = set()
        for k in [primary, *sk]:
            if k and k not in seen_k:
                seen_k.add(k)
                merged_kinds.append(k)
        item["share_kinds"] = merged_kinds
    return out


def upsert_folder(
    tenant_id: str,
    *,
    folder_id: str,
    name: str,
    created_by: str | None = None,
    collection_ids: list[str] | None = None,
    kind: str | None = None,
    scope: dict[str, Any] | None = None,
    owner_username: str | None = None,
    parent_folder_id: str | None = None,
) -> None:
    tid = (tenant_id or "").strip() or "tenant1"
    fid = (folder_id or "").strip()
    if not fid:
        raise ValueError("folder_id required")
    nm = _safe_name(name, fid)
    cols = [str(x).strip() for x in (collection_ids or []) if str(x).strip()]
    scope_json = json.dumps(scope or {}, ensure_ascii=False)
    with get_db() as db:
        db.execute(
            text(
                """
                INSERT INTO kb_folders (folder_id, tenant_id, name, kind, scope_json, owner_username, created_by, updated_at, parent_folder_id)
                VALUES (:fid, :t, :n, :k, :sj, :ou, :cb, CURRENT_TIMESTAMP, :pf)
                ON CONFLICT (folder_id) DO UPDATE
                SET name = EXCLUDED.name,
                    kind = EXCLUDED.kind,
                    scope_json = EXCLUDED.scope_json,
                    owner_username = EXCLUDED.owner_username,
                    parent_folder_id = EXCLUDED.parent_folder_id,
                    updated_at = CURRENT_TIMESTAMP
                """
            ),
            {
                "fid": fid,
                "t": tid,
                "n": nm,
                "k": (kind or "").strip() or None,
                "sj": scope_json,
                "ou": (owner_username or "").strip() or None,
                "cb": (created_by or "").strip() or None,
                "pf": (parent_folder_id or "").strip() or None,
            },
        )
        if collection_ids is not None:
            db.execute(
                text(
                    """
                    DELETE FROM kb_folder_collections
                    WHERE tenant_id=:t AND folder_id=:fid
                    """
                ),
                {"t": tid, "fid": fid},
            )
            for cid in cols:
                db.execute(
                    text(
                        """
                        INSERT INTO kb_folder_collections (tenant_id, folder_id, collection_id)
                        VALUES (:t, :fid, :cid)
                        ON CONFLICT (tenant_id, folder_id, collection_id) DO NOTHING
                        """
                    ),
                    {"t": tid, "fid": fid, "cid": cid},
                )
        # Update non-null fields
        db.execute(
            text(
                """
                UPDATE kb_folders
                SET kind = :k,
                    scope_json = :sj,
                    owner_username = :ou,
                    updated_at = CURRENT_TIMESTAMP
                WHERE tenant_id=:t AND folder_id=:fid
                """
            ),
            {
                "t": tid,
                "fid": fid,
                "k": (kind or "").strip() or None,
                "sj": scope_json,
                "ou": (owner_username or "").strip() or None,
            },
        )


def create_folder(
    tenant_id: str,
    *,
    name: str,
    created_by: str | None = None,
    kind: str | None = None,
    scope: dict[str, Any] | None = None,
    owner_username: str | None = None,
    parent_folder_id: str | None = None,
) -> dict[str, Any]:
    tid = (tenant_id or "").strip() or "tenant1"
    fid = _new_folder_id("f")
    upsert_folder(
        tid,
        folder_id=fid,
        name=name,
        created_by=created_by,
        collection_ids=[],
        kind=kind,
        scope=scope or {},
        owner_username=owner_username,
        parent_folder_id=parent_folder_id,
    )
    return {"folder_id": fid}


def delete_folder(tenant_id: str, *, folder_id: str) -> bool:
    tid = (tenant_id or "").strip() or "tenant1"
    fid = (folder_id or "").strip()
    if not fid:
        return False
    with get_db() as db:
        db.execute(text("DELETE FROM kb_folder_resources WHERE tenant_id=:t AND folder_id=:fid"), {"t": tid, "fid": fid})
        db.execute(text("DELETE FROM kb_folder_collections WHERE tenant_id=:t AND folder_id=:fid"), {"t": tid, "fid": fid})
        res = db.execute(text("DELETE FROM kb_folders WHERE tenant_id=:t AND folder_id=:fid"), {"t": tid, "fid": fid})
        return bool(getattr(res, "rowcount", 0) or 0) > 0


def get_folder(tenant_id: str, *, folder_id: str) -> dict[str, Any] | None:
    tid = (tenant_id or "").strip() or "tenant1"
    fid = (folder_id or "").strip()
    if not fid:
        return None
    with get_db() as db:
        row = db.execute(
            text(
                """
                SELECT folder_id, name, kind, scope_json, owner_username, created_by, created_at, updated_at, parent_folder_id
                FROM kb_folders
                WHERE tenant_id=:t AND folder_id=:fid
                """
            ),
            {"t": tid, "fid": fid},
        ).fetchone()
        if not row:
            return None
        cols = db.execute(
            text(
                """
                SELECT collection_id
                FROM kb_folder_collections
                WHERE tenant_id=:t AND folder_id=:fid
                ORDER BY collection_id
                """
            ),
            {"t": tid, "fid": fid},
        ).fetchall()
    scope_raw = str(row[3] or "").strip()
    try:
        scope = json.loads(scope_raw) if scope_raw else {}
    except Exception:
        scope = {}
    if not isinstance(scope, dict):
        scope = {}
    return {
        "folder_id": str(row[0]),
        "name": str(row[1] or "").strip(),
        "kind": str(row[2] or "").strip() or None,
        "scope": scope,
        "owner_username": str(row[4] or "").strip() or None,
        "created_by": str(row[5] or "").strip() or None,
        "created_at": row[6].isoformat() if getattr(row[6], "isoformat", None) else None,
        "updated_at": row[7].isoformat() if getattr(row[7], "isoformat", None) else None,
        "parent_folder_id": str(row[8] or "").strip() or None,
        "collection_ids": [str(r[0]) for r in cols if r and r[0]],
    }


def ensure_private_folder(tenant_id: str, *, username: str) -> str:
    """
    为用户确保一个“私有文件夹”（稳定 id），并绑定其动态私有 collection。
    """
    tid = (tenant_id or "").strip() or "tenant1"
    un = (username or "").strip()
    if not un:
        raise ValueError("username required")
    fid = f"f_private_{''.join(c if c.isalnum() or c in '_-' else '_' for c in un)}"
    pcid = dynamic_private_collection_id(un)
    upsert_folder(
        tid,
        folder_id=fid,
        name="我的私人知识库",
        created_by=un,
        collection_ids=[pcid],
        kind="Private",
        scope={},
        owner_username=un,
    )
    return fid


def bind_resource_to_folder(
    tenant_id: str,
    *,
    folder_id: str,
    resource_type: str,
    resource_id: str,
) -> None:
    tid = (tenant_id or "").strip() or "tenant1"
    fid = (folder_id or "").strip()
    rt = (resource_type or "").strip()
    rid = (resource_id or "").strip()
    if not fid or rt not in {"doc", "table"} or not rid:
        raise ValueError("invalid bind params")
    # 保证“一个资源只属于一个文件夹”（folder-only 模型）
    with get_db() as db:
        db.execute(
            text(
                """
                DELETE FROM kb_folder_resources
                WHERE tenant_id=:t AND resource_type=:rt AND resource_id=:rid
                """
            ),
            {"t": tid, "rt": rt, "rid": rid},
        )
        db.execute(
            text(
                """
                INSERT INTO kb_folder_resources (tenant_id, folder_id, resource_type, resource_id)
                VALUES (:t, :fid, :rt, :rid)
                ON CONFLICT (tenant_id, folder_id, resource_type, resource_id) DO NOTHING
                """
            ),
            {"t": tid, "fid": fid, "rt": rt, "rid": rid},
        )
        db.execute(text("UPDATE kb_folders SET updated_at=CURRENT_TIMESTAMP WHERE tenant_id=:t AND folder_id=:fid"), {"t": tid, "fid": fid})


def add_resource_to_folder_extra(
    tenant_id: str,
    *,
    folder_id: str,
    resource_type: str,
    resource_id: str,
) -> None:
    """
    在**不删除**其它文件夹绑定的前提下，将资源额外绑定到目标文件夹（「复制到文件夹」）。
    与 bind_resource_to_folder（移动：先删后绑）区分。
    """
    tid = (tenant_id or "").strip() or "tenant1"
    fid = (folder_id or "").strip()
    rt = (resource_type or "").strip()
    rid = (resource_id or "").strip()
    if not fid or rt not in {"doc", "table"} or not rid:
        raise ValueError("invalid bind params")
    with get_db() as db:
        db.execute(
            text(
                """
                INSERT INTO kb_folder_resources (tenant_id, folder_id, resource_type, resource_id)
                VALUES (:t, :fid, :rt, :rid)
                ON CONFLICT (tenant_id, folder_id, resource_type, resource_id) DO NOTHING
                """
            ),
            {"t": tid, "fid": fid, "rt": rt, "rid": rid},
        )
        db.execute(text("UPDATE kb_folders SET updated_at=CURRENT_TIMESTAMP WHERE tenant_id=:t AND folder_id=:fid"), {"t": tid, "fid": fid})


def unlink_doc_from_folder(
    tenant_id: str,
    *,
    folder_id: str,
    doc_id: str,
    owner_username: str,
) -> None:
    """从指定文件夹移除文档绑定；若文档不再属于任何文件夹，则挂回该用户的私有文件夹。"""
    tid = (tenant_id or "").strip() or "tenant1"
    fid = (folder_id or "").strip()
    did = (doc_id or "").strip()
    un = (owner_username or "").strip()
    if not fid or not did or not un:
        raise ValueError("invalid unlink params")
    with get_db() as db:
        db.execute(
            text(
                """
                DELETE FROM kb_folder_resources
                WHERE tenant_id=:t AND folder_id=:fid AND resource_type='doc' AND resource_id=:did
                """
            ),
            {"t": tid, "fid": fid, "did": did},
        )
        n = db.execute(
            text(
                """
                SELECT COUNT(*) FROM kb_folder_resources
                WHERE tenant_id=:t AND resource_type='doc' AND resource_id=:did
                """
            ),
            {"t": tid, "did": did},
        ).scalar()
        cnt = int(n or 0)
    if cnt == 0:
        pf = ensure_private_folder(tid, username=un)
        bind_resource_to_folder(tid, folder_id=pf, resource_type="doc", resource_id=did)


def list_folder_user_doc_ids(tenant_id: str, *, folder_id: str) -> list[str]:
    """本文件夹内、在 kb_user_documents 中仍存在的 doc_id（不含 rp_* 等大 PDF 包占位绑定）。"""
    tid = (tenant_id or "").strip() or "tenant1"
    fid = (folder_id or "").strip()
    if not fid:
        return []
    with get_db() as db:
        rows = db.execute(
            text(
                """
                SELECT fr.resource_id
                FROM kb_folder_resources fr
                INNER JOIN kb_user_documents d
                  ON d.tenant_id = fr.tenant_id AND d.doc_id = fr.resource_id
                WHERE fr.tenant_id = :t AND fr.folder_id = :fid AND fr.resource_type = 'doc'
                ORDER BY fr.created_at DESC
                """
            ),
            {"t": tid, "fid": fid},
        ).fetchall()
    return [str(r[0] or "").strip() for r in rows if str(r[0] or "").strip()]


def prune_stale_folder_doc_bindings(tenant_id: str, *, folder_id: str) -> int:
    """移除文件夹内已不存在于 kb_user_documents 的 doc 绑定（含历史 rp_* 占位）。"""
    tid = (tenant_id or "").strip() or "tenant1"
    fid = (folder_id or "").strip()
    if not fid:
        return 0
    with get_db() as db:
        res = db.execute(
            text(
                """
                DELETE FROM kb_folder_resources fr
                WHERE fr.tenant_id = :t AND fr.folder_id = :fid AND fr.resource_type = 'doc'
                  AND NOT EXISTS (
                    SELECT 1 FROM kb_user_documents d
                    WHERE d.tenant_id = fr.tenant_id AND d.doc_id = fr.resource_id
                  )
                """
            ),
            {"t": tid, "fid": fid},
        )
        return int(getattr(res, "rowcount", 0) or 0)


def list_folder_resources(tenant_id: str, *, folder_id: str) -> list[dict[str, Any]]:
    tid = (tenant_id or "").strip() or "tenant1"
    fid = (folder_id or "").strip()
    if not fid:
        return []
    with get_db() as db:
        rows = db.execute(
            text(
                """
                SELECT resource_type, resource_id, created_at
                FROM kb_folder_resources
                WHERE tenant_id=:t AND folder_id=:fid
                ORDER BY created_at DESC
                """
            ),
            {"t": tid, "fid": fid},
        ).fetchall()
    out = []
    for r in rows:
        out.append(
            {
                "resource_type": str(r[0] or "").strip(),
                "resource_id": str(r[1] or "").strip(),
                "created_at": r[2].isoformat() if getattr(r[2], "isoformat", None) else None,
            }
        )
    return out


def folder_visible_to_user(
    folder: dict[str, Any],
    *,
    username: str,
    allowed_collection_ids: set[str],
) -> bool:
    """与 /api/knowledge/folders 列表可见性一致。"""
    cids = [str(x) for x in (folder.get("collection_ids") or []) if str(x).strip()]
    if any(cid in allowed_collection_ids for cid in cids):
        return True
    owner = (str(folder.get("owner_username") or "").strip() or "")
    return bool(owner and owner == (username or "").strip())


def collect_doc_ids_in_visible_folders(
    tenant_id: str,
    *,
    username: str,
    allowed_collection_ids: set[str] | list[str],
) -> set[str]:
    """
    文件夹已分享到用户可见的 collection（如部门公共库）时，
    其 kb_folder_resources 内文档应可读，即使 doc 仍挂在 owner 私有 collection 上。
    """
    tid = (tenant_id or "").strip() or "tenant1"
    uname = (username or "").strip()
    allowed = set(allowed_collection_ids or [])
    if not allowed:
        return set()
    out: set[str] = set()
    for f in list_folders(tid):
        if not folder_visible_to_user(f, username=uname, allowed_collection_ids=allowed):
            continue
        fid = str(f.get("folder_id") or "").strip()
        if not fid:
            continue
        for did in collect_subtree_doc_ids(tid, fid):
            out.add(did)
    return out


def collect_subtree_doc_ids(tenant_id: str, folder_id: str) -> list[str]:
    """递归收集 folder 及所有后代 folder 中绑定的 doc_id（去重，顺序稳定）。"""
    tid = (tenant_id or "").strip() or "tenant1"
    root = (folder_id or "").strip()
    if not root:
        return []
    folders = list_folders(tid)
    children_map: dict[str, list[str]] = {}
    for f in folders:
        fid = str(f.get("folder_id") or "").strip()
        if not fid:
            continue
        parent = str(f.get("parent_folder_id") or "").strip() or None
        if parent:
            children_map.setdefault(parent, []).append(fid)

    out: list[str] = []
    seen: set[str] = set()
    stack = [root]
    while stack:
        fid = stack.pop()
        for did in list_folder_user_doc_ids(tid, folder_id=fid):
            if did not in seen:
                out.append(did)
                seen.add(did)
        for child in children_map.get(fid, []):
            stack.append(child)
    return out


def set_folder_collections(tenant_id: str, *, folder_id: str, collection_ids: list[str]) -> None:
    tid = (tenant_id or "").strip() or "tenant1"
    fid = (folder_id or "").strip()
    cols = [str(x).strip() for x in (collection_ids or []) if str(x).strip()]
    with get_db() as db:
        db.execute(text("DELETE FROM kb_folder_collections WHERE tenant_id=:t AND folder_id=:fid"), {"t": tid, "fid": fid})
        for cid in sorted(set(cols)):
            db.execute(
                text(
                    """
                    INSERT INTO kb_folder_collections (tenant_id, folder_id, collection_id)
                    VALUES (:t, :fid, :cid)
                    ON CONFLICT (tenant_id, folder_id, collection_id) DO NOTHING
                    """
                ),
                {"t": tid, "fid": fid, "cid": cid},
            )
        db.execute(text("UPDATE kb_folders SET updated_at=CURRENT_TIMESTAMP WHERE tenant_id=:t AND folder_id=:fid"), {"t": tid, "fid": fid})


def backfill_uploaded_docs_to_private_folders(tenant_id: str) -> dict[str, int]:
    """
    一次性回填：把缺少 folder 绑定的用户上传文档（ud_*）归入其 owner 的私有文件夹。
    只做绑定关系，不改业务数据。
    """
    tid = (tenant_id or "").strip() or "tenant1"
    with get_db() as db:
        rows = db.execute(
            text(
                """
                SELECT d.doc_id, d.owner_username
                FROM kb_user_documents d
                WHERE d.tenant_id=:t
                  AND NOT EXISTS (
                    SELECT 1 FROM kb_folder_resources r
                    WHERE r.tenant_id=:t AND r.resource_type='doc' AND r.resource_id=d.doc_id
                  )
                ORDER BY d.created_at ASC
                """
            ),
            {"t": tid},
        ).fetchall()
    total = 0
    for r in rows:
        did = str(r[0] or "").strip()
        ou = str(r[1] or "").strip()
        if not did or not ou:
            continue
        fid = ensure_private_folder(tid, username=ou)
        bind_resource_to_folder(tid, folder_id=fid, resource_type="doc", resource_id=did)
        total += 1
    return {"bound_docs": total}


def _append_share_scope(scope: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
    out = dict(scope or {})
    history: list[dict[str, Any]] = []
    raw_hist = out.get("share_scopes")
    if isinstance(raw_hist, list):
        history = [x for x in raw_hist if isinstance(x, dict)]
    legacy = out.get("share_add")
    if isinstance(legacy, dict) and legacy not in history:
        history.append(legacy)
    history.append(entry)
    out["share_scopes"] = history
    out["share_add"] = entry
    return out


def _kind_after_additive_share(folder: dict[str, Any], kb_kind: str, target: str) -> str:
    """管理层为加法式共享：不覆盖已有部门/项目/公司库的树归属。"""
    if (target or "").strip().lower() == "management":
        cur = str(folder.get("kind") or "").strip()
        if cur and cur not in {"", "Private", "ManagementPublic"}:
            return cur
    return kb_kind


def merge_collections_into_subtree_docs(
    tenant_id: str,
    *,
    folder_id: str,
    collection_ids: list[str],
) -> int:
    from backend.services.kb_acl_store import merge_resource_assignments

    tid = (tenant_id or "").strip() or "tenant1"
    fid = (folder_id or "").strip()
    cols = [str(x).strip() for x in (collection_ids or []) if str(x).strip()]
    if not fid or not cols:
        return 0
    n = 0
    for did in collect_subtree_doc_ids(tid, fid):
        merge_resource_assignments(tid, resource_type="doc", resource_id=did, collection_ids=cols)
        n += 1
    return n


def share_folder_to_kb_kind(
    tenant_id: str,
    fixtures: dict[str, Any],
    *,
    folder_id: str,
    kb_kind: str,
    department_ids: list[str] | None = None,
    project_ids: list[str] | None = None,
    company_public: bool = False,
) -> list[str]:
    """
    folder-only 模型：共享以 folder 为单位，folder 的 collection 映射成为 folder 对外可见性的“权威集合”。
    """
    tid = (tenant_id or "").strip() or "tenant1"
    fid = (folder_id or "").strip()
    if not fid:
        raise ValueError("folder_id required")
    department_ids = department_ids or []
    project_ids = project_ids or []

    extra: list[str] = []
    if company_public:
        extra.extend(
            resolve_share_collection_ids(
                fixtures, tid, kb_kind="CompanyPublic", department_ids=[], project_ids=[], company_public=True
            )
        )
    extra.extend(
        resolve_share_collection_ids(
            fixtures,
            tid,
            kb_kind=kb_kind,
            department_ids=department_ids,
            project_ids=project_ids,
            company_public=False,
        )
    )
    extra = sorted(set([x for x in extra if x]))
    set_folder_collections(tid, folder_id=fid, collection_ids=extra)
    # 同步 folder 元信息（kind/scope_json）
    scope = {"department_ids": department_ids, "project_ids": project_ids, "company_public": bool(company_public)}
    with get_db() as db:
        db.execute(
            text(
                """
                UPDATE kb_folders
                SET kind=:k, scope_json=:sj, updated_at=CURRENT_TIMESTAMP
                WHERE tenant_id=:t AND folder_id=:fid
                """
            ),
            {"t": tid, "fid": fid, "k": (kb_kind or "").strip() or None, "sj": json.dumps(scope, ensure_ascii=False)},
        )
    return extra


def share_folder_scope(
    tenant_id: str,
    fixtures: dict[str, Any],
    *,
    folder_id: str,
    target: str,
    department_ids: list[str] | None = None,
    project_ids: list[str] | None = None,
) -> list[str]:
    """
    新语义：共享文件夹到 公司/部门/项目（可撤销）。
    - company：CompanyPublic
    - department：DeptPublic + department_ids
    - project：ProjectPublic + project_ids
    """
    tgt = (target or "").strip().lower()
    if tgt == "company":
        return share_folder_to_kb_kind(tenant_id, fixtures, folder_id=folder_id, kb_kind="CompanyPublic", company_public=True)
    if tgt == "department":
        return share_folder_to_kb_kind(
            tenant_id,
            fixtures,
            folder_id=folder_id,
            kb_kind="DeptPublic",
            department_ids=list(department_ids or []),
            project_ids=[],
            company_public=False,
        )
    if tgt == "project":
        return share_folder_to_kb_kind(
            tenant_id,
            fixtures,
            folder_id=folder_id,
            kb_kind="ProjectPublic",
            department_ids=[],
            project_ids=list(project_ids or []),
            company_public=False,
        )
    raise ValueError("invalid target")


def share_folder_add_scope(
    tenant_id: str,
    fixtures: dict[str, Any],
    *,
    folder_id: str,
    target: str,
    access_kind: str = "public",  # public|lead（仅 department/project 生效）
    department_ids: list[str] | None = None,
    project_ids: list[str] | None = None,
    company_public: bool = False,
) -> list[str]:
    """
    新语义：共享（加法，不是覆盖）。
    - 物理上仍是同一个 folder/doc；只是在 ACL 层面追加可见集合。
    - 保留 owner 的动态私有 collection（owner 仍可在“私人”里看到）。
    - 同时把 folder.kind 设为目标 kind（让共享目标库能“调用/看到”该文件夹）。
      注：当前数据模型只有一个 kind 字段，无法表达“同时属于多个库”，因此采用“目标库可见 + 私人仍可见”的折中。
    """
    tid = (tenant_id or "").strip() or "tenant1"
    fid = (folder_id or "").strip()
    if not fid:
        raise ValueError("folder_id required")
    f = get_folder(tid, folder_id=fid)
    if not f:
        raise ValueError("folder not found")
    owner = str(f.get("owner_username") or "").strip()
    if not owner:
        raise ValueError("folder has no owner")
    pcid = dynamic_private_collection_id(owner)

    tgt = (target or "").strip().lower()
    ak = (access_kind or "").strip().lower()
    if ak not in {"public", "lead"}:
        ak = "public"

    kb_kind = "Private"
    extra: list[str] = []
    department_ids = list(department_ids or [])
    project_ids = list(project_ids or [])

    if tgt == "company":
        kb_kind = "CompanyPublic"
        extra.extend(resolve_share_collection_ids(fixtures, tid, kb_kind="CompanyPublic", department_ids=[], project_ids=[], company_public=True))
    elif tgt == "department":
        kb_kind = "DeptLead" if ak == "lead" else "DeptPublic"
        extra.extend(resolve_share_collection_ids(fixtures, tid, kb_kind=kb_kind, department_ids=department_ids, project_ids=[], company_public=False))
    elif tgt == "project":
        kb_kind = "ProjectLead" if ak == "lead" else "ProjectPublic"
        extra.extend(resolve_share_collection_ids(fixtures, tid, kb_kind=kb_kind, department_ids=[], project_ids=project_ids, company_public=False))
    elif tgt == "management":
        kb_kind = "ManagementPublic"
        extra.extend(
            resolve_share_collection_ids(
                fixtures, tid, kb_kind="ManagementPublic", department_ids=[], project_ids=[], company_public=False
            )
        )
    else:
        raise ValueError("invalid target")

    cur = [str(x) for x in (f.get("collection_ids") or []) if str(x).strip()]
    merged = sorted(set([pcid, *cur, *[x for x in extra if x]]))
    set_folder_collections(tid, folder_id=fid, collection_ids=merged)

    existing_scope = f.get("scope") if isinstance(f.get("scope"), dict) else {}
    share_entry = {
        "target": tgt,
        "access_kind": ak,
        "department_ids": department_ids,
        "project_ids": project_ids,
        "company_public": bool(company_public) or kb_kind == "CompanyPublic",
    }
    scope = _append_share_scope(existing_scope, share_entry)
    kind_to_set = _kind_after_additive_share(f, kb_kind, tgt)
    with get_db() as db:
        db.execute(
            text(
                """
                UPDATE kb_folders
                SET kind=:k, scope_json=:sj, updated_at=CURRENT_TIMESTAMP
                WHERE tenant_id=:t AND folder_id=:fid
                """
            ),
            {"t": tid, "fid": fid, "k": kind_to_set, "sj": json.dumps(scope, ensure_ascii=False)},
        )
    if tgt == "management":
        apply_management_share_acl(tid, folder_id=fid, shared_by=owner)
    return merged


def apply_management_share_acl(tenant_id: str, *, folder_id: str, shared_by: str) -> None:
    from backend.services import kb_documents as kbd

    tid = (tenant_id or "").strip() or "tenant1"
    for did in collect_subtree_doc_ids(tid, folder_id):
        kbd.merge_special_doc_acl(tid, did, {"allow_management": True, "allow_owner": True})
        kbd.add_management_doc_share(did, shared_by)


def revoke_management_share_acl_for_folder(tenant_id: str, *, folder_id: str) -> None:
    from backend.services import kb_documents as kbd

    tid = (tenant_id or "").strip() or "tenant1"
    for did in collect_subtree_doc_ids(tid, folder_id):
        kbd.clear_management_special_acl(tid, did)
        kbd.revoke_management_doc_share(did)


def unshare_folder_to_private(tenant_id: str, *, folder_id: str) -> list[str]:
    """
    撤销共享：把文件夹恢复为私有（仅 owner 可见）。
    语义：folder_collections 仅绑定 owner 的动态私有 collection，并更新 kind/scope_json。
    """
    tid = (tenant_id or "").strip() or "tenant1"
    fid = (folder_id or "").strip()
    if not fid:
        raise ValueError("folder_id required")
    f = get_folder(tid, folder_id=fid)
    if not f:
        raise ValueError("folder not found")
    owner = str(f.get("owner_username") or "").strip()
    if not owner:
        raise ValueError("folder has no owner")
    pcid = dynamic_private_collection_id(owner)
    revoke_management_share_acl_for_folder(tid, folder_id=fid)
    set_folder_collections(tid, folder_id=fid, collection_ids=[pcid])
    with get_db() as db:
        db.execute(
            text(
                """
                UPDATE kb_folders
                SET kind='Private', scope_json='{}', owner_username=:ou, updated_at=CURRENT_TIMESTAMP
                WHERE tenant_id=:t AND folder_id=:fid
                """
            ),
            {"t": tid, "fid": fid, "ou": owner},
        )
    return [pcid]

