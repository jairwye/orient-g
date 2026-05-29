"""kb_tasks worker lease columns (started_at, heartbeat_at, …)

Revision ID: 20260522_122h_kb_tasks_worker
Revises: 08cd345b6500
Create Date: 2026-05-22

生产 Docker（DB_MIGRATION_MODE=alembic）若只跑到 122g，会缺少 worker 租约列，
导致 claim_next_task / requeue_stale_tasks 报 column does not exist。
"""

from __future__ import annotations

from alembic import op


revision = "20260522_122h_kb_tasks_worker"
down_revision = "08cd345b6500"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE kb_tasks ADD COLUMN IF NOT EXISTS worker_id TEXT")
    op.execute("ALTER TABLE kb_tasks ADD COLUMN IF NOT EXISTS heartbeat_at TIMESTAMP NULL")
    op.execute("ALTER TABLE kb_tasks ADD COLUMN IF NOT EXISTS started_at TIMESTAMP NULL")
    op.execute("ALTER TABLE kb_tasks ADD COLUMN IF NOT EXISTS finished_at TIMESTAMP NULL")
    op.execute("ALTER TABLE kb_tasks ADD COLUMN IF NOT EXISTS last_error TEXT")
    op.execute("ALTER TABLE kb_tasks ADD COLUMN IF NOT EXISTS dedupe_key TEXT")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_kb_tasks_queue
        ON kb_tasks (status, queue_priority, next_run_at, created_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_kb_tasks_dedupe
        ON kb_tasks (tenant_id, dedupe_key)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_kb_tasks_dedupe")
    op.execute("DROP INDEX IF EXISTS ix_kb_tasks_queue")
    op.execute("ALTER TABLE kb_tasks DROP COLUMN IF EXISTS dedupe_key")
    op.execute("ALTER TABLE kb_tasks DROP COLUMN IF EXISTS last_error")
    op.execute("ALTER TABLE kb_tasks DROP COLUMN IF EXISTS finished_at")
    op.execute("ALTER TABLE kb_tasks DROP COLUMN IF EXISTS started_at")
    op.execute("ALTER TABLE kb_tasks DROP COLUMN IF EXISTS heartbeat_at")
    op.execute("ALTER TABLE kb_tasks DROP COLUMN IF EXISTS worker_id")
