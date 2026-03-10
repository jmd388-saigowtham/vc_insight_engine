from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.session import Session


class Artifact(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        Index("ix_artifacts_session_id", "session_id"),
        Index("ix_artifacts_created_at", "created_at"),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    artifact_type: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[Any | None] = mapped_column("metadata_", JSONB, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, server_default="1", nullable=False)
    step: Mapped[str | None] = mapped_column(String(50), nullable=True)

    session: Mapped[Session] = relationship(back_populates="artifacts")
