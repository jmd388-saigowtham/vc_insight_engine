from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CodeProposalCreate(BaseModel):
    step: str
    code: str
    language: str = "python"


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
    created_at: datetime
    resolved_at: datetime | None


class CodeApprovalRequest(BaseModel):
    feedback: str | None = None
