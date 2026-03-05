from __future__ import annotations

import asyncio
import json
import uuid
from collections import defaultdict
from collections.abc import AsyncGenerator
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trace_event import TraceEvent
from app.schemas.event import TraceEventCreate


class EventService:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)

    def subscribe(self, session_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers[session_id].append(queue)
        return queue

    def unsubscribe(self, session_id: str, queue: asyncio.Queue) -> None:
        queues = self._subscribers.get(session_id, [])
        if queue in queues:
            queues.remove(queue)
        if not queues and session_id in self._subscribers:
            del self._subscribers[session_id]

    async def emit(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
        event: TraceEventCreate,
    ) -> TraceEvent:
        trace = TraceEvent(
            id=uuid.uuid4(),
            session_id=session_id,
            event_type=event.event_type,
            step=event.step,
            payload=event.payload,
        )
        db.add(trace)
        await db.commit()
        await db.refresh(trace)

        sse_data = {
            "id": str(trace.id),
            "event_type": trace.event_type,
            "step": trace.step,
            "payload": trace.payload,
            "created_at": trace.created_at.isoformat(),
        }

        sid = str(session_id)
        for queue in self._subscribers.get(sid, []):
            await queue.put(sse_data)

        return trace

    async def stream(self, session_id: str) -> AsyncGenerator[str, None]:
        queue = self.subscribe(session_id)
        try:
            while True:
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"event: trace\ndata: {json.dumps(data)}\n\n"
                except asyncio.TimeoutError:
                    yield f": keepalive {datetime.now(timezone.utc).isoformat()}\n\n"
        finally:
            self.unsubscribe(session_id, queue)

    async def get_events(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[TraceEvent]:
        stmt = (
            select(TraceEvent)
            .where(TraceEvent.session_id == session_id)
            .order_by(TraceEvent.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())
