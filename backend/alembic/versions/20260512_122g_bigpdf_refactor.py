"""v1.2.2.g bigpdf refactor: enhance kb_tasks with file metadata and queue management

Revision ID: 20260512_122g_bigpdf_refactor
Revises: 20260415_122_schema
Create Date: 2026-05-12
"""

from __future__ import annotations

from alembic import op


revision = "20260512_122g_bigpdf_refactor"
down_revision = "20260415_123_folder_resources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # === 持久化队列必需列（enqueue_bigpdf_task 走 kb_tasks 表的先决条件）===
    op.execute("ALTER TABLE kb_tasks ADD COLUMN IF NOT EXISTS queue_priority INTEGER DEFAULT 1")
    op.execute("ALTER TABLE kb_tasks ADD COLUMN IF NOT EXISTS payload_json TEXT")
    op.execute("ALTER TABLE kb_tasks ADD COLUMN IF NOT EXISTS lease_until TIMESTAMP NULL")
    op.execute("ALTER TABLE kb_tasks ADD COLUMN IF NOT EXISTS attempts INTEGER DEFAULT 0")
    op.execute("ALTER TABLE kb_tasks ADD COLUMN IF NOT EXISTS max_attempts INTEGER DEFAULT 3")
    op.execute("ALTER TABLE kb_tasks ADD COLUMN IF NOT EXISTS next_run_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")

    # kb_tasks 新增字段（bigpdf 增强）
    op.execute("ALTER TABLE kb_tasks ADD COLUMN IF NOT EXISTS file_name VARCHAR(255)")
    op.execute("ALTER TABLE kb_tasks ADD COLUMN IF NOT EXISTS file_size BIGINT")
    op.execute("ALTER TABLE kb_tasks ADD COLUMN IF NOT EXISTS page_count INTEGER")
    op.execute("ALTER TABLE kb_tasks ADD COLUMN IF NOT EXISTS docling_task_id VARCHAR(255)")
    op.execute("ALTER TABLE kb_tasks ADD COLUMN IF NOT EXISTS task_position INTEGER DEFAULT 0")
    op.execute("ALTER TABLE kb_tasks ADD COLUMN IF NOT EXISTS estimated_duration INTEGER")
    op.execute("ALTER TABLE kb_tasks ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP NULL")
    op.execute("ALTER TABLE kb_tasks ADD COLUMN IF NOT EXISTS cancelled_by VARCHAR(100)")
    op.execute("ALTER TABLE kb_tasks ADD COLUMN IF NOT EXISTS cancel_type VARCHAR(20)")

    # 新增索引
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_kb_tasks_status_kind
        ON kb_tasks(tenant_id, status, kind)
        WHERE status IN ('queued', 'running')
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_kb_tasks_owner
        ON kb_tasks(tenant_id, owner_username, created_at DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_kb_tasks_owner")
    op.execute("DROP INDEX IF EXISTS idx_kb_tasks_status_kind")
    op.execute("ALTER TABLE kb_tasks DROP COLUMN IF EXISTS cancel_type")
    op.execute("ALTER TABLE kb_tasks DROP COLUMN IF EXISTS cancelled_by")
    op.execute("ALTER TABLE kb_tasks DROP COLUMN IF EXISTS completed_at")
    op.execute("ALTER TABLE kb_tasks DROP COLUMN IF EXISTS estimated_duration")
    op.execute("ALTER TABLE kb_tasks DROP COLUMN IF EXISTS task_position")
    op.execute("ALTER TABLE kb_tasks DROP COLUMN IF EXISTS docling_task_id")
    op.execute("ALTER TABLE kb_tasks DROP COLUMN IF EXISTS page_count")
    op.execute("ALTER TABLE kb_tasks DROP COLUMN IF EXISTS file_size")
    op.execute("ALTER TABLE kb_tasks DROP COLUMN IF EXISTS file_name")
    op.execute("ALTER TABLE kb_tasks DROP COLUMN IF EXISTS next_run_at")
    op.execute("ALTER TABLE kb_tasks DROP COLUMN IF EXISTS max_attempts")
    op.execute("ALTER TABLE kb_tasks DROP COLUMN IF EXISTS attempts")
    op.execute("ALTER TABLE kb_tasks DROP COLUMN IF EXISTS lease_until")
    op.execute("ALTER TABLE kb_tasks DROP COLUMN IF EXISTS payload_json")
    op.execute("ALTER TABLE kb_tasks DROP COLUMN IF EXISTS queue_priority")
