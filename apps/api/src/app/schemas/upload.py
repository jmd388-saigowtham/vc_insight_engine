from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UploadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    filename: str
    file_type: str
    size_bytes: int
    row_count: int | None
    column_count: int | None
    created_at: datetime


class FileListResponse(BaseModel):
    files: list[UploadResponse]
    total: int
