"""Tests for trace completeness — all event types emitted, trace structure.

Proves:
- All required event types are recognized
- Trace events have correct structure
- emit_trace adds events to state
- Event type taxonomy is complete
"""

from __future__ import annotations

from app.agent.nodes.node_helpers import emit_trace
from app.agent.state import AgentState


def _blank_state() -> AgentState:
    return AgentState(
        session_id=None,
        current_step="",
        uploaded_files=[],
        column_profiles=[],
        next_action="",
        pending_step="",
        pending_code="",
        pending_code_description="",
        approval_status="",
        approved_code="",
        denial_counts={},
        step_states={},
        trace_events=[],
        pending_proposal_step="",
        pending_proposal_plan={},
        pending_proposal_summary="",
        pending_proposal_reasoning="",
        pending_proposal_alternatives=[],
        pending_proposal_type="",
        proposal_status="",
        proposal_feedback="",
        proposal_revision_count={},
        user_feedback={},
    )


# All event types the system should support
REQUIRED_EVENT_TYPES = {
    # Core execution events
    "PLAN",
    "TOOL_CALL",
    "TOOL_RESULT",
    "CODE_PROPOSED",
    "CODE_APPROVED",
    "CODE_DENIED",
    "EXEC_START",
    "EXEC_END",
    "ERROR",
    "INFO",
    # AI reasoning events
    "AI_REASONING",
    # Proposal lifecycle
    "PROPOSAL_CREATED",
    "PROPOSAL_APPROVED",
    "PROPOSAL_REVISED",
    "PROPOSAL_REJECTED",
    # Final output
    "FINAL_SUMMARY",
}


class TestEventTypeTaxonomy:
    """Test that all required event types are supported."""

    def test_all_event_types_can_be_emitted(self):
        """Every event type should be emittable without error."""
        state = _blank_state()
        for event_type in REQUIRED_EVENT_TYPES:
            emit_trace(state, event_type, "test_step", {"test": True})
        assert len(state["trace_events"]) == len(REQUIRED_EVENT_TYPES)

    def test_event_structure(self):
        """Trace events should have event_type, step, and payload."""
        state = _blank_state()
        emit_trace(state, "TOOL_CALL", "profiling", {
            "tool": "data_ingest.profile",
            "file_path": "/data/test.csv",
        })

        event = state["trace_events"][0]
        assert "event_type" in event
        assert "step" in event
        assert "payload" in event
        assert event["event_type"] == "TOOL_CALL"
        assert event["step"] == "profiling"
        assert event["payload"]["tool"] == "data_ingest.profile"


class TestTraceAccumulation:
    """Test that trace events accumulate correctly across steps."""

    def test_multiple_steps_accumulate(self):
        state = _blank_state()

        # Simulate a mini pipeline
        emit_trace(state, "PLAN", "profiling", {"message": "Starting profiling"})
        emit_trace(state, "TOOL_CALL", "profiling", {"tool": "data_ingest.profile"})
        emit_trace(state, "TOOL_RESULT", "profiling", {"columns": 10, "rows": 1000})
        emit_trace(state, "AI_REASONING", "target_id", {"message": "Identified churn"})
        emit_trace(state, "CODE_PROPOSED", "eda", {"code_length": 50})
        emit_trace(state, "CODE_APPROVED", "eda", {"approved": True})
        emit_trace(state, "EXEC_START", "eda", {"message": "Running EDA code"})
        emit_trace(state, "EXEC_END", "eda", {"success": True, "plots": 4})

        assert len(state["trace_events"]) == 8

        # Verify steps are correctly tagged
        steps = [e["step"] for e in state["trace_events"]]
        assert steps.count("profiling") == 3
        assert steps.count("target_id") == 1
        assert steps.count("eda") == 4

    def test_error_event(self):
        state = _blank_state()
        emit_trace(state, "ERROR", "modeling", {
            "message": "Training failed",
            "error": "OutOfMemoryError",
        })

        event = state["trace_events"][0]
        assert event["event_type"] == "ERROR"
        assert "OutOfMemory" in event["payload"]["error"]

    def test_final_summary_event(self):
        state = _blank_state()
        emit_trace(state, "FINAL_SUMMARY", "report", {
            "narrative_summary": "Analysis complete",
            "key_decisions": {"best_model": "Random Forest"},
            "artifacts_count": 15,
        })

        event = state["trace_events"][0]
        assert event["event_type"] == "FINAL_SUMMARY"
        assert event["payload"]["artifacts_count"] == 15

    def test_proposal_events(self):
        state = _blank_state()
        emit_trace(state, "PROPOSAL_CREATED", "feature_selection", {
            "summary": "Selected 10 features",
            "proposal_type": "feature_selection",
        })
        emit_trace(state, "PROPOSAL_REVISED", "feature_selection", {
            "summary": "Revised: added 3 features",
            "revision": 1,
        })
        emit_trace(state, "PROPOSAL_APPROVED", "feature_selection", {
            "summary": "Approved 13 features",
        })

        assert len(state["trace_events"]) == 3
        types = [e["event_type"] for e in state["trace_events"]]
        assert "PROPOSAL_CREATED" in types
        assert "PROPOSAL_REVISED" in types
        assert "PROPOSAL_APPROVED" in types
