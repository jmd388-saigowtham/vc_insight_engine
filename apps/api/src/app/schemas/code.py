from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class CodeProposalCreate(BaseModel):
    step: str
    code: str
    language: str = "python"
    description: str | None = None
    node_name: str | None = None
    context: dict[str, Any] | None = None


class CodeProposalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    step: str
    code: str
    language: str
    status: str
    result_stdout: str | None
    result_stderr: str | None
    execution_time: float | None
    description: str | None = None
    node_name: str | None = None
    context: dict[str, Any] | None = None
    created_at: datetime
    resolved_at: datetime | None


class CodeApprovalRequest(BaseModel):
    feedback: str | None = None
    code: str | None = None
