"""本库知识库向量索引覆盖统计。用法: .\\.venv\\Scripts\\python.exe scripts\\kb_embedding_stats.py"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, text

from backend.config import settings

TENANT = "tenant1"
MODEL = (settings.ollama_embed_model or "bge-m3").strip()


def main() -> None:
    e = create_engine(settings.database_url)
    with e.connect() as c:
        total = c.execute(
            text("SELECT COUNT(*) FROM kb_user_documents WHERE tenant_id=:t"),
            {"t": TENANT},
        ).scalar()
        done = c.execute(
            text(
                """
                SELECT COUNT(DISTINCT doc_id)
                FROM kb_doc_chunk_embeddings
                WHERE tenant_id=:t AND embed_model=:m
                """
            ),
            {"t": TENANT, "m": MODEL},
        ).scalar()
        chunks = c.execute(
            text("SELECT COUNT(*) FROM kb_doc_chunk_embeddings WHERE embed_model=:m"),
            {"m": MODEL},
        ).scalar()
        with_chunks = c.execute(
            text(
                """
                SELECT COUNT(DISTINCT d.doc_id)
                FROM kb_user_documents d
                WHERE d.tenant_id=:t
                  AND EXISTS (
                    SELECT 1 FROM kb_user_document_chunks ch WHERE ch.doc_id = d.doc_id
                  )
                """
            ),
            {"t": TENANT},
        ).scalar()

    total_i = int(total or 0)
    done_i = int(done or 0)
    print(f"tenant_id: {TENANT}")
    print(f"embed_model: {MODEL}")
    print(f"documents total: {total_i}")
    print(f"documents with embeddings: {done_i}")
    print(f"documents still missing embeddings: {total_i - done_i}")
    print(f"documents with text chunks: {int(with_chunks or 0)}")
    print(f"embedding rows (chunks): {int(chunks or 0)}")


if __name__ == "__main__":
    main()
