"""Add dataset registry table

Revision ID: 003
Revises: 002
Create Date: 2026-03-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "datasets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_type", sa.VARCHAR(50), nullable=False),
        sa.Column("name", sa.VARCHAR(255), nullable=False),
        sa.Column("file_path", sa.TEXT, nullable=False),
        sa.Column("row_count", sa.INTEGER, nullable=True),
        sa.Column("column_count", sa.INTEGER, nullable=True),
        sa.Column(
            "parent_dataset_id",
            UUID(as_uuid=True),
            sa.ForeignKey("datasets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_datasets_session_id", "datasets", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_datasets_session_id")
    op.drop_table("datasets")
