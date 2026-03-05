from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db_session
from app.schemas.profile import ColumnProfileResponse, ProfileSummary
from app.services.profiling_service import ProfilingService

router = APIRouter()


def _get_service(db: AsyncSession = Depends(get_db_session)) -> ProfilingService:
    return ProfilingService(db)


@router.get("/files/{file_id}/profile", response_model=list[ColumnProfileResponse])
async def get_file_profile(
    file_id: uuid.UUID,
    service: ProfilingService = Depends(_get_service),
) -> list[ColumnProfileResponse]:
    profiles = await service.get_profiles(file_id)
    return [ColumnProfileResponse.model_validate(p) for p in profiles]


class DescriptionUpdate(BaseModel):
    description: str


@router.patch("/columns/{column_id}/description", response_model=ColumnProfileResponse)
async def update_column_description(
    column_id: uuid.UUID,
    data: DescriptionUpdate,
    service: ProfilingService = Depends(_get_service),
) -> ColumnProfileResponse:
    profile = await service.update_description(column_id, data.description)
    if profile is None:
        raise HTTPException(status_code=404, detail="Column profile not found")
    return ColumnProfileResponse.model_validate(profile)


@router.get("/sessions/{session_id}/tables", response_model=list[ProfileSummary])
async def get_session_tables(
    session_id: uuid.UUID,
    service: ProfilingService = Depends(_get_service),
) -> list[ProfileSummary]:
    tables = await service.get_session_tables(session_id)
    return [
        ProfileSummary(
            file_id=t["file_id"],
            filename=t["filename"],
            row_count=t["row_count"],
            column_count=t["column_count"],
            columns=[ColumnProfileResponse.model_validate(c) for c in t["columns"]],
        )
        for t in tables
    ]
