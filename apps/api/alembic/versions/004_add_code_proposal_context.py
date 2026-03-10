"""Add context JSONB column to code_proposals table.

Revision ID: 004
Revises: 003
Create Date: 2026-03-08
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers
revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("code_proposals", sa.Column("context", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("code_proposals", "context")
