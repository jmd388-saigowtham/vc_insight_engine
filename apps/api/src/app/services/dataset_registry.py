"""Dataset registry — tracks all datasets (uploaded, merged, derived, preprocessed) per session."""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dataset import Dataset

logger = structlog.get_logger()


class DatasetRegistry:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def register(
        self,
        session_id: uuid.UUID,
        source_type: str,
        name: str,
        file_path: str,
        row_count: int | None = None,
        column_count: int | None = None,
        parent_dataset_id: uuid.UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Dataset:
        """Register a new dataset in the registry."""
        dataset = Dataset(
            id=uuid.uuid4(),
            session_id=session_id,
            source_type=source_type,
            name=name,
            file_path=file_path,
            row_count=row_count,
            column_count=column_count,
            parent_dataset_id=parent_dataset_id,
            metadata_=metadata,
        )
        self.db.add(dataset)
        await self.db.commit()
        await self.db.refresh(dataset)

        logger.info(
            "dataset_registry.register",
            dataset_id=str(dataset.id),
            session_id=str(session_id),
            source_type=source_type,
            name=name,
        )
        return dataset

    async def list_datasets(self, session_id: uuid.UUID) -> list[Dataset]:
        """List all datasets for a session."""
        stmt = (
            select(Dataset)
            .where(Dataset.session_id == session_id)
            .order_by(Dataset.created_at)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_latest(
        self, session_id: uuid.UUID, source_type: str | None = None
    ) -> Dataset | None:
        """Get the most recent dataset for a session, optionally by type."""
        stmt = (
            select(Dataset)
            .where(Dataset.session_id == session_id)
        )
        if source_type:
            stmt = stmt.where(Dataset.source_type == source_type)
        stmt = stmt.order_by(Dataset.created_at.desc()).limit(1)

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
