from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

from backend.database import get_db

ROLE_MANAGEMENT = "管理层"


def is_system_admin_role(roles: list[str] | None) -> bool:
    return any(str(r).strip().lower() == "admin" for r in (roles or []))


def is_management_role(roles: list[str] | None) -> bool:
    return any(str(r).strip() == ROLE_MANAGEMENT for r in (roles or []))


def _roles_to_json(roles: list[str]) -> str:
    return json.dumps([str(x).strip() for x in (roles or []) if str(x).strip()], ensure_ascii=False)


def _roles_from_json(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        arr = json.loads(raw)
        if isinstance(arr, list):
            return [str(x).strip() for x in arr if str(x).strip()]
    except Exception:
        pass
    return []


def list_users() -> list[dict[str, Any]]:
    with get_db() as db:
        users = db.execute(
            text(
                """
                SELECT username, password_hash, roles_json, is_active
                FROM app_users
                ORDER BY username
                """
            )
        ).fetchall()
        dept_rows = db.execute(
            text(
                """
                SELECT username, department_id, is_department_lead
                FROM user_department_roles
                """
            )
        ).fetchall()
        proj_rows = db.execute(
            text(
                """
                SELECT username, project_id, is_project_lead
                FROM user_project_roles
                """
            )
        ).fetchall()

    dept_map: dict[str, tuple[str, bool]] = {}
    for r in dept_rows:
        dept_map[str(r[0])] = (str(r[1] or ""), bool(r[2]))

    proj_map: dict[str, list[dict[str, Any]]] = {}
    for r in proj_rows:
        proj_map.setdefault(str(r[0]), []).append({"project_id": str(r[1]), "is_project_lead": bool(r[2])})

    out: list[dict[str, Any]] = []
    for u in users:
        username = str(u[0])
        dept_id, dept_lead = dept_map.get(username, ("", False))
        out.append(
            {
                "username": username,
                "password_hash": str(u[1] or ""),
                "roles": _roles_from_json(u[2]),
                "department": dept_id,
                "is_department_lead": dept_lead,
                "projects": proj_map.get(username, []),
                "is_active": bool(u[3]),
            }
        )
    return out


def get_user(username: str) -> dict[str, Any] | None:
    username_l = (username or "").strip().lower()
    if not username_l:
        return None
    for u in list_users():
        if (u.get("username") or "").strip().lower() == username_l:
            return u
    return None


def upsert_user(
    username: str,
    *,
    password_hash: str,
    roles: list[str],
    department: str = "",
    is_department_lead: bool = False,
    projects: list[dict[str, Any]] | None = None,
    is_active: bool = True,
) -> None:
    uname = (username or "").strip()
    if not uname:
        return
    with get_db() as db:
        db.execute(
            text(
                """
                INSERT INTO app_users (username, password_hash, roles_json, is_active)
                VALUES (:u, :ph, :roles, :active)
                ON CONFLICT (username) DO UPDATE
                SET password_hash = EXCLUDED.password_hash,
                    roles_json = EXCLUDED.roles_json,
                    is_active = EXCLUDED.is_active
                """
            ),
            {"u": uname, "ph": password_hash, "roles": _roles_to_json(roles), "active": bool(is_active)},
        )
        db.execute(
            text("DELETE FROM user_department_roles WHERE username = :u"),
            {"u": uname},
        )
        if (department or "").strip():
            db.execute(
                text(
                    """
                    INSERT INTO user_department_roles (username, department_id, is_department_lead)
                    VALUES (:u, :d, :lead)
                    """
                ),
                {"u": uname, "d": (department or "").strip(), "lead": bool(is_department_lead)},
            )
        db.execute(text("DELETE FROM user_project_roles WHERE username = :u"), {"u": uname})
        for p in projects or []:
            pid = str((p or {}).get("project_id") or "").strip()
            if not pid:
                continue
            db.execute(
                text(
                    """
                    INSERT INTO user_project_roles (username, project_id, is_project_lead)
                    VALUES (:u, :pid, :lead)
                    """
                ),
                {"u": uname, "pid": pid, "lead": bool((p or {}).get("is_project_lead"))},
            )


def delete_user(username: str) -> None:
    uname = (username or "").strip()
    if not uname:
        return
    with get_db() as db:
        db.execute(text("DELETE FROM user_project_roles WHERE username = :u"), {"u": uname})
        db.execute(text("DELETE FROM user_department_roles WHERE username = :u"), {"u": uname})
        db.execute(text("DELETE FROM app_users WHERE username = :u"), {"u": uname})


def set_user_password(username: str, password_hash: str) -> None:
    uname = (username or "").strip()
    if not uname:
        return
    with get_db() as db:
        db.execute(
            text("UPDATE app_users SET password_hash = :ph WHERE username = :u"),
            {"u": uname, "ph": password_hash},
        )


def list_projects() -> list[dict[str, Any]]:
    with get_db() as db:
        rows = db.execute(
            text(
                """
                SELECT project_id, name, COALESCE(department_id, '')
                FROM projects
                ORDER BY project_id
                """
            )
        ).fetchall()
    return [{"project_id": str(r[0]), "name": str(r[1] or ""), "department_id": str(r[2] or "")} for r in rows]


def get_user_acl_overrides(username: str) -> dict[str, dict[str, set[str]]]:
    uname = (username or "").strip()
    with get_db() as db:
        rows = db.execute(
            text(
                """
                SELECT resource_type, resource_id, effect
                FROM kb_user_acl_overrides
                WHERE username = :u
                """
            ),
            {"u": uname},
        ).fetchall()
    out: dict[str, dict[str, set[str]]] = {
        "allow": {"collection": set(), "doc": set(), "table": set()},
        "deny": {"collection": set(), "doc": set(), "table": set()},
    }
    for r in rows:
        rtype = str(r[0] or "")
        rid = str(r[1] or "")
        effect = "allow" if str(r[2] or "").lower() != "deny" else "deny"
        if rtype in {"collection", "doc", "table"} and rid:
            out[effect][rtype].add(rid)
    return out


def set_user_acl_overrides(username: str, overrides: list[dict[str, str]]) -> None:
    uname = (username or "").strip()
    with get_db() as db:
        db.execute(text("DELETE FROM kb_user_acl_overrides WHERE username = :u"), {"u": uname})
        for ov in overrides or []:
            rtype = str((ov or {}).get("resource_type") or "").strip()
            rid = str((ov or {}).get("resource_id") or "").strip()
            effect = str((ov or {}).get("effect") or "allow").strip().lower()
            if rtype not in {"collection", "doc", "table"} or not rid or effect not in {"allow", "deny"}:
                continue
            db.execute(
                text(
                    """
                    INSERT INTO kb_user_acl_overrides (username, resource_type, resource_id, effect)
                    VALUES (:u, :t, :rid, :e)
                    """
                ),
                {"u": uname, "t": rtype, "rid": rid, "e": effect},
            )


def get_user_collection_write_overrides(username: str) -> dict[str, set[str]]:
    """
    返回：
    - allow: set(collection_id)
    - deny: set(collection_id)
    """
    uname = (username or "").strip()
    with get_db() as db:
        rows = db.execute(
            text(
                """
                SELECT collection_id, effect
                FROM kb_user_collection_write_overrides
                WHERE username = :u
                """
            ),
            {"u": uname},
        ).fetchall()
    out = {"allow": set(), "deny": set()}
    for r in rows:
        cid = str(r[0] or "").strip()
        eff = str(r[1] or "allow").strip().lower()
        if not cid or eff not in {"allow", "deny"}:
            continue
        out["allow" if eff != "deny" else "deny"].add(cid)
    return out


def set_user_collection_write_overrides(username: str, overrides: list[dict[str, str]]) -> None:
    """
    overrides item: {effect:'allow'|'deny', collection_id:'...'}
    """
    uname = (username or "").strip()
    with get_db() as db:
        db.execute(text("DELETE FROM kb_user_collection_write_overrides WHERE username = :u"), {"u": uname})
        for ov in overrides or []:
            cid = str((ov or {}).get("collection_id") or "").strip()
            eff = str((ov or {}).get("effect") or "allow").strip().lower()
            if not cid or eff not in {"allow", "deny"}:
                continue
            db.execute(
                text(
                    """
                    INSERT INTO kb_user_collection_write_overrides (username, collection_id, effect)
                    VALUES (:u, :cid, :e)
                    """
                ),
                {"u": uname, "cid": cid, "e": eff},
            )
