from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SessionCreate(BaseModel):
    company_name: str
    industry: str | None = None
    business_context: str | None = None


class SessionUpdate(BaseModel):
    company_name: str | None = None
    industry: str | None = None
    business_context: str | None = None
    current_step: str | None = None
    step_states: dict | None = None
    target_column: str | None = None
    selected_features: list[str] | None = None


class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_name: str
    industry: str | None
    business_context: str | None
    current_step: str
    status: str
    step_states: dict | None = None
    target_column: str | None = None
    selected_features: list[str] | None = None
    created_at: datetime
    updated_at: datetime
