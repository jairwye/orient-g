from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from backend.config import settings
from backend.database import get_db

QUEUE_PRIORITY_HIGH = 0
QUEUE_PRIORITY_LOW = 1
_supports_persisted_queue: bool | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def supports_persisted_queue() -> bool:
    global _supports_persisted_queue
    if _supports_persisted_queue is not None:
        return _supports_persisted_queue
    try:
        with get_db() as db:
            rows = db.execute(
                text(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name='kb_tasks'
                    """
                )
            ).fetchall()
        cols = {str(r[0] or "").strip().lower() for r in rows}
        _supports_persisted_queue = {"queue_priority", "payload_json", "lease_until"}.issubset(cols)
    except Exception:
        _supports_persisted_queue = False
    return bool(_supports_persisted_queue)


def create_task(
    tenant_id: str,
    owner_username: str,
    *,
    kind: str,
    detail: str | None = None,
) -> dict[str, Any]:
    task_id = f"t_{uuid.uuid4().hex}"
    with get_db() as db:
        if supports_persisted_queue():
            db.execute(
                text(
                    """
                    INSERT INTO kb_tasks
                        (task_id, tenant_id, owner_username, kind, status, stage, progress, detail, queue_priority, attempts, max_attempts, next_run_at, created_at, updated_at)
                    VALUES
                        (:id, :tid, :u, :k, 'queued', 'queued', 0, :d, :pri, 0, :max_attempts, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """
                ),
                {
                    "id": task_id,
                    "tid": tenant_id,
                    "u": owner_username,
                    "k": kind,
                    "d": (detail or "").strip() or None,
                    "pri": QUEUE_PRIORITY_LOW,
                    "max_attempts": int(settings.queue_task_max_attempts),
                },
            )
        else:
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


def enqueue_task(
    tenant_id: str,
    owner_username: str,
    *,
    kind: str,
    payload: dict[str, Any],
    task_id: str | None = None,
    detail: str | None = None,
    priority: int = QUEUE_PRIORITY_LOW,
    max_attempts: int | None = None,
    dedupe_key: str | None = None,
) -> str:
    if not supports_persisted_queue():
        return str(task_id or f"t_{uuid.uuid4().hex}")
    tid = str(task_id or f"t_{uuid.uuid4().hex}").strip()
    if not tid:
        tid = f"t_{uuid.uuid4().hex}"
    payload_json = json.dumps(payload or {}, ensure_ascii=False)
    maxa = max(1, int(max_attempts or settings.queue_task_max_attempts))
    with get_db() as db:
        if dedupe_key:
            row = db.execute(
                text(
                    """
                    SELECT task_id
                    FROM kb_tasks
                    WHERE tenant_id=:t AND dedupe_key=:dk AND status IN ('queued', 'running')
                    ORDER BY created_at DESC
                    LIMIT 1
                    """
                ),
                {"t": tenant_id, "dk": str(dedupe_key)},
            ).fetchone()
            if row:
                return str(row[0])
        db.execute(
            text(
                """
                INSERT INTO kb_tasks
                    (task_id, tenant_id, owner_username, kind, status, stage, progress, detail, payload_json, queue_priority, attempts, max_attempts, dedupe_key, next_run_at, created_at, updated_at)
                VALUES
                    (:id, :tid, :u, :k, 'queued', 'queued', 0, :d, :payload, :pri, 0, :maxa, :dk, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (task_id) DO UPDATE
                SET payload_json=EXCLUDED.payload_json,
                    queue_priority=EXCLUDED.queue_priority,
                    status='queued',
                    stage='queued',
                    progress=0,
                    detail=EXCLUDED.detail,
                    next_run_at=CURRENT_TIMESTAMP,
                    updated_at=CURRENT_TIMESTAMP
                """
            ),
            {
                "id": tid,
                "tid": tenant_id,
                "u": owner_username,
                "k": kind,
                "d": (detail or "").strip() or None,
                "payload": payload_json,
                "pri": int(priority),
                "maxa": maxa,
                "dk": (str(dedupe_key).strip() if dedupe_key else None),
            },
        )
    return tid


def count_queue(priority: int | None = None) -> int:
    if not supports_persisted_queue():
        return 0
    cond = "status IN ('queued', 'running')"
    params: dict[str, Any] = {}
    if priority is not None:
        cond += " AND queue_priority=:p"
        params["p"] = int(priority)
    with get_db() as db:
        row = db.execute(text(f"SELECT COUNT(*) FROM kb_tasks WHERE {cond}"), params).fetchone()
    return int(row[0] if row else 0)


def queue_overview() -> dict[str, int]:
    if not supports_persisted_queue():
        return {"queued": 0, "running": 0, "done": 0, "failed": 0}
    with get_db() as db:
        rows = db.execute(
            text(
                """
                SELECT status, COUNT(*)::int
                FROM kb_tasks
                WHERE kind IN ('bigpdf', 'user_doc_parse')
                GROUP BY status
                """
            )
        ).fetchall()
    out = {"queued": 0, "running": 0, "done": 0, "failed": 0}
    for r in rows:
        st = str(r[0] or "").strip().lower()
        if st in out:
            out[st] = int(r[1] or 0)
    return out


def list_failed_tasks(kind: str, *, limit: int = 100) -> list[dict[str, Any]]:
    if not supports_persisted_queue():
        return []
    with get_db() as db:
        rows = db.execute(
            text(
                """
                SELECT tenant_id, task_id, payload_json, detail, last_error
                FROM kb_tasks
                WHERE kind=:k AND status='failed'
                ORDER BY updated_at DESC
                LIMIT :lim
                """
            ),
            {"k": kind, "lim": max(1, int(limit))},
        ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        payload = {}
        try:
            payload = json.loads(str(r[2] or "{}"))
        except Exception:
            payload = {}
        out.append(
            {
                "tenant_id": str(r[0] or ""),
                "task_id": str(r[1] or ""),
                "payload": payload,
                "detail": str(r[3] or "") if r[3] else None,
                "last_error": str(r[4] or "") if r[4] else None,
            }
        )
    return out


def claim_next_task(*, worker_id: str, lease_seconds: int, accepted_kinds: list[str] | None = None) -> dict[str, Any] | None:
    if not supports_persisted_queue():
        return None
    kinds = [str(x).strip() for x in (accepted_kinds or []) if str(x).strip()]
    where_kind = ""
    params: dict[str, Any] = {"wid": worker_id, "lease_s": max(30, int(lease_seconds))}
    if kinds:
        where_kind = " AND kind = ANY(:kinds)"
        params["kinds"] = kinds
    with get_db() as db:
        row = db.execute(
            text(
                f"""
                WITH picked AS (
                    SELECT task_id
                    FROM kb_tasks
                    WHERE status='queued'
                      AND COALESCE(next_run_at, CURRENT_TIMESTAMP) <= CURRENT_TIMESTAMP
                      {where_kind}
                    ORDER BY queue_priority ASC, created_at ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                UPDATE kb_tasks k
                SET status='running',
                    stage=CASE WHEN k.stage IN ('queued', 'failed') THEN 'running' ELSE k.stage END,
                    attempts=COALESCE(k.attempts, 0) + 1,
                    started_at=COALESCE(k.started_at, CURRENT_TIMESTAMP),
                    heartbeat_at=CURRENT_TIMESTAMP,
                    lease_until=(CURRENT_TIMESTAMP + (:lease_s * INTERVAL '1 second')),
                    worker_id=:wid,
                    updated_at=CURRENT_TIMESTAMP,
                    last_error=NULL
                FROM picked
                WHERE k.task_id = picked.task_id
                RETURNING
                    k.task_id, k.tenant_id, k.owner_username, k.kind, k.status, k.stage,
                    k.progress, k.detail, k.result_package_id, k.payload_json, k.attempts,
                    k.max_attempts, k.queue_priority, k.created_at, k.updated_at
                """
            ),
            params,
        ).fetchone()
    if not row:
        return None
    payload: dict[str, Any] = {}
    try:
        payload = json.loads(str(row[9] or "{}"))
    except Exception:
        payload = {}
    return {
        "task_id": str(row[0]),
        "tenant_id": str(row[1] or ""),
        "owner_username": str(row[2] or ""),
        "kind": str(row[3] or ""),
        "status": str(row[4] or ""),
        "stage": str(row[5] or ""),
        "progress": int(row[6] or 0),
        "detail": str(row[7] or "") if row[7] else None,
        "result_package_id": str(row[8] or "") if row[8] else None,
        "payload": payload,
        "attempts": int(row[10] or 0),
        "max_attempts": int(row[11] or 0),
        "queue_priority": int(row[12] or QUEUE_PRIORITY_LOW),
        "created_at": row[13].isoformat() if row[13] else None,
        "updated_at": row[14].isoformat() if row[14] else None,
    }


def heartbeat_task(tenant_id: str, task_id: str, *, worker_id: str, lease_seconds: int) -> None:
    if not supports_persisted_queue():
        return
    with get_db() as db:
        db.execute(
            text(
                """
                UPDATE kb_tasks
                SET heartbeat_at=CURRENT_TIMESTAMP,
                    lease_until=(CURRENT_TIMESTAMP + (:lease_s * INTERVAL '1 second')),
                    updated_at=CURRENT_TIMESTAMP
                WHERE tenant_id=:t AND task_id=:id AND status='running' AND worker_id=:wid
                """
            ),
            {"t": tenant_id, "id": task_id, "wid": worker_id, "lease_s": max(30, int(lease_seconds))},
        )


def finish_task(
    tenant_id: str,
    task_id: str,
    *,
    worker_id: str,
    status: str = "done",
    stage: str | None = None,
    progress: int | None = None,
    detail: str | None = None,
    result_package_id: str | None = None,
) -> None:
    if not supports_persisted_queue():
        return
    sets = [
        "status=:st",
        "stage=:sg",
        "updated_at=CURRENT_TIMESTAMP",
        "finished_at=CURRENT_TIMESTAMP",
        "lease_until=NULL",
        "worker_id=NULL",
        "heartbeat_at=CURRENT_TIMESTAMP",
    ]
    params: dict[str, Any] = {
        "t": tenant_id,
        "id": task_id,
        "wid": worker_id,
        "st": status,
        "sg": stage or ("done" if status == "done" else status),
    }
    if progress is not None:
        sets.append("progress=:pg")
        params["pg"] = max(0, min(100, int(progress)))
    if detail is not None:
        sets.append("detail=:dt")
        params["dt"] = (detail or "").strip() or None
    if result_package_id is not None:
        sets.append("result_package_id=:rp")
        params["rp"] = result_package_id
    with get_db() as db:
        db.execute(
            text(f"UPDATE kb_tasks SET {', '.join(sets)} WHERE tenant_id=:t AND task_id=:id AND worker_id=:wid"),
            params,
        )


def fail_or_retry_task(
    tenant_id: str,
    task_id: str,
    *,
    worker_id: str,
    error: str,
    backoff_seconds: int = 30,
) -> str:
    if not supports_persisted_queue():
        return "failed"
    err = str(error or "unknown error").strip()[:4000]
    with get_db() as db:
        row = db.execute(
            text(
                """
                SELECT attempts, max_attempts
                FROM kb_tasks
                WHERE tenant_id=:t AND task_id=:id
                """
            ),
            {"t": tenant_id, "id": task_id},
        ).fetchone()
        attempts = int(row[0] if row else 1)
        max_attempts = int(row[1] if row else 1)
        if attempts < max_attempts:
            db.execute(
                text(
                    """
                    UPDATE kb_tasks
                    SET status='queued',
                        stage='queued',
                        detail=:dt,
                        last_error=:err,
                        lease_until=NULL,
                        worker_id=NULL,
                        next_run_at=(CURRENT_TIMESTAMP + (:bo * INTERVAL '1 second')),
                        updated_at=CURRENT_TIMESTAMP
                    WHERE tenant_id=:t AND task_id=:id AND worker_id=:wid
                    """
                ),
                {"t": tenant_id, "id": task_id, "wid": worker_id, "bo": max(1, int(backoff_seconds)), "dt": err, "err": err},
            )
            return "retry"
        db.execute(
            text(
                """
                UPDATE kb_tasks
                SET status='failed',
                    stage='failed',
                    progress=100,
                    detail=:dt,
                    last_error=:err,
                    finished_at=CURRENT_TIMESTAMP,
                    lease_until=NULL,
                    worker_id=NULL,
                    updated_at=CURRENT_TIMESTAMP
                WHERE tenant_id=:t AND task_id=:id AND worker_id=:wid
                """
            ),
            {"t": tenant_id, "id": task_id, "wid": worker_id, "dt": err, "err": err},
        )
    return "failed"


def requeue_stale_tasks(*, running_timeout_seconds: int, queued_timeout_seconds: int) -> dict[str, int]:
    if not supports_persisted_queue():
        return {"requeued_running": 0, "failed_running": 0, "failed_queued": 0}
    run_timeout = max(60, int(running_timeout_seconds))
    queued_timeout = max(300, int(queued_timeout_seconds))
    out = {"requeued_running": 0, "failed_running": 0, "failed_queued": 0}
    with get_db() as db:
        rows = db.execute(
            text(
                """
                SELECT tenant_id, task_id, attempts, max_attempts
                FROM kb_tasks
                WHERE status='running'
                  AND (
                    lease_until IS NULL OR
                    lease_until < CURRENT_TIMESTAMP OR
                    heartbeat_at < (CURRENT_TIMESTAMP - (:rt * INTERVAL '1 second'))
                  )
                LIMIT 200
                """
            ),
            {"rt": run_timeout},
        ).fetchall()
        for r in rows:
            tenant_id = str(r[0] or "")
            task_id = str(r[1] or "")
            attempts = int(r[2] or 0)
            max_attempts = int(r[3] or 1)
            if attempts < max_attempts:
                db.execute(
                    text(
                        """
                        UPDATE kb_tasks
                        SET status='queued',
                            stage='queued',
                            detail='worker lease expired, requeued',
                            worker_id=NULL,
                            lease_until=NULL,
                            next_run_at=CURRENT_TIMESTAMP,
                            updated_at=CURRENT_TIMESTAMP
                        WHERE tenant_id=:t AND task_id=:id
                        """
                    ),
                    {"t": tenant_id, "id": task_id},
                )
                out["requeued_running"] += 1
            else:
                db.execute(
                    text(
                        """
                        UPDATE kb_tasks
                        SET status='failed',
                            stage='failed',
                            progress=100,
                            detail='worker lease expired and attempts exhausted',
                            last_error='worker lease expired',
                            worker_id=NULL,
                            lease_until=NULL,
                            finished_at=CURRENT_TIMESTAMP,
                            updated_at=CURRENT_TIMESTAMP
                        WHERE tenant_id=:t AND task_id=:id
                        """
                    ),
                    {"t": tenant_id, "id": task_id},
                )
                out["failed_running"] += 1
        row2 = db.execute(
            text(
                """
                UPDATE kb_tasks
                SET status='failed',
                    stage='failed',
                    progress=100,
                    detail='queued too long',
                    last_error='queued timeout',
                    finished_at=CURRENT_TIMESTAMP,
                    updated_at=CURRENT_TIMESTAMP
                WHERE status='queued'
                  AND created_at < (CURRENT_TIMESTAMP - (:qt * INTERVAL '1 second'))
                RETURNING task_id
                """
            ),
            {"qt": queued_timeout},
        ).fetchall()
        out["failed_queued"] = len(row2)
    return out


def update_task(
    tenant_id: str,
    task_id: str,
    *,
    status: str | None = None,
    stage: str | None = None,
    progress: int | None = None,
    detail: str | None = None,
    result_package_id: str | None = None,
    payload: dict[str, Any] | None = None,
    priority: int | None = None,
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
    if payload is not None:
        if supports_persisted_queue():
            sets.append("payload_json=:pj")
            params["pj"] = json.dumps(payload, ensure_ascii=False)
    if priority is not None and supports_persisted_queue():
        sets.append("queue_priority=:pri")
        params["pri"] = priority
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

