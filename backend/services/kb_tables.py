"""
2.b/2.c/2.d 交叉缺口落地：表实例（TableInstance）持久化与最小 table evidence 检索。

- 表实例：kb_table_instances
- 行证据：kb_table_rows（row_key 为稳定引用键，采用 surrogate key 方案）
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import text

from backend.database import get_db
from backend.services.kb_acl_store import set_resource_assignments, set_resource_owner
from backend.services.kb_documents import dynamic_private_collection_id


def _safe_str(v: Any) -> str:
    if v is None:
        return ""
    return str(v)


def _normalize_name(name: str) -> str:
    n = (name or "").strip()
    return n[:200] or "未命名表"


def _columns_from_headers(headers: list[Any]) -> list[dict[str, Any]]:
    cols: list[dict[str, Any]] = []
    for h in headers or []:
        s = _safe_str(h).strip()
        if not s:
            continue
        cols.append({"column_id": s, "name": s})
    # 去重保序
    seen = set()
    out = []
    for c in cols:
        cid = c["column_id"]
        if cid in seen:
            continue
        seen.add(cid)
        out.append(c)
    return out[:200]


def _row_search_text(values: dict[str, Any]) -> str:
    parts = []
    for k, v in (values or {}).items():
        if v is None or v == "":
            continue
        parts.append(f"{k}:{_safe_str(v)}")
    s = " ".join(parts)
    return s[:5000]


def create_table_instance_from_rows(
    tenant_id: str,
    owner_username: str,
    *,
    name: str,
    source_type: str,
    source_ref: str | None,
    headers: list[Any],
    rows: list[list[Any]],
    assign_to_private: bool = True,
) -> dict[str, Any]:
    """
    将通用表（headers + rows）存为 TableInstance，并写入行证据。
    返回：{table_id, row_count, private_collection_id?}
    """
    tid = (tenant_id or "").strip() or "tenant1"
    ou = (owner_username or "").strip()
    if not ou:
        raise ValueError("owner_username required")
    table_id = f"ti_{uuid.uuid4().hex}"
    cols = _columns_from_headers(headers or [])
    col_ids = [c["column_id"] for c in cols]
    row_count = 0

    with get_db() as db:
        db.execute(
            text(
                """
                INSERT INTO kb_table_instances
                    (table_id, tenant_id, owner_username, name, source_type, source_ref, columns_json, row_count, status)
                VALUES
                    (:id, :t, :u, :n, :st, :sr, :cj, 0, 'active')
                """
            ),
            {
                "id": table_id,
                "t": tid,
                "u": ou,
                "n": _normalize_name(name),
                "st": (source_type or "excel_session").strip()[:40],
                "sr": (source_ref or "").strip()[:200] or None,
                "cj": json.dumps(cols, ensure_ascii=False),
            },
        )

        for r in (rows or [])[:5000]:
            values: dict[str, Any] = {}
            for i, cid in enumerate(col_ids):
                if i < len(r):
                    values[cid] = r[i]
            row_key = f"rk_{uuid.uuid4().hex}"
            db.execute(
                text(
                    """
                    INSERT INTO kb_table_rows (tenant_id, table_id, row_key, row_json, search_text)
                    VALUES (:t, :tid, :rk, :rj, :st)
                    """
                ),
                {
                    "t": tid,
                    "tid": table_id,
                    "rk": row_key,
                    "rj": json.dumps(values, ensure_ascii=False),
                    "st": _row_search_text(values),
                },
            )
            row_count += 1

        db.execute(
            text(
                """
                UPDATE kb_table_instances
                SET row_count=:rc, updated_at=CURRENT_TIMESTAMP
                WHERE tenant_id=:t AND table_id=:id
                """
            ),
            {"t": tid, "id": table_id, "rc": int(row_count)},
        )

    # ACL：默认存入用户动态私有 collection
    private_collection_id = None
    if assign_to_private:
        private_collection_id = dynamic_private_collection_id(ou)
        set_resource_assignments(tid, resource_type="table", resource_id=table_id, collection_ids=[private_collection_id])
        set_resource_owner(tid, resource_type="table", resource_id=table_id, owner_username=ou)

    return {
        "table_id": table_id,
        "row_count": row_count,
        "private_collection_id": private_collection_id,
    }


def list_table_instances(tenant_id: str, table_ids: list[str]) -> list[dict[str, Any]]:
    tid = (tenant_id or "").strip() or "tenant1"
    ids = [str(x).strip() for x in (table_ids or []) if str(x).strip()]
    if not ids:
        return []
    with get_db() as db:
        rows = db.execute(
            text(
                """
                SELECT table_id, name, owner_username, source_type, source_ref, columns_json, row_count, status, created_at
                FROM kb_table_instances
                WHERE tenant_id=:t AND table_id = ANY(:ids)
                ORDER BY created_at DESC
                """
            ),
            {"t": tid, "ids": ids},
        ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        try:
            cols = json.loads(r[5] or "[]")
        except Exception:
            cols = []
        out.append(
            {
                "table_id": str(r[0]),
                "name": str(r[1] or ""),
                "owner_username": str(r[2] or ""),
                "source_type": str(r[3] or ""),
                "source_ref": str(r[4] or "") if r[4] else None,
                "columns": cols if isinstance(cols, list) else [],
                "row_count": int(r[6] or 0),
                "status": str(r[7] or ""),
                "created_at": r[8].isoformat() if r[8] else None,
            }
        )
    return out


def retrieve_table_evidence(
    tenant_id: str,
    *,
    selected_table_ids: set[str],
    query: str,
) -> dict[str, Any]:
    """
    最小 table content QA：
    - 在 selected_table_ids 内找一条 search_text 命中 query 的行
    - 返回 {evidence, answer_value}
    """
    tid = (tenant_id or "").strip() or "tenant1"
    q = (query or "").strip()
    if not q or not selected_table_ids:
        return {"evidence": None, "answer_value": None}
    ids = sorted([str(x) for x in selected_table_ids if str(x).strip()])
    if not ids:
        return {"evidence": None, "answer_value": None}
    pat = f"%{q[:200]}%"
    with get_db() as db:
        row = db.execute(
            text(
                """
                SELECT r.table_id, r.row_key, r.row_json
                FROM kb_table_rows r
                WHERE r.tenant_id=:t
                  AND r.table_id = ANY(:ids)
                  AND r.search_text ILIKE :pat
                ORDER BY r.id DESC
                LIMIT 1
                """
            ),
            {"t": tid, "ids": ids, "pat": pat},
        ).fetchone()
    if not row:
        return {"evidence": None, "answer_value": None}
    table_id = str(row[0] or "")
    row_key = str(row[1] or "")
    raw = str(row[2] or "{}")
    try:
        values = json.loads(raw) if raw else {}
    except Exception:
        values = {}
    if not isinstance(values, dict):
        values = {}

    # pick a numeric-ish value first; otherwise any first value
    chosen_col = None
    chosen_val = None
    for k, v in values.items():
        if isinstance(v, (int, float)):
            chosen_col, chosen_val = str(k), v
            break
    if chosen_col is None:
        for k, v in values.items():
            chosen_col, chosen_val = str(k), v
            break

    evidence = {
        "evidence_type": "table_row",
        "table_id": table_id,
        "row_key": row_key,
        "column_id": chosen_col,
    }
    return {"evidence": evidence, "answer_value": chosen_val}

