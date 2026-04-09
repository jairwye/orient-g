"""
KB ACL Store：Project lead/member policy、private owner mapping、resource->collection assignments。

B(rel_only) 落地要求：关系与分配数据在 PostgreSQL 中可配置、可验收。
文档/表对象内容仍由 fixtures 或消费侧对象层提供。
"""

from __future__ import annotations

from typing import Any, Iterable

from sqlalchemy import text

from backend.database import get_db


def get_project_members(tenant_id: str, project_id: str) -> dict[str, str]:
    """
    返回：{ username: membership_role('lead'|'member') }
    """
    with get_db() as db:
        rows = db.execute(
            text(
                """
            SELECT username, membership_role
            FROM kb_project_members
            WHERE tenant_id = :tid AND project_id = :pid
            """
            ),
            {"tid": tenant_id, "pid": project_id},
        ).fetchall()
    return {r[0]: r[1] for r in rows}


def get_project_policy(tenant_id: str, project_id: str) -> dict[str, Any] | None:
    with get_db() as db:
        row = db.execute(
            text(
                """
            SELECT allow_leads, allow_members
            FROM kb_project_access_policy
            WHERE tenant_id = :tid AND project_id = :pid
            """
            ),
            {"tid": tenant_id, "pid": project_id},
        ).fetchone()
    if not row:
        return None
    return {"allow_leads": bool(row[0]), "allow_members": bool(row[1])}


def set_project_policy(tenant_id: str, project_id: str, *, allow_leads: bool, allow_members: bool) -> None:
    with get_db() as db:
        db.execute(
            text(
                """
            INSERT INTO kb_project_access_policy (tenant_id, project_id, allow_leads, allow_members)
            VALUES (:tid, :pid, :al, :am)
            ON CONFLICT (tenant_id, project_id) DO UPDATE
            SET allow_leads = EXCLUDED.allow_leads,
                allow_members = EXCLUDED.allow_members
            """
            ),
            {"tid": tenant_id, "pid": project_id, "al": bool(allow_leads), "am": bool(allow_members)},
        )


def set_project_members(
    tenant_id: str,
    project_id: str,
    *,
    leads: Iterable[str],
    members: Iterable[str],
) -> None:
    # 先删再插，避免残留
    with get_db() as db:
        db.execute(
            text(
                """
            DELETE FROM kb_project_members
            WHERE tenant_id = :tid AND project_id = :pid
            """
            ),
            {"tid": tenant_id, "pid": project_id},
        )
        for u in leads or []:
            uname = (u or "").strip()
            if not uname:
                continue
            db.execute(
                text(
                    """
                INSERT INTO kb_project_members (tenant_id, project_id, username, membership_role)
                VALUES (:tid, :pid, :un, 'lead')
                    """
                ),
                {"tid": tenant_id, "pid": project_id, "un": uname},
            )
        for u in members or []:
            uname = (u or "").strip()
            if not uname:
                continue
            db.execute(
                text(
                    """
                INSERT INTO kb_project_members (tenant_id, project_id, username, membership_role)
                VALUES (:tid, :pid, :un, 'member')
                    """
                ),
                {"tid": tenant_id, "pid": project_id, "un": uname},
            )


def get_private_owner_map(tenant_id: str) -> dict[str, str]:
    """
    返回：{ private_collection_id: owner_username }
    """
    with get_db() as db:
        rows = db.execute(
            text(
                """
            SELECT private_collection_id, owner_username
            FROM kb_private_collection_owner
            WHERE tenant_id = :tid
            """
            ),
            {"tid": tenant_id},
        ).fetchall()
    return {r[0]: r[1] for r in rows}


def set_private_owner(tenant_id: str, private_collection_id: str, owner_username: str) -> None:
    with get_db() as db:
        db.execute(
            text(
                """
            INSERT INTO kb_private_collection_owner (tenant_id, private_collection_id, owner_username)
            VALUES (:tid, :pcid, :owner)
            ON CONFLICT (tenant_id, private_collection_id) DO UPDATE
            SET owner_username = EXCLUDED.owner_username
            """
            ),
            {"tid": tenant_id, "pcid": private_collection_id, "owner": owner_username},
        )


def get_all_resource_assignments(tenant_id: str, *, resource_type: str) -> list[dict[str, Any]]:
    """
    返回：[ {resource_type, resource_id, collection_id}, ...]
    """
    with get_db() as db:
        rows = db.execute(
            text(
                """
            SELECT resource_type, resource_id, collection_id
            FROM kb_resource_collection_assignments
            WHERE tenant_id = :tid AND resource_type = :rtype
            """
            ),
            {"tid": tenant_id, "rtype": resource_type},
        ).fetchall()
    return [{"resource_type": r[0], "resource_id": r[1], "collection_id": r[2]} for r in rows]


