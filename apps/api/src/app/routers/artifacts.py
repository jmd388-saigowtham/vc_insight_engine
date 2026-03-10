from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
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


class ArtifactFrontendResponse(BaseModel):
    """Response shape matching the frontend Artifact type."""

    id: str
    session_id: str
    step: str
    artifact_type: str
    title: str
    description: str
    file_path: str | None
    data: dict[str, Any] | None
    created_at: str


def _to_frontend(a: Artifact) -> dict[str, Any]:
    """Convert a DB Artifact to the frontend-compatible shape."""
    meta = a.metadata_ or {}
    # Determine if this is a displayable file (image)
    is_image = a.name.endswith((".png", ".jpg", ".jpeg", ".svg", ".gif"))
    file_path = f"/artifacts/{a.id}/file" if is_image else None
    return {
        "id": str(a.id),
        "session_id": str(a.session_id),
        "step": meta.get("step", a.artifact_type),
        "artifact_type": "image" if is_image else a.artifact_type,
        "title": meta.get("title", a.name),
        "description": meta.get("description", ""),
        "file_path": file_path,
        "data": meta,
        "created_at": a.created_at.isoformat() if a.created_at else "",
    }


@router.get("/sessions/{session_id}/artifacts")
async def list_artifacts(
    session_id: uuid.UUID,
    step: str | None = None,
    db: AsyncSession = Depends(get_db_session),
) -> list[dict[str, Any]]:
    stmt = select(Artifact).where(Artifact.session_id == session_id)
    if step:
        stmt = stmt.where(Artifact.artifact_type == step)
    stmt = stmt.order_by(Artifact.created_at.desc())
    result = await db.execute(stmt)
    artifacts = list(result.scalars().all())
    return [_to_frontend(a) for a in artifacts]


@router.get("/artifacts/{artifact_id}", response_model=ArtifactResponse)
async def get_artifact(
    artifact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> ArtifactResponse:
    artifact = await db.get(Artifact, artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return ArtifactResponse.model_validate(artifact)


@router.get("/artifacts/{artifact_id}/file")
async def serve_artifact_file(
    artifact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> FileResponse:
    """Serve an artifact file with the correct media type for browser rendering."""
    artifact = await db.get(Artifact, artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")

    file_path = Path(artifact.storage_path).resolve()
    upload_dir = Path(settings.upload_dir).resolve()
    if not file_path.is_relative_to(upload_dir):
        raise HTTPException(status_code=403, detail="Access denied")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    # Determine media type from extension
    suffix = file_path.suffix.lower()
    media_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".svg": "image/svg+xml",
        ".gif": "image/gif",
        ".json": "application/json",
        ".csv": "text/csv",
        ".html": "text/html",
        ".txt": "text/plain",
    }
    media_type = media_types.get(suffix, "application/octet-stream")
    return FileResponse(file_path, media_type=media_type, filename=artifact.name)


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
