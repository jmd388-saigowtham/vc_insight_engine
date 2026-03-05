from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db_session, get_event_service
from app.schemas.event import TraceEventResponse
from app.services.event_service import EventService

router = APIRouter()


@router.get("/sessions/{session_id}/events/stream")
async def stream_events(
    session_id: uuid.UUID,
    event_service: EventService = Depends(get_event_service),
) -> StreamingResponse:
    return StreamingResponse(
        event_service.stream(str(session_id)),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/sessions/{session_id}/events", response_model=list[TraceEventResponse])
async def get_events(
    session_id: uuid.UUID,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db_session),
    event_service: EventService = Depends(get_event_service),
) -> list[TraceEventResponse]:
    events = await event_service.get_events(db, session_id, limit=limit, offset=offset)
    return [TraceEventResponse.model_validate(e) for e in events]
