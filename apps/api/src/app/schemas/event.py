from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class TraceEventCreate(BaseModel):
    event_type: str
    step: str | None = None
    payload: dict[str, Any] | None = None


class TraceEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    event_type: str
    step: str | None
    payload: Any | None
    created_at: datetime


class SSEEvent(BaseModel):
    event: str
    data: dict[str, Any]
