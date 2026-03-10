"""Tests for the execution policy — tool classification, context building.

Proves:
- Read-only tools classified as "auto" (no approval needed)
- Mutating tools classified as "approval_required"
- Context payload built with explanation fields
- Step context reads from session doc
- Step-to-section mapping covers all pipeline steps
- ExecutionPolicyService.is_safe_action uses SAFE_ACTIONS tuple format
- ExecutionPolicyService.execute_and_record with mocked MCP bridge
- All SAFE_ACTIONS entries return True via is_safe_action
- Non-safe actions return False via is_safe_action
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.nodes.node_helpers import (
    _step_to_section,
    build_context_payload,
    classify_action,
    emit_trace,
    read_step_context,
)
from app.agent.state import AgentState
from app.services.execution_policy import (
    SAFE_ACTIONS,
    ExecutionPolicyService,
    ExecutionResult,
)


def _blank_state() -> AgentState:
    """Create a minimal blank agent state."""
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


class TestToolClassification:
    """Test tool classification as auto vs approval_required."""

    def test_read_only_tools_auto(self):
        """Read-only tools should be classified as 'auto'."""
        auto_tools = [
            ("data_ingest", "profile"),
            ("data_ingest", "sample"),
            ("data_ingest", "row_count"),
            ("data_ingest", "list_sheets"),
            ("session_doc", "read"),
            ("session_doc", "get_section"),
            ("eda_plots", "distribution_plot"),
            ("eda_plots", "correlation_matrix"),
            ("hypothesis", "generate_hypotheses"),
            ("hypothesis", "run_test"),
            ("modeling_explain", "shap_analysis"),
            ("modeling_explain", "detect_leakage"),
            ("dtype_manager", "suggest_types"),
            ("code_registry", "retrieve"),
            ("merge_planner", "detect_keys"),
        ]
        for server, tool in auto_tools:
            result = classify_action(server, tool)
            assert result == "auto", f"Expected {server}.{tool} to be 'auto'"

    def test_mutating_tools_approval_required(self):
        """Non-read-only tools should require approval."""
        mutating_tools = [
            ("sandbox_executor", "run"),
            ("preprocessing", "handle_missing"),
            ("preprocessing", "encode_categorical"),
            ("modeling_explain", "train"),
            ("merge_planner", "execute_merge"),
            ("dtype_manager", "cast_column"),
            ("unknown_server", "unknown_tool"),
        ]
        for server, tool in mutating_tools:
            result = classify_action(server, tool)
            assert result == "approval_required", \
                f"Expected {server}.{tool} to be 'approval_required'"


class TestStepToSectionMapping:
    """Test that all pipeline steps map to session doc sections."""

    def test_all_steps_have_mappings(self):
        from app.services.step_state_service import STEP_ORDER

        for step in STEP_ORDER:
            section = _step_to_section(step)
            assert section, f"No section mapping for step: {step}"
            assert section != step, f"Step {step} has no custom mapping"

    def test_known_mappings(self):
        """Verify specific well-known mappings."""
        assert _step_to_section("profiling") == "Column Dictionary"
        assert _step_to_section("target_id") == "Target Variable"
        assert _step_to_section("feature_selection") == "Feature Selection"
        assert _step_to_section("eda") == "EDA Findings"
        assert _step_to_section("preprocessing") == "Preprocessing Decisions"
        assert _step_to_section("hypothesis") == "Hypotheses & Results"
        assert _step_to_section("modeling") == "Model Results"
        assert _step_to_section("explainability") == "Explainability"
        assert _step_to_section("recommendation") == "Recommendations"
        assert _step_to_section("report") == "Report"
        assert _step_to_section("merge_planning") == "Merge Strategy"
        assert _step_to_section("feature_eng") == "Feature Engineering"
        assert _step_to_section("dtype_handling") == "Dtype Decisions"
        assert _step_to_section("data_understanding") == "Data Inventory"
        assert _step_to_section("opportunity_analysis") == "Value Creation Analysis"
        assert _step_to_section("threshold_calibration") == "Threshold Decisions"


class TestContextPayload:
    """Test building context payloads for code proposals."""

    def test_basic_context_payload(self):
        state = _blank_state()
        payload = build_context_payload(
            state, "modeling",
            ai_explanation="Training a model to predict churn",
            tool_tried="modeling_explain.train",
            tool_insufficiency="Need custom hyperparameters",
        )
        assert payload["ai_explanation"] == "Training a model to predict churn"
        assert payload["tool_tried"] == "modeling_explain.train"
        assert payload["tool_insufficiency"] == "Need custom hyperparameters"

    def test_context_payload_with_denial(self):
        state = _blank_state()
        state["denial_counts"] = {"modeling": 1}
        state["denial_feedback"] = {"modeling": ["Use XGBoost instead"]}
        payload = build_context_payload(state, "modeling")
        assert payload["denial_count"] == 1
        assert "XGBoost" in str(payload.get("denial_feedback", []))

    def test_context_payload_with_alternatives(self):
        state = _blank_state()
        alts = [
            {"strategy": "Random Forest", "reasoning": "Works well with tabular data"},
            {"strategy": "Gradient Boosting", "reasoning": "Better for imbalanced data"},
        ]
        payload = build_context_payload(
            state, "modeling",
            alternative_strategies=alts,
        )
        assert payload["alternative_strategies"] == alts


class TestEmitTrace:
    """Test trace event emission."""

    def test_emit_trace_appends_event(self):
        state = _blank_state()
        emit_trace(state, "TOOL_CALL", "profiling", {"tool": "data_ingest.profile"})
        assert len(state["trace_events"]) == 1
        event = state["trace_events"][0]
        assert event["event_type"] == "TOOL_CALL"
        assert event["step"] == "profiling"
        assert event["payload"]["tool"] == "data_ingest.profile"

    def test_emit_trace_multiple_events(self):
        state = _blank_state()
        emit_trace(state, "TOOL_CALL", "eda", {"tool": "eda_plots.distribution"})
        emit_trace(state, "TOOL_RESULT", "eda", {"plots": 3})
        emit_trace(state, "AI_REASONING", "eda", {"message": "EDA complete"})
        assert len(state["trace_events"]) == 3


class TestReadStepContext:
    """Test read_step_context returns useful context."""

    def test_read_step_context_returns_dict(self):
        state = _blank_state()
        ctx = read_step_context(state, "modeling")
        assert isinstance(ctx, dict)
        # Should have standard keys even if session doc is empty
        assert "session_doc_section" in ctx or "strategy_hint" in ctx or ctx == {}

    def test_read_step_context_with_denial_feedback(self):
        state = _blank_state()
        state["denial_feedback"] = {"modeling": ["Try logistic regression"]}
        state["denial_counts"] = {"modeling": 1}
        ctx = read_step_context(state, "modeling")
        assert isinstance(ctx, dict)


# ---------------------------------------------------------------------------
# ExecutionPolicyService.is_safe_action — tuple format
# ---------------------------------------------------------------------------


class TestIsSafeAction:
    """Test is_safe_action with (server, tool) tuple format."""

    def test_all_safe_actions_return_true(self):
        """Every entry in SAFE_ACTIONS should return True from is_safe_action."""
        policy = ExecutionPolicyService()
        for server, tool in SAFE_ACTIONS:
            assert policy.is_safe_action(server, tool), \
                f"Expected ({server}, {tool}) to be safe"

    def test_non_safe_actions_return_false(self):
        """Non-safe actions should return False from is_safe_action."""
        policy = ExecutionPolicyService()
        non_safe = [
            ("sandbox_executor", "run"),
            ("preprocessing", "handle_missing"),
            ("preprocessing", "encode_categorical"),
            ("preprocessing", "scale_numeric"),
            ("modeling_explain", "train"),
            ("merge_planner", "execute_merge"),
            ("merge_planner", "generate_merge_code"),
            ("dtype_manager", "cast_column"),
            ("code_registry", "store"),
            ("session_doc", "upsert"),
            ("unknown_server", "unknown_tool"),
        ]
        for server, tool in non_safe:
            assert not policy.is_safe_action(server, tool), \
                f"Expected ({server}, {tool}) to NOT be safe"

    def test_safe_actions_is_frozenset_of_tuples(self):
        """SAFE_ACTIONS should be a frozenset of (str, str) tuples."""
        assert isinstance(SAFE_ACTIONS, frozenset)
        for entry in SAFE_ACTIONS:
            assert isinstance(entry, tuple), f"Entry {entry} is not a tuple"
            assert len(entry) == 2, f"Entry {entry} does not have 2 elements"
            assert isinstance(entry[0], str), f"Server {entry[0]} is not a str"
            assert isinstance(entry[1], str), f"Tool {entry[1]} is not a str"

    def test_safe_actions_covers_all_read_only_tools(self):
        """SAFE_ACTIONS in execution_policy should cover the same tools as
        _READ_ONLY_TOOLS in node_helpers."""
        from app.agent.nodes.node_helpers import _READ_ONLY_TOOLS

        for server, tool in _READ_ONLY_TOOLS:
            assert (server, tool) in SAFE_ACTIONS, \
                f"_READ_ONLY_TOOLS entry ({server}, {tool}) missing from SAFE_ACTIONS"


# ---------------------------------------------------------------------------
# ExecutionPolicyService.execute_and_record — mocked MCP bridge
# ---------------------------------------------------------------------------


class TestExecuteAndRecord:
    """Test execute_and_record with mocked MCP bridge."""

    @pytest.mark.asyncio
    async def test_safe_action_auto_executes(self):
        """A safe action should auto-execute and return tool_auto result."""
        policy = ExecutionPolicyService()

        mock_bridge = MagicMock()
        mock_bridge.call_tool = AsyncMock(return_value={"rows": 100})
        policy._bridge = mock_bridge

        state = _blank_state()
        state["session_id"] = "test-session"

        result = await policy.execute_and_record(
            state,
            step="profiling",
            server="data_ingest",
            tool="profile",
            arguments={"file_path": "/tmp/test.csv"},
            description="Profile uploaded file",
        )

        assert isinstance(result, ExecutionResult)
        assert result.success is True
        assert result.action_taken == "tool_auto"
        assert result.result == {"rows": 100}
        assert result.proposal_needed is False
        assert len(result.trace_events) >= 1
        # Verify a TOOL_DISCOVERY event was emitted
        discovery_events = [
            e for e in result.trace_events if e["event_type"] == "TOOL_DISCOVERY"
        ]
        assert len(discovery_events) >= 1

    @pytest.mark.asyncio
    async def test_unsafe_action_returns_proposal(self):
        """A non-safe action should return proposal data, not execute."""
        policy = ExecutionPolicyService()

        mock_bridge = MagicMock()
        mock_bridge.call_tool = AsyncMock()
        policy._bridge = mock_bridge

        state = _blank_state()
        state["session_id"] = "test-session"

        result = await policy.execute_and_record(
            state,
            step="modeling",
            server="modeling_explain",
            tool="train",
            arguments={"data_path": "/tmp/train.csv"},
            description="Train model",
        )

        assert isinstance(result, ExecutionResult)
        assert result.success is True
        assert result.action_taken == "tool_proposed"
        assert result.proposal_needed is True
        assert result.proposal_data["tool_server"] == "modeling_explain"
        assert result.proposal_data["tool_name"] == "train"
        # Tool should NOT have been called
        mock_bridge.call_tool.assert_not_called()

    @pytest.mark.asyncio
    async def test_safe_action_failure_returns_error(self):
        """When a safe auto-execute fails, the result should indicate error."""
        policy = ExecutionPolicyService()

        mock_bridge = MagicMock()
        mock_bridge.call_tool = AsyncMock(side_effect=RuntimeError("File not found"))
        policy._bridge = mock_bridge

        state = _blank_state()
        state["session_id"] = "test-session"

        result = await policy.execute_and_record(
            state,
            step="profiling",
            server="data_ingest",
            tool="profile",
            arguments={"file_path": "/tmp/missing.csv"},
        )

        assert result.success is False
        assert result.action_taken == "tool_auto"
        assert "File not found" in result.error
