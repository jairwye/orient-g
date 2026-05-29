"""
本地开发：为 PostgreSQL 启用 pgvector 并创建 kb_doc_chunk_embeddings 表。
用法（项目根目录）：
  .\\.venv\\Scripts\\python.exe scripts\\init_kb_vector_local.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, text

from backend.config import settings


def main() -> int:
    dim = int(getattr(settings, "kb_embedding_dim", 1024) or 1024)
    url = settings.database_url
    print(f"DATABASE_URL host: {url.split('@')[-1] if '@' in url else url}")
    print(f"KB_EMBEDDING_DIM={dim}")

    engine = create_engine(url)
    with engine.connect() as conn:
        try:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()
            print("[OK] CREATE EXTENSION vector")
        except Exception as e:
            print("[FAIL] pgvector 扩展不可用:", e)
            print(
                "  Windows 本机 Postgres 需单独安装 pgvector，或改用 Docker 跑 pgvector/pgvector:pg16"
            )
            return 1

        conn.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS kb_doc_chunk_embeddings (
                    tenant_id TEXT NOT NULL,
                    doc_id TEXT NOT NULL,
                    chunk_id TEXT NOT NULL,
                    chunk_seq_no INTEGER NOT NULL,
                    embedding vector({dim}) NOT NULL,
                    embed_model TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (tenant_id, doc_id, chunk_id, embed_model)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS idx_kb_doc_chunk_embeddings_tenant_model
                ON kb_doc_chunk_embeddings (tenant_id, embed_model)
                """
            )
        )
        conn.commit()
        print("[OK] kb_doc_chunk_embeddings 表已就绪")

        row = conn.execute(
            text("SELECT COUNT(*) FROM kb_doc_chunk_embeddings")
        ).fetchone()
        print(f"[INFO] 当前向量行数: {int(row[0] or 0)}")

    print("\n下一步:")
    print("  1) .env 确认 KB_VECTOR_ENABLED=true、OLLAMA_URL、OLLAMA_EMBED_MODEL=bge-m3")
    print("  2) 重启本机 backend")
    print("  3) 登录后 POST /api/knowledge/admin/reindex（Bearer 为 JWT，不是用户 ID）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
