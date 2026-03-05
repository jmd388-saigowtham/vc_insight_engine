from __future__ import annotations

from collections.abc import AsyncGenerator
from functools import lru_cache

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, settings
from app.database import get_db
from app.services.event_service import EventService
from app.services.storage import StorageService


@lru_cache
def get_settings() -> Settings:
    return settings


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_db():
        yield session


_event_service: EventService | None = None


def get_event_service() -> EventService:
    global _event_service
    if _event_service is None:
        _event_service = EventService()
    return _event_service


def get_storage_service(
    cfg: Settings = Depends(get_settings),
) -> StorageService:
    return StorageService(upload_dir=cfg.upload_dir)