def set_resource_assignments(
    tenant_id: str,
    *,
    resource_type: str,
    resource_id: str,
    collection_ids: Iterable[str],
) -> None:
    collection_ids = [str(x).strip() for x in collection_ids or [] if str(x).strip()]
    with get_db() as db:
        db.execute(
            text(
                """
            DELETE FROM kb_resource_collection_assignments
            WHERE tenant_id = :tid AND resource_type = :rtype AND resource_id = :rid
            """
            ),
            {"tid": tenant_id, "rtype": resource_type, "rid": resource_id},
        )
        for cid in collection_ids:
            db.execute(
                text(
                    """
                INSERT INTO kb_resource_collection_assignments (tenant_id, resource_type, resource_id, collection_id)
                VALUES (:tid, :rtype, :rid, :cid)
                    """
                ),
                {"tid": tenant_id, "rtype": resource_type, "rid": resource_id, "cid": cid},
            )


def get_department_policy(tenant_id: str, department_id: str) -> dict[str, Any] | None:
    with get_db() as db:
        row = db.execute(
            text(
                """
            SELECT allow_leads, allow_members
            FROM kb_department_access_policy
            WHERE tenant_id = :tid AND department_id = :did
            """
            ),
            {"tid": tenant_id, "did": department_id},
        ).fetchone()
    if not row:
        return None
    return {"allow_leads": bool(row[0]), "allow_members": bool(row[1])}


def set_department_policy(tenant_id: str, department_id: str, *, allow_leads: bool, allow_members: bool) -> None:
    with get_db() as db:
        db.execute(
            text(
                """
            INSERT INTO kb_department_access_policy (tenant_id, department_id, allow_leads, allow_members)
            VALUES (:tid, :did, :al, :am)
            ON CONFLICT (tenant_id, department_id) DO UPDATE
            SET allow_leads = EXCLUDED.allow_leads,
                allow_members = EXCLUDED.allow_members
            """
            ),
            {"tid": tenant_id, "did": department_id, "al": bool(allow_leads), "am": bool(allow_members)},
        )


def get_resource_owner_map(tenant_id: str, *, resource_type: str) -> dict[str, str]:
    """
    返回：{ resource_id: owner_username }
    """
    with get_db() as db:
        rows = db.execute(
            text(
                """
            SELECT resource_id, owner_username
            FROM kb_resource_owner
            WHERE tenant_id = :tid AND resource_type = :rtype
            """
            ),
            {"tid": tenant_id, "rtype": resource_type},
        ).fetchall()
    return {str(r[0]): str(r[1] or "") for r in rows if str(r[0] or "").strip() and str(r[1] or "").strip()}


def get_doc_collection_ids(tenant_id: str, doc_id: str) -> list[str]:
    did = (doc_id or "").strip()
    if not did:
        return []
    with get_db() as db:
        rows = db.execute(
            text(
                """
            SELECT collection_id
            FROM kb_resource_collection_assignments
            WHERE tenant_id = :tid AND resource_type = 'doc' AND resource_id = :rid
            ORDER BY collection_id
            """
            ),
            {"tid": tenant_id, "rid": did},
        ).fetchall()
    return [str(r[0]) for r in rows if r and r[0]]


def get_collection_scope(tenant_id: str, collection_id: str) -> dict[str, Any]:
    cid = (collection_id or "").strip()
    if not cid:
        return {}
    with get_db() as db:
        row = db.execute(
            text(
                """
            SELECT scope_kind, scope_json
            FROM kb_collection_scope
            WHERE tenant_id = :tid AND collection_id = :cid
            """
            ),
            {"tid": tenant_id, "cid": cid},
        ).fetchone()
    if not row:
        return {}
    try:
        import json

        data = json.loads(row[1] or "{}")
        if isinstance(data, dict):
            data["_scope_kind"] = str(row[0] or "")
            return data
    except Exception:
        pass
    return {}


def set_resource_owner(tenant_id: str, *, resource_type: str, resource_id: str, owner_username: str) -> None:
    rid = (resource_id or "").strip()
    owner = (owner_username or "").strip()
    if not rid or not owner:
        return
    with get_db() as db:
        db.execute(
            text(
                """
            INSERT INTO kb_resource_owner (tenant_id, resource_type, resource_id, owner_username)
            VALUES (:tid, :rtype, :rid, :owner)
            ON CONFLICT (tenant_id, resource_type, resource_id) DO UPDATE
            SET owner_username = EXCLUDED.owner_username
            """
            ),
            {"tid": tenant_id, "rtype": resource_type, "rid": rid, "owner": owner},
        )

