"""Add proposals and user_feedback tables.

Revision ID: 005
Revises: 004
Create Date: 2025-06-01 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create proposals table
    op.create_table(
        "proposals",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("step", sa.String(50), nullable=False),
        sa.Column("proposal_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("version", sa.Integer, server_default="1", nullable=False),
        sa.Column("plan", JSONB, nullable=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("ai_reasoning", sa.Text, nullable=True),
        sa.Column("alternatives", JSONB, nullable=True),
        sa.Column("user_feedback", sa.Text, nullable=True),
        sa.Column(
            "parent_id",
            UUID(as_uuid=True),
            sa.ForeignKey("proposals.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "resolved_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_proposals_session_id", "proposals", ["session_id"])
    op.create_index("ix_proposals_created_at", "proposals", ["created_at"])
    op.create_index(
        "ix_proposals_session_step", "proposals", ["session_id", "step"]
    )

    # Create user_feedback table
    op.create_table(
        "user_feedback",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("step", sa.String(50), nullable=True),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_user_feedback_session_id", "user_feedback", ["session_id"])
    op.create_index("ix_user_feedback_created_at", "user_feedback", ["created_at"])


def downgrade() -> None:
    op.drop_table("user_feedback")
    op.drop_table("proposals")
