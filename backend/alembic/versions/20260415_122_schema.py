"""v1.2.2 schema: folders + contract ledger

Only schema changes (DDL). No data migration.

Revision ID: 20260415_122_schema
Revises: 
Create Date: 2026-04-15
"""

from __future__ import annotations

from alembic import op


revision = "20260415_122_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # kb_folders / kb_folder_collections
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS kb_folders (
            folder_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            name TEXT NOT NULL,
            created_by TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS kb_folder_collections (
            tenant_id TEXT NOT NULL,
            folder_id TEXT NOT NULL,
            collection_id TEXT NOT NULL,
            PRIMARY KEY (tenant_id, folder_id, collection_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_kb_folder_collections_tenant_folder
        ON kb_folder_collections (tenant_id, folder_id)
        """
    )

    # contract_ledger
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS contract_ledger (
            contract_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            owner_username TEXT NOT NULL,
            doc_id TEXT NOT NULL,
            original_filename TEXT,
            storage_path TEXT,
            extracted_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'active',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_contract_ledger_tenant_created
        ON contract_ledger (tenant_id, created_at DESC)
        """
    )


def downgrade() -> None:
    # 保守：降级仅删除新增对象；若生产已依赖请勿执行 downgrade。
    op.execute("DROP TABLE IF EXISTS contract_ledger")
    op.execute("DROP TABLE IF EXISTS kb_folder_collections")
    op.execute("DROP TABLE IF EXISTS kb_folders")

