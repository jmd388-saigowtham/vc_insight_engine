from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict


class ColumnProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    file_id: uuid.UUID
    column_name: str
    dtype: str
    null_count: int | None
    null_pct: float | None
    unique_count: int | None
    min_value: str | None
    max_value: str | None
    mean_value: float | None
    sample_values: Any | None
    description: str | None


class ProfileSummary(BaseModel):
    file_id: uuid.UUID
    filename: str
    row_count: int | None
    column_count: int | None
    columns: list[ColumnProfileResponse]
