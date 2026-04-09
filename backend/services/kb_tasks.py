from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from backend.database import get_db


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_task(
    tenant_id: str,
    owner_username: str,
    *,
    kind: str,
    detail: str | None = None,
) -> dict[str, Any]:
    task_id = f"t_{uuid.uuid4().hex}"
    with get_db() as db:
        db.execute(
            text(
                """
                INSERT INTO kb_tasks
                    (task_id, tenant_id, owner_username, kind, status, stage, progress, detail, created_at, updated_at)
                VALUES
                    (:id, :tid, :u, :k, 'queued', 'queued', 0, :d, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
            ),
            {"id": task_id, "tid": tenant_id, "u": owner_username, "k": kind, "d": (detail or "").strip() or None},
        )
    return {"task_id": task_id, "kind": kind, "status": "queued", "stage": "queued", "progress": 0, "detail": detail}


def update_task(
    tenant_id: str,
    task_id: str,
    *,
    status: str | None = None,
    stage: str | None = None,
    progress: int | None = None,
    detail: str | None = None,
    result_package_id: str | None = None,
) -> None:
    sets: list[str] = ["updated_at=CURRENT_TIMESTAMP"]
    params: dict[str, Any] = {"tid": tenant_id, "id": task_id}
    if status is not None:
        sets.append("status=:st")
        params["st"] = status
    if stage is not None:
        sets.append("stage=:sg")
        params["sg"] = stage
    if progress is not None:
        sets.append("progress=:pg")
        params["pg"] = max(0, min(100, int(progress)))
    if detail is not None:
        sets.append("detail=:dt")
        params["dt"] = (detail or "").strip() or None
    if result_package_id is not None:
        sets.append("result_package_id=:rp")
        params["rp"] = result_package_id
    sql = "UPDATE kb_tasks SET " + ", ".join(sets) + " WHERE tenant_id=:tid AND task_id=:id"
    with get_db() as db:
        db.execute(text(sql), params)


def get_task(tenant_id: str, task_id: str) -> dict[str, Any] | None:
    with get_db() as db:
        row = db.execute(
            text(
                """
                SELECT task_id, kind, status, stage, progress, detail, result_package_id, created_at, updated_at
                FROM kb_tasks
                WHERE tenant_id=:t AND task_id=:id
                """
            ),
            {"t": tenant_id, "id": task_id},
        ).fetchone()
    if not row:
        return None
    return {
        "task_id": str(row[0]),
        "kind": str(row[1] or ""),
        "status": str(row[2] or ""),
        "stage": str(row[3] or ""),
        "progress": int(row[4] or 0),
        "detail": str(row[5] or "") if row[5] else None,
        "result_package_id": str(row[6] or "") if row[6] else None,
        "created_at": row[7].isoformat() if row[7] else None,
        "updated_at": row[8].isoformat() if row[8] else None,
    }


def list_my_tasks(tenant_id: str, owner_username: str, *, kind: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    where = "tenant_id=:t AND owner_username=:u"
    params: dict[str, Any] = {"t": tenant_id, "u": owner_username, "lim": max(1, min(200, int(limit)))}
    if kind:
        where += " AND kind=:k"
        params["k"] = kind
    with get_db() as db:
        rows = db.execute(
            text(
                f"""
                SELECT task_id, kind, status, stage, progress, detail, result_package_id, created_at, updated_at
                FROM kb_tasks
                WHERE {where}
                ORDER BY created_at DESC
                LIMIT :lim
                """
            ),
            params,
        ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "task_id": str(r[0]),
                "kind": str(r[1] or ""),
                "status": str(r[2] or ""),
                "stage": str(r[3] or ""),
                "progress": int(r[4] or 0),
                "detail": str(r[5] or "") if r[5] else None,
                "result_package_id": str(r[6] or "") if r[6] else None,
                "created_at": r[7].isoformat() if r[7] else None,
                "updated_at": r[8].isoformat() if r[8] else None,
            }
        )
    return out

