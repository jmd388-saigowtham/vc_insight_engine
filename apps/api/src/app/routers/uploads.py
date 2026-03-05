from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db_session, get_storage_service
from app.schemas.upload import FileListResponse, UploadResponse
from app.services.profiling_service import ProfilingService
from app.services.storage import StorageService
from app.services.upload_service import UploadService

logger = structlog.get_logger()

router = APIRouter()


@router.post(
    "/sessions/{session_id}/upload",
    response_model=UploadResponse,
    status_code=201,
)
async def upload_file(
    session_id: uuid.UUID,
    file: UploadFile,
    db: AsyncSession = Depends(get_db_session),
    storage: StorageService = Depends(get_storage_service),
) -> UploadResponse:
    service = UploadService(db, storage)
    uploaded = await service.upload_file(session_id, file)

    try:
        profiling = ProfilingService(db)
        await profiling.profile_file(uploaded.id)
        await db.refresh(uploaded)
    except Exception:
        logger.warning(
            "profiling_failed",
            file_id=str(uploaded.id),
            exc_info=True,
        )

    return UploadResponse.model_validate(uploaded)


@router.get("/sessions/{session_id}/files", response_model=FileListResponse)
async def list_files(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    storage: StorageService = Depends(get_storage_service),
) -> FileListResponse:
    service = UploadService(db, storage)
    files = await service.list_files(session_id)
    return FileListResponse(
        files=[UploadResponse.model_validate(f) for f in files],
        total=len(files),
    )


@router.get("/files/{file_id}", response_model=UploadResponse)
async def get_file(
    file_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    storage: StorageService = Depends(get_storage_service),
) -> UploadResponse:
    service = UploadService(db, storage)
    uploaded = await service.get_file(file_id)
    if uploaded is None:
        raise HTTPException(status_code=404, detail="File not found")
    return UploadResponse.model_validate(uploaded)
