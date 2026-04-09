from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import text

from backend.database import get_db


def _sha256_text(s: str) -> str:
    return hashlib.sha256((s or "").encode("utf-8", errors="ignore")).hexdigest()


def write_event(
    tenant_id: str,
    *,
    username: str | None,
    event_type: str,
    query: str | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    """
    写入审计事件（追加写）。

    约束：
    - 不要把敏感明文塞进 meta（例如 chunk_text、原文段落等）
    - query 只存 hash 与长度，不存明文
    """
    tid = (tenant_id or "").strip() or "tenant1"
    un = (username or "").strip() or None
    et = (event_type or "").strip() or "unknown"
    q = query or ""
    qh = _sha256_text(q) if q else None
    qlen = len(q) if q else None
    mj = json.dumps(meta or {}, ensure_ascii=False) if meta is not None else None
    with get_db() as db:
        db.execute(
            text(
                """
                INSERT INTO kb_audit_events
                    (tenant_id, username, event_type, query_sha256, query_len, meta_json)
                VALUES
                    (:t, :u, :e, :qh, :ql, :mj)
                """
            ),
            {"t": tid, "u": un, "e": et, "qh": qh, "ql": qlen, "mj": mj},
        )

