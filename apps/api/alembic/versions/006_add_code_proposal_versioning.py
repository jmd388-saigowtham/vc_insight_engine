"""Add version and parent_id to code_proposals for revision chain tracking.

Revision ID: 006
Revises: 005
Create Date: 2025-06-01 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "code_proposals",
        sa.Column("version", sa.Integer, server_default="1", nullable=False),
    )
    op.add_column(
        "code_proposals",
        sa.Column(
            "parent_id",
            UUID(as_uuid=True),
            sa.ForeignKey("code_proposals.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("code_proposals", "parent_id")
    op.drop_column("code_proposals", "version")
