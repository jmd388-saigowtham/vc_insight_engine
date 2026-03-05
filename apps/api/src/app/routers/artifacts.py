from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db_session, get_storage_service
from app.models.artifact import Artifact
from app.services.storage import StorageService

router = APIRouter()


class ArtifactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    artifact_type: str
    name: str
    storage_path: str
    metadata_: Any | None
    created_at: Any


@router.get("/sessions/{session_id}/artifacts", response_model=list[ArtifactResponse])
async def list_artifacts(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> list[ArtifactResponse]:
    stmt = (
        select(Artifact)
        .where(Artifact.session_id == session_id)
        .order_by(Artifact.created_at.desc())
    )
    result = await db.execute(stmt)
    artifacts = list(result.scalars().all())
    return [ArtifactResponse.model_validate(a) for a in artifacts]


@router.get("/artifacts/{artifact_id}", response_model=ArtifactResponse)
async def get_artifact(
    artifact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> ArtifactResponse:
    artifact = await db.get(Artifact, artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return ArtifactResponse.model_validate(artifact)


@router.get("/artifacts/{artifact_id}/download")
async def download_artifact(
    artifact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    storage: StorageService = Depends(get_storage_service),
) -> Response:
    artifact = await db.get(Artifact, artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")

    try:
        content = storage.get_file(artifact.storage_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Artifact file not found on disk")

    return Response(
        content=content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{artifact.name}"'},
    )
