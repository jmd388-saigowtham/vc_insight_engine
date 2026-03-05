from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db_session
from app.schemas.session import SessionCreate, SessionResponse, SessionUpdate
from app.services.session_service import SessionService

router = APIRouter()


def _get_service(db: AsyncSession = Depends(get_db_session)) -> SessionService:
    return SessionService(db)


@router.post("", response_model=SessionResponse, status_code=201)
async def create_session(
    data: SessionCreate,
    service: SessionService = Depends(_get_service),
) -> SessionResponse:
    session = await service.create(data)
    return SessionResponse.model_validate(session)


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: uuid.UUID,
    service: SessionService = Depends(_get_service),
) -> SessionResponse:
    session = await service.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionResponse.model_validate(session)


@router.patch("/{session_id}", response_model=SessionResponse)
async def update_session(
    session_id: uuid.UUID,
    data: SessionUpdate,
    service: SessionService = Depends(_get_service),
) -> SessionResponse:
    session = await service.update(session_id, data)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionResponse.model_validate(session)


class BusinessContextUpdate(BaseModel):
    business_context: str


@router.post("/{session_id}/business-context", response_model=SessionResponse)
async def update_business_context(
    session_id: uuid.UUID,
    data: BusinessContextUpdate,
    service: SessionService = Depends(_get_service),
) -> SessionResponse:
    session = await service.update_business_context(session_id, data.business_context)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionResponse.model_validate(session)


@router.get("", response_model=list[SessionResponse])
async def list_sessions(
    limit: int = 50,
    offset: int = 0,
    service: SessionService = Depends(_get_service),
) -> list[SessionResponse]:
    sessions = await service.list_all(limit=limit, offset=offset)
    return [SessionResponse.model_validate(s) for s in sessions]
