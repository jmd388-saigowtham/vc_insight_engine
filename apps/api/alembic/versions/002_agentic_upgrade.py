"""Agentic upgrade: add step_states, target_column, selected_features,
revision, step, description, node_name columns

Revision ID: 002
Revises: 001
Create Date: 2025-06-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # sessions: step_states, target_column, selected_features
    op.add_column("sessions", sa.Column("step_states", JSONB, nullable=True))
    op.add_column("sessions", sa.Column("target_column", sa.VARCHAR(255), nullable=True))
    op.add_column("sessions", sa.Column("selected_features", JSONB, nullable=True))

    # artifacts: revision, step
    op.add_column(
        "artifacts",
        sa.Column("revision", sa.INTEGER, server_default="1", nullable=False),
    )
    op.add_column("artifacts", sa.Column("step", sa.VARCHAR(50), nullable=True))

    # code_proposals: description, node_name
    op.add_column("code_proposals", sa.Column("description", sa.TEXT, nullable=True))
    op.add_column("code_proposals", sa.Column("node_name", sa.VARCHAR(50), nullable=True))


def downgrade() -> None:
    op.drop_column("code_proposals", "node_name")
    op.drop_column("code_proposals", "description")
    op.drop_column("artifacts", "step")
    op.drop_column("artifacts", "revision")
    op.drop_column("sessions", "selected_features")
    op.drop_column("sessions", "target_column")
    op.drop_column("sessions", "step_states")
