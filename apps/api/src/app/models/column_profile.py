from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin

if TYPE_CHECKING:
    from app.models.uploaded_file import UploadedFile


class ColumnProfile(UUIDMixin, Base):
    __tablename__ = "column_profiles"
    __table_args__ = (Index("ix_column_profiles_file_id", "file_id"),)

    file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("uploaded_files.id", ondelete="CASCADE"),
        nullable=False,
    )
    column_name: Mapped[str] = mapped_column(String(255), nullable=False)
    dtype: Mapped[str] = mapped_column(String(50), nullable=False)
    null_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    null_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    unique_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    min_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    max_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    mean_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    sample_values: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    file: Mapped[UploadedFile] = relationship(back_populates="column_profiles")
