"""Initial schema with all 7 tables

Revision ID: 001
Revises:
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, TIMESTAMPTZ

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_name", sa.VARCHAR(255), nullable=False),
        sa.Column("industry", sa.VARCHAR(100), nullable=True),
        sa.Column("business_context", sa.TEXT, nullable=True),
        sa.Column("current_step", sa.VARCHAR(50), server_default="onboarding", nullable=False),
        sa.Column("status", sa.VARCHAR(20), server_default="active", nullable=False),
        sa.Column(
            "created_at",
            TIMESTAMPTZ,
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            TIMESTAMPTZ,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_sessions_created_at", "sessions", ["created_at"])

    op.create_table(
        "uploaded_files",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("filename", sa.VARCHAR(255), nullable=False),
        sa.Column("storage_path", sa.TEXT, nullable=False),
        sa.Column("file_type", sa.VARCHAR(10), nullable=False),
        sa.Column("size_bytes", sa.BIGINT, nullable=False),
        sa.Column("row_count", sa.INTEGER, nullable=True),
        sa.Column("column_count", sa.INTEGER, nullable=True),
        sa.Column(
            "created_at",
            TIMESTAMPTZ,
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_uploaded_files_session_id", "uploaded_files", ["session_id"])
    op.create_index("ix_uploaded_files_created_at", "uploaded_files", ["created_at"])

    op.create_table(
        "column_profiles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "file_id",
            UUID(as_uuid=True),
            sa.ForeignKey("uploaded_files.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("column_name", sa.VARCHAR(255), nullable=False),
        sa.Column("dtype", sa.VARCHAR(50), nullable=False),
        sa.Column("null_count", sa.INTEGER, nullable=True),
        sa.Column("null_pct", sa.FLOAT, nullable=True),
        sa.Column("unique_count", sa.INTEGER, nullable=True),
        sa.Column("min_value", sa.TEXT, nullable=True),
        sa.Column("max_value", sa.TEXT, nullable=True),
        sa.Column("mean_value", sa.FLOAT, nullable=True),
        sa.Column("sample_values", JSONB, nullable=True),
        sa.Column("description", sa.TEXT, nullable=True),
    )
    op.create_index("ix_column_profiles_file_id", "column_profiles", ["file_id"])

    op.create_table(
        "trace_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.VARCHAR(30), nullable=False),
        sa.Column("step", sa.VARCHAR(50), nullable=True),
        sa.Column("payload", JSONB, nullable=True),
        sa.Column(
            "created_at",
            TIMESTAMPTZ,
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_trace_events_session_id", "trace_events", ["session_id"])
    op.create_index("ix_trace_events_created_at", "trace_events", ["created_at"])

    op.create_table(
        "code_proposals",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("step", sa.VARCHAR(50), nullable=False),
        sa.Column("code", sa.TEXT, nullable=False),
        sa.Column("language", sa.VARCHAR(20), server_default="python", nullable=False),
        sa.Column("status", sa.VARCHAR(20), server_default="pending", nullable=False),
        sa.Column("result_stdout", sa.TEXT, nullable=True),
        sa.Column("result_stderr", sa.TEXT, nullable=True),
        sa.Column("execution_time", sa.FLOAT, nullable=True),
        sa.Column(
            "created_at",
            TIMESTAMPTZ,
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("resolved_at", TIMESTAMPTZ, nullable=True),
    )
    op.create_index("ix_code_proposals_session_id", "code_proposals", ["session_id"])
    op.create_index("ix_code_proposals_created_at", "code_proposals", ["created_at"])

    op.create_table(
        "artifacts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("artifact_type", sa.VARCHAR(50), nullable=False),
        sa.Column("name", sa.VARCHAR(255), nullable=False),
        sa.Column("storage_path", sa.TEXT, nullable=False),
        sa.Column("metadata_", JSONB, nullable=True),
        sa.Column(
            "created_at",
            TIMESTAMPTZ,
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_artifacts_session_id", "artifacts", ["session_id"])
    op.create_index("ix_artifacts_created_at", "artifacts", ["created_at"])

    op.create_table(
        "session_context_docs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("content_md", sa.TEXT, nullable=True),
        sa.Column("version", sa.INTEGER, server_default="1", nullable=False),
        sa.Column(
            "updated_at",
            TIMESTAMPTZ,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_session_context_docs_session_id", "session_context_docs", ["session_id"], unique=True
    )


def downgrade() -> None:
    op.drop_table("session_context_docs")
    op.drop_table("artifacts")
    op.drop_table("code_proposals")
    op.drop_table("trace_events")
    op.drop_table("column_profiles")
    op.drop_table("uploaded_files")
    op.drop_table("sessions")
