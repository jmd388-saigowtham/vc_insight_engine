from __future__ import annotations

import uuid
from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    # Session identity
    session_id: uuid.UUID
    company_name: str
    industry: str
    business_context: str
    current_step: str

    # Data paths
    uploaded_files: list[dict[str, Any]]
    column_profiles: list[dict[str, Any]]
    merge_plan: dict[str, Any]
    merged_df_path: str

    # Target & features
    target_column: str
    selected_features: list[str]

    # Analysis results
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

    # Orchestrator
    next_action: str
    llm_plan: str
    awaiting_approval: str | None
    step_states: dict[str, str]
    session_doc: str

    # Approval gate (two-phase code approval pattern)
    pending_step: str
    pending_code: str
    pending_code_description: str
    approval_status: str
    approved_code: str
    denial_counts: dict[str, int]

    # Business-logic proposal gate (plan-level approval)
    pending_proposal_step: str
    pending_proposal_plan: dict[str, Any]
    pending_proposal_summary: str
    pending_proposal_reasoning: str
    pending_proposal_alternatives: list[dict[str, Any]]
    pending_proposal_type: str
    proposal_status: str  # ""|"approved"|"revision_requested"|"rejected"
    proposal_feedback: str
    proposal_revision_count: dict[str, int]
    user_feedback: dict[str, list[str]]

    # New pipeline stage results
    data_understanding_summary: dict[str, Any]
    opportunity_recommendations: list[dict[str, Any]]
    selected_opportunity: dict[str, Any]
    dtype_decisions: dict[str, Any]
    threshold_config: dict[str, Any]

    # LLM-driven orchestration
    orchestrator_reasoning: str
    strategy_hint: str
    orchestrator_candidates: list[dict[str, Any]]
    orchestrator_reflection: str
    run_id: str
    denial_feedback: dict[str, list[str]]
    node_plans: dict[str, dict[str, Any]]
    pending_context: dict[str, Any]

    # Tracing
    error: str | None
    trace_events: list[dict[str, Any]]

    # Internal: loop detection (not persisted)
    _loop_history: list[str]
