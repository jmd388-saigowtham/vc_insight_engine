"""Business-logic proposal model for plan-level approval workflows.

Unlike CodeProposal (which handles code approval), Proposal handles
higher-level business decisions: merge strategy, target selection,
feature selection, preprocessing plan, model selection, etc.

Each proposal supports a revision chain via parent_id for tracking
the full decision history.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import TIMESTAMP, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.session import Session


class Proposal(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "proposals"
    __table_args__ = (
        Index("ix_proposals_session_id", "session_id"),
        Index("ix_proposals_created_at", "created_at"),
        Index("ix_proposals_session_step", "session_id", "step"),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    step: Mapped[str] = mapped_column(String(50), nullable=False)
    proposal_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), server_default="pending", nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, server_default="1", nullable=False)
    plan: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    alternatives: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    user_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("proposals.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    session: Mapped[Session] = relationship(back_populates="proposals")
    parent: Mapped[Proposal | None] = relationship(
        remote_side="Proposal.id", foreign_keys=[parent_id]
    )
