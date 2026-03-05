from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.session import Session


class TraceEvent(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "trace_events"
    __table_args__ = (
        Index("ix_trace_events_session_id", "session_id"),
        Index("ix_trace_events_created_at", "created_at"),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    step: Mapped[str | None] = mapped_column(String(50), nullable=True)
    payload: Mapped[Any | None] = mapped_column(JSONB, nullable=True)

    session: Mapped[Session] = relationship(back_populates="trace_events")
