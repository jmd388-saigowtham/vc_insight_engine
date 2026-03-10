"""User feedback model for free-form input during agent workflow.

Users can submit feedback at any point during the pipeline. The agent
reads pending feedback to inform its decisions.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.session import Session


class UserFeedback(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "user_feedback"
    __table_args__ = (
        Index("ix_user_feedback_session_id", "session_id"),
        Index("ix_user_feedback_created_at", "created_at"),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    step: Mapped[str | None] = mapped_column(String(50), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), server_default="pending", nullable=False
    )

    session: Mapped[Session] = relationship(back_populates="user_feedback")
