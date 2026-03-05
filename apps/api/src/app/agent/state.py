from __future__ import annotations

import uuid
from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    session_id: uuid.UUID
    company_name: str
    industry: str
    business_context: str
    current_step: str
    uploaded_files: list[dict[str, Any]]
    column_profiles: list[dict[str, Any]]
    merge_plan: dict[str, Any]
    merged_df_path: str
    target_column: str
    eda_results: dict[str, Any]
    preprocessing_plan: dict[str, Any]
    cleaned_df_path: str
    hypotheses: list[dict[str, Any]]
    feature_plan: dict[str, Any]
    features_df_path: str
    model_results: dict[str, Any]
    explainability_results: dict[str, Any]
    recommendations: list[dict[str, Any]]
    report_path: str
    error: str | None
    trace_events: list[dict[str, Any]]
