"""Tests for agent node helper functions."""

from __future__ import annotations

import uuid

from app.agent.nodes.node_helpers import (
    build_context_payload,
    classify_action,
    emit_trace,
    read_step_context,
)
from app.agent.state import AgentState


def _make_state(**overrides) -> AgentState:
    base: AgentState = {
        "session_id": uuid.uuid4(),
        "company_name": "Test Corp",
        "industry": "SaaS",
        "business_context": "Churn analysis",
        "current_step": "profiling",
        "uploaded_files": [],
        "column_profiles": [],
        "merge_plan": {},
        "merged_df_path": "",
        "target_column": "",
        "selected_features": [],
        "eda_results": {},
        "preprocessing_plan": {},
        "cleaned_df_path": "",
        "hypotheses": [],
        "feature_plan": {},
        "features_df_path": "",
        "model_results": {},
        "explainability_results": {},
        "recommendations": [],
        "report_path": "",
        "next_action": "",
        "llm_plan": "",
        "awaiting_approval": None,
        "step_states": {},
        "session_doc": "",
        "pending_step": "",
        "pending_code": "",
        "pending_code_description": "",
        "approval_status": "",
        "approved_code": "",
        "denial_counts": {},
        "orchestrator_reasoning": "",
        "strategy_hint": "",
        "run_id": "",
        "denial_feedback": {},
        "node_plans": {},
        "pending_context": {},
        "error": None,
        "trace_events": [],
    }
    base.update(overrides)
    return base


class TestEmitTrace:
    def test_appends_event(self):
        state = _make_state()
        emit_trace(state, "AI_REASONING", "eda", {"reasoning": "test"})
        assert len(state["trace_events"]) == 1
        assert state["trace_events"][0]["event_type"] == "AI_REASONING"
        assert state["trace_events"][0]["step"] == "eda"
        assert state["trace_events"][0]["payload"]["reasoning"] == "test"

    def test_appends_multiple_events(self):
        state = _make_state()
        emit_trace(state, "TOOL_CALL", "profiling", {"tool": "data_ingest.profile"})
        emit_trace(state, "TOOL_RESULT", "profiling", {"columns": 10})
        assert len(state["trace_events"]) == 2

    def test_preserves_existing_events(self):
        state = _make_state(trace_events=[{"event_type": "PLAN", "step": "pipeline", "payload": {}}])
        emit_trace(state, "AI_REASONING", "eda", {"reasoning": "test"})
        assert len(state["trace_events"]) == 2


class TestClassifyAction:
    def test_read_only_tools(self):
        assert classify_action("data_ingest", "profile") == "auto"
        assert classify_action("eda_plots", "distribution_plot") == "auto"
        assert classify_action("hypothesis", "run_test") == "auto"
        assert classify_action("session_doc", "read") == "auto"
        assert classify_action("modeling_explain", "shap_analysis") == "auto"

    def test_mutating_tools(self):
        assert classify_action("preprocessing", "handle_missing") == "approval_required"
        assert classify_action("preprocessing", "encode_categorical") == "approval_required"
        assert classify_action("sandbox_executor", "run") == "approval_required"
        assert classify_action("merge_planner", "execute_merge") == "approval_required"
        assert classify_action("modeling_explain", "train") == "approval_required"

    def test_unknown_tool(self):
        assert classify_action("unknown_server", "unknown_tool") == "approval_required"


class TestReadStepContext:
    def test_returns_strategy_hint(self):
        state = _make_state(strategy_hint="Focus on churn features")
        ctx = read_step_context(state, "eda")
        assert ctx["strategy_hint"] == "Focus on churn features"

    def test_returns_denial_feedback(self):
        state = _make_state(
            denial_feedback={"eda": ["Too many plots", "Need scatter plots"]},
            denial_counts={"eda": 2},
        )
        ctx = read_step_context(state, "eda")
        assert ctx["denial_feedback"] == ["Too many plots", "Need scatter plots"]
        assert ctx["denial_count"] == 2

    def test_empty_denial_feedback(self):
        state = _make_state()
        ctx = read_step_context(state, "eda")
        assert ctx["denial_feedback"] == []
        assert ctx["denial_count"] == 0

    def test_includes_session_doc(self):
        state = _make_state(session_doc="Full session document text")
        ctx = read_step_context(state, "eda")
        assert ctx["session_doc_full"] == "Full session document text"


class TestBuildContextPayload:
    def test_basic_payload(self):
        state = _make_state()
        payload = build_context_payload(
            state, "modeling",
            ai_explanation="Training 3 models based on data characteristics",
        )
        assert payload["ai_explanation"] == "Training 3 models based on data characteristics"
        assert payload["denial_count"] == 0
        assert payload["max_denials"] == 3
        assert payload["denial_feedback"] == []

    def test_with_denials(self):
        state = _make_state(
            denial_counts={"modeling": 1},
            denial_feedback={"modeling": ["Try different models"]},
        )
        payload = build_context_payload(
            state, "modeling",
            ai_explanation="Revised model selection",
            tool_tried="train",
            alternative_strategies=["Use ensemble only", "Add SVM"],
        )
        assert payload["denial_count"] == 1
        assert payload["denial_feedback"] == ["Try different models"]
        assert payload["tool_tried"] == "train"
        assert len(payload["alternative_strategies"]) == 2
