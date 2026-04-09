from __future__ import annotations

from typing import Any

from sqlalchemy import text

from backend.database import get_db
from backend.services.kb_vector_store import upsert_doc_chunk_embeddings, vector_enabled


def _load_uploaded_doc_chunks(tenant_id: str, doc_id: str) -> list[dict[str, Any]]:
    with get_db() as db:
        rows = db.execute(
            text(
                """
                SELECT chunk_id, chunk_seq_no, chunk_text
                FROM kb_user_document_chunks
                WHERE doc_id = :d
                ORDER BY chunk_seq_no
                """
            ),
            {"d": doc_id},
        ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append({"chunk_id": str(r[0]), "chunk_seq_no": int(r[1] or 0), "chunk_text": str(r[2] or "")})
    return out


def index_uploaded_document_task(tenant_id: str, doc_id: str) -> None:
    """
    后台任务：为上传文档生成 chunk embeddings 并写入 pgvector 表。
    """
    tid = (tenant_id or "").strip() or "tenant1"
    did = (doc_id or "").strip()
    if not did:
        return
    if not vector_enabled():
        return
    chunks = _load_uploaded_doc_chunks(tid, did)
    if not chunks:
        return
    upsert_doc_chunk_embeddings(tid, doc_id=did, chunks=chunks)

