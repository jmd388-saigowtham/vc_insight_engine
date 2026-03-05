from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.uploaded_file import UploadedFile
from app.services.storage import StorageService

ALLOWED_EXTENSIONS = {".csv", ".xlsx"}


class UploadService:
    def __init__(self, db: AsyncSession, storage: StorageService) -> None:
        self.db = db
        self.storage = storage

    async def upload_file(
        self, session_id: uuid.UUID, file: UploadFile
    ) -> UploadedFile:
        if not file.filename:
            raise HTTPException(status_code=400, detail="No filename provided")

        ext = Path(file.filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
            )

        content = await file.read()
        size_bytes = len(content)
        max_size = settings.max_upload_size_mb * 1024 * 1024
        if size_bytes > max_size:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size: {settings.max_upload_size_mb}MB",
            )

        storage_path = self.storage.save_file(content, file.filename)

        file_type = ext.lstrip(".")
        uploaded = UploadedFile(
            id=uuid.uuid4(),
            session_id=session_id,
            filename=file.filename,
            storage_path=storage_path,
            file_type=file_type,
            size_bytes=size_bytes,
        )
        self.db.add(uploaded)
        await self.db.commit()
        await self.db.refresh(uploaded)
        return uploaded

    async def list_files(self, session_id: uuid.UUID) -> list[UploadedFile]:
        stmt = (
            select(UploadedFile)
            .where(UploadedFile.session_id == session_id)
            .order_by(UploadedFile.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_file(self, file_id: uuid.UUID) -> UploadedFile | None:
        return await self.db.get(UploadedFile, file_id)
