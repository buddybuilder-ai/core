"""add_project_preview_image

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-18 00:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("preview_image", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("projects", "preview_image")
