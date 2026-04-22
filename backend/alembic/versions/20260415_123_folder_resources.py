"""folder-first schema: folder fields + folder resources

Revision ID: 20260415_123_folder_resources
Revises: 20260415_122_schema
Create Date: 2026-04-15
"""

from __future__ import annotations

from alembic import op


revision = "20260415_123_folder_resources"
down_revision = "20260415_122_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Extend kb_folders to support folder-first workflow
    op.execute("ALTER TABLE kb_folders ADD COLUMN IF NOT EXISTS kind TEXT")
    op.execute("ALTER TABLE kb_folders ADD COLUMN IF NOT EXISTS scope_json TEXT NOT NULL DEFAULT '{}'")
    op.execute("ALTER TABLE kb_folders ADD COLUMN IF NOT EXISTS owner_username TEXT")
    op.execute("ALTER TABLE kb_folders ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP")

    # Bind resources (doc/table) into folders
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS kb_folder_resources (
            tenant_id TEXT NOT NULL,
            folder_id TEXT NOT NULL,
            resource_type TEXT NOT NULL, -- 'doc' | 'table'
            resource_id TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (tenant_id, folder_id, resource_type, resource_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_kb_folder_resources_tenant_resource
        ON kb_folder_resources (tenant_id, resource_type, resource_id)
        """
    )


def downgrade() -> None:
    # Conservative: keep columns; only drop the new binding table.
    op.execute("DROP TABLE IF EXISTS kb_folder_resources")

