"""Pydantic schemas for business-logic proposals and user feedback."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


# ── Proposal schemas ──────────────────────────────────────────────

class ProposalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    step: str
    proposal_type: str
    status: str
    version: int
    plan: Any | None = None
    summary: str | None = None
    ai_reasoning: str | None = None
    alternatives: Any | None = None
    user_feedback: str | None = None
    parent_id: uuid.UUID | None = None
    resolved_at: datetime | None = None
    created_at: datetime


class ProposalRevisionRequest(BaseModel):
    feedback: str


class ProposalSelectionRequest(BaseModel):
    """For stages like opportunity analysis where user selects one option."""
    selected_index: int
    feedback: str | None = None


# ── User Feedback schemas ─────────────────────────────────────────

class UserFeedbackCreate(BaseModel):
    message: str
    step: str | None = None


class UserFeedbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    step: str | None
    message: str
    status: str
    created_at: datetime
