from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import text

from backend.database import get_db


def create_contract(
    tenant_id: str,
    owner_username: str,
    *,
    doc_id: str,
    original_filename: str | None,
    storage_path: str | None,
    extracted: dict[str, Any] | None = None,
) -> dict[str, Any]:
    tid = (tenant_id or "").strip() or "tenant1"
    ou = (owner_username or "").strip()
    did = (doc_id or "").strip()
    if not ou or not did:
        raise ValueError("owner_username/doc_id required")
    contract_id = f"ct_{uuid.uuid4().hex}"
    ex = extracted if isinstance(extracted, dict) else {}
    with get_db() as db:
        db.execute(
            text(
                """
                INSERT INTO contract_ledger
                    (contract_id, tenant_id, owner_username, doc_id, original_filename, storage_path, extracted_json, status, updated_at)
                VALUES
                    (:cid, :t, :u, :d, :ofn, :sp, :ej, 'active', CURRENT_TIMESTAMP)
                """
            ),
            {
                "cid": contract_id,
                "t": tid,
                "u": ou,
                "d": did,
                "ofn": (original_filename or "").strip()[:400] or None,
                "sp": (storage_path or "").strip()[:800] or None,
                "ej": json.dumps(ex, ensure_ascii=False),
            },
        )
    return get_contract(tid, contract_id) or {"contract_id": contract_id, "doc_id": did}


def list_my_contracts(tenant_id: str, owner_username: str, *, limit: int = 50) -> list[dict[str, Any]]:
    tid = (tenant_id or "").strip() or "tenant1"
    ou = (owner_username or "").strip()
    if not ou:
        return []
    lim = max(1, min(200, int(limit or 50)))
    with get_db() as db:
        rows = db.execute(
            text(
                """
                SELECT contract_id, doc_id, original_filename, status, created_at
                FROM contract_ledger
                WHERE tenant_id=:t AND owner_username=:u
                ORDER BY created_at DESC
                LIMIT :lim
                """
            ),
            {"t": tid, "u": ou, "lim": lim},
        ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "contract_id": str(r[0]),
                "doc_id": str(r[1]),
                "original_filename": str(r[2] or ""),
                "status": str(r[3] or ""),
                "created_at": r[4].isoformat() if r[4] else None,
            }
        )
    return out


def get_contract(tenant_id: str, contract_id: str) -> dict[str, Any] | None:
    tid = (tenant_id or "").strip() or "tenant1"
    cid = (contract_id or "").strip()
    if not cid:
        return None
    with get_db() as db:
        row = db.execute(
            text(
                """
                SELECT contract_id, tenant_id, owner_username, doc_id, original_filename, storage_path, extracted_json, status, created_at, updated_at
                FROM contract_ledger
                WHERE tenant_id=:t AND contract_id=:cid
                """
            ),
            {"t": tid, "cid": cid},
        ).fetchone()
    if not row:
        return None
    raw = str(row[6] or "{}")
    try:
        ex = json.loads(raw) if raw else {}
    except Exception:
        ex = {}
    if not isinstance(ex, dict):
        ex = {}
    return {
        "contract_id": str(row[0]),
        "tenant_id": str(row[1]),
        "owner_username": str(row[2]),
        "doc_id": str(row[3]),
        "original_filename": str(row[4] or ""),
        "storage_path": str(row[5] or ""),
        "extracted": ex,
        "status": str(row[7] or ""),
        "created_at": row[8].isoformat() if row[8] else None,
        "updated_at": row[9].isoformat() if row[9] else None,
    }

