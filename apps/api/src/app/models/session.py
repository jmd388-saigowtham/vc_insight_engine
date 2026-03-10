from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, FullTimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.artifact import Artifact
    from app.models.code_proposal import CodeProposal
    from app.models.dataset import Dataset
    from app.models.proposal import Proposal
    from app.models.session_context import SessionContextDoc
    from app.models.trace_event import TraceEvent
    from app.models.uploaded_file import UploadedFile
    from app.models.user_feedback import UserFeedback


class Session(UUIDMixin, FullTimestampMixin, Base):
    __tablename__ = "sessions"
    __table_args__ = (Index("ix_sessions_created_at", "created_at"),)

    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True)
    business_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_step: Mapped[str] = mapped_column(
        String(50), server_default="onboarding", nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), server_default="active", nullable=False)
    step_states: Mapped[Any | None] = mapped_column("step_states", JSONB, nullable=True)
    target_column: Mapped[str | None] = mapped_column(String(255), nullable=True)
    selected_features: Mapped[Any | None] = mapped_column("selected_features", JSONB, nullable=True)

    files: Mapped[list[UploadedFile]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    trace_events: Mapped[list[TraceEvent]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    code_proposals: Mapped[list[CodeProposal]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    artifacts: Mapped[list[Artifact]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    context_doc: Mapped[SessionContextDoc | None] = relationship(
        back_populates="session", cascade="all, delete-orphan", uselist=False
    )
    datasets: Mapped[list[Dataset]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    proposals: Mapped[list[Proposal]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    user_feedback: Mapped[list[UserFeedback]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
