from __future__ import annotations

from typing import Any

from sqlalchemy import text

from backend.config import settings
from backend.database import get_db
from backend.services.ollama_embeddings import embed_texts


def _pgvector_literal(values: list[float]) -> str:
    """PostgreSQL pgvector 字面量（用于 CAST(... AS vector)）。"""
    return "[" + ",".join(f"{float(v):.8g}" for v in values) + "]"


def vector_enabled() -> bool:
    """
    是否启用向量检索。

    原则：默认关闭（小文档海走 keyword-only 更稳定、可控）。
    """
    if not settings.kb_vector_enabled:
        return False
    if not settings.ollama_configured:
        return False
    # 数据库侧能力探测：表存在即可（vector 扩展未启用会在建表/查询时报错，此处兜底 False）
    try:
        with get_db() as db:
            db.execute(text("SELECT 1 FROM kb_doc_chunk_embeddings LIMIT 1"))
        return True
    except Exception:
        return False


def upsert_doc_chunk_embeddings(
    tenant_id: str,
    *,
    doc_id: str,
    chunks: list[dict[str, Any]],
    embed_model: str | None = None,
) -> int:
    """
    chunks item: {chunk_id, chunk_seq_no, chunk_text}
    返回写入条数。
    """
    if not vector_enabled():
        return 0

    tid = (tenant_id or "").strip() or "tenant1"
    did = (doc_id or "").strip()
    if not did:
        return 0

    m = (embed_model or settings.ollama_embed_model or "").strip()
    if not m:
        return 0

    items = []
    texts: list[str] = []
    for c in chunks or []:
        cid = str(c.get("chunk_id") or "").strip()
        seq = int(c.get("chunk_seq_no") or 0)
        txt = str(c.get("chunk_text") or "").strip()
        if not cid or not txt:
            continue
        items.append((cid, seq, txt))
        texts.append(txt[:4000])
    if not items:
        return 0

    embs = embed_texts(texts, model=m, timeout_s=120)
    if len(embs) != len(items):
        raise RuntimeError("embedding 数量与 chunks 数量不一致")
    exp_dim = int(getattr(settings, "kb_embedding_dim", 0) or 0)
    if exp_dim > 0:
        for e in embs:
            if len(e) != exp_dim:
                raise RuntimeError(f"embedding 维度不匹配：expect={exp_dim}, got={len(e)} (model={m})")

    wrote = 0
    with get_db() as db:
        for (cid, seq, _txt), emb in zip(items, embs, strict=False):
            db.execute(
                text(
                    """
                    INSERT INTO kb_doc_chunk_embeddings
                        (tenant_id, doc_id, chunk_id, chunk_seq_no, embedding, embed_model)
                    VALUES
                        (:t, :d, :cid, :seq, :emb, :m)
                    ON CONFLICT (tenant_id, doc_id, chunk_id, embed_model) DO UPDATE
                    SET chunk_seq_no = EXCLUDED.chunk_seq_no,
                        embedding = EXCLUDED.embedding
                    """
                ),
                {"t": tid, "d": did, "cid": cid, "seq": seq, "emb": emb, "m": m},
            )
            wrote += 1
    return wrote


def search_doc_chunks(
    tenant_id: str,
    *,
    query: str,
    candidate_doc_ids: list[str],
    k: int = 6,
    embed_model: str | None = None,
) -> list[dict[str, Any]]:
    """
    在候选 doc 范围内做向量相似度搜索，返回 doc_id/chunk_id/chunk_seq_no/score。

    score 越小越相似（cosine distance）。
    """
    if not vector_enabled():
        return []

    tid = (tenant_id or "").strip() or "tenant1"
    q = (query or "").strip()
    if not q:
        return []

    cand = [str(x).strip() for x in (candidate_doc_ids or []) if str(x).strip()]
    if not cand:
        return []

    m = (embed_model or settings.ollama_embed_model or "").strip()
    if not m:
        return []

    qv = embed_texts([q], model=m, timeout_s=60)[0]
    exp_dim = int(getattr(settings, "kb_embedding_dim", 0) or 0)
    if exp_dim > 0 and len(qv) != exp_dim:
        raise RuntimeError(f"query embedding 维度不匹配：expect={exp_dim}, got={len(qv)} (model={m})")
    lim = max(1, min(30, int(k)))
    qv_lit = _pgvector_literal(qv)
    with get_db() as db:
        rows = db.execute(
            text(
                """
                SELECT doc_id, chunk_id, chunk_seq_no, (embedding <=> CAST(:qv AS vector)) AS score
                FROM kb_doc_chunk_embeddings
                WHERE tenant_id = :t
                  AND embed_model = :m
                  AND doc_id = ANY(:doc_ids)
                ORDER BY embedding <=> CAST(:qv AS vector)
                LIMIT :lim
                """
            ),
            {"t": tid, "m": m, "doc_ids": cand, "qv": qv_lit, "lim": lim},
        ).fetchall()

    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "doc_id": str(r[0]),
                "chunk_id": str(r[1]),
                "chunk_seq_no": int(r[2] or 0),
                "score": float(r[3] or 0.0),
            }
        )
    return out

