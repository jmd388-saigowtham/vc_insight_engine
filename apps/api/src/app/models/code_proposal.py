from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import TIMESTAMP, Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.session import Session


class CodeProposal(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "code_proposals"
    __table_args__ = (
        Index("ix_code_proposals_session_id", "session_id"),
        Index("ix_code_proposals_created_at", "created_at"),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    step: Mapped[str] = mapped_column(String(50), nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(20), server_default="python", nullable=False)
    status: Mapped[str] = mapped_column(String(20), server_default="pending", nullable=False)
    result_stdout: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_stderr: Mapped[str | None] = mapped_column(Text, nullable=True)
    execution_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    session: Mapped[Session] = relationship(back_populates="code_proposals")
