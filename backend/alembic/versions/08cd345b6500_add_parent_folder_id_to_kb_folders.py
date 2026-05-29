"""add parent_folder_id to kb_folders

Revision ID: 08cd345b6500
Revises: 20260512_122g_bigpdf_refactor
Create Date: 2026-05-19 18:02:04.731221

"""

from __future__ import annotations

from alembic import op

import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '08cd345b6500'
down_revision = '20260512_122g_bigpdf_refactor'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE kb_folders
        ADD COLUMN IF NOT EXISTS parent_folder_id TEXT
        REFERENCES kb_folders(folder_id)
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE kb_folders
        DROP COLUMN IF EXISTS parent_folder_id
        """
    )

