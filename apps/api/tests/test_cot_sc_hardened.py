"""Tests for hardened CoT-SC + orchestrator failure handling — Phase 4.

Verifies that:
- All 3 CoT-SC candidates failing returns 'wait' not 'end'
- __failed__ candidates are filtered out of voting
- Malformed JSON candidates get filtered
- Fallback reason is logged in trace events
- invoke_llm_json repairs trailing commas
"""

import pytest
from unittest.mock import AsyncMock, patch

from app.agent.llm import _repair_json, _try_parse_json


def _make_state(**overrides):
    base = {
        "session_id": None,
        "company_name": "TestCo",
        "industry": "SaaS",
        "business_context": "Churn analysis",
        "current_step": "",
        "uploaded_files": [{"filename": "test.csv"}],
        "column_profiles": [],
        "merge_plan": {},
        "merged_df_path": "/tmp/test.csv",
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
        "pending_proposal_step": "",
        "pending_proposal_plan": {},
        "pending_proposal_summary": "",
        "pending_proposal_reasoning": "",
        "pending_proposal_alternatives": [],
        "pending_proposal_type": "",
        "proposal_status": "",
        "proposal_feedback": "",
        "proposal_revision_count": {},
        "user_feedback": {},
        "data_understanding_summary": {},
        "opportunity_recommendations": [],
        "selected_opportunity": {},
        "dtype_decisions": {},
        "threshold_config": {},
        "orchestrator_reasoning": "",
        "strategy_hint": "",
        "orchestrator_candidates": [],
        "orchestrator_reflection": "",
        "run_id": "test-run",
        "denial_feedback": {},
        "node_plans": {},
        "pending_context": {},
        "error": None,
        "trace_events": [],
    }
    base.update(overrides)
    return base


class TestJsonRepair:
    """Test JSON repair for trailing commas."""

    def test_trailing_comma_in_object(self):
        text = '{"key": "value", "key2": "value2",}'
        repaired = _repair_json(text)
        parsed = _try_parse_json(repaired)
        assert parsed is not None
        assert parsed["key"] == "value"

    def test_trailing_comma_in_array(self):
        text = '{"items": [1, 2, 3,]}'
        repaired = _repair_json(text)
        parsed = _try_parse_json(repaired)
        assert parsed is not None
        assert parsed["items"] == [1, 2, 3]

    def test_nested_trailing_commas(self):
        text = '{"a": {"b": "c",}, "d": [1,],}'
        repaired = _repair_json(text)
        parsed = _try_parse_json(repaired)
        assert parsed is not None
        assert parsed["a"]["b"] == "c"

    def test_valid_json_unchanged(self):
        text = '{"key": "value"}'
        repaired = _repair_json(text)
        assert repaired == text

    def test_try_parse_json_valid(self):
        result = _try_parse_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_try_parse_json_invalid(self):
        result = _try_parse_json("not json")
        assert result is None

    def test_try_parse_json_non_dict(self):
        result = _try_parse_json("[1, 2, 3]")
        assert result is None


class TestCandidateFiltering:
    """Test that __failed__ candidates and 0.0 confidence are filtered."""

    @pytest.mark.asyncio
    @patch("app.agent.nodes.orchestrator.invoke_llm_json")
    async def test_all_candidates_fail_returns_wait(self, mock_llm):
        """When all 3 CoT-SC candidates fail, orchestrator returns 'wait'."""
        mock_llm.side_effect = Exception("LLM unavailable")

        from app.agent.nodes.orchestrator import _generate_candidate_plans

        state = _make_state(
            step_states={"profiling": "READY"}
        )
        summary = {
            "company_name": "TestCo", "industry": "SaaS",
            "business_context": "Churn", "step_states": '{"profiling": "READY"}',
            "uploaded_files": "test.csv", "target_column": "not identified",
            "errors": "none", "session_doc": "", "denial_history": "No denials.",
            "artifact_summary": "No artifacts yet.", "available_steps": "profiling",
        }
        candidates = await _generate_candidate_plans(state, summary)

        # All candidates should have __failed__ or confidence 0.0
        valid = [
            c for c in candidates
            if c.get("next_action") != "__failed__" and c.get("confidence", 0) > 0
        ]
        assert len(valid) == 0

    @pytest.mark.asyncio
    @patch("app.agent.nodes.orchestrator.invoke_llm_json")
    async def test_partial_failure_uses_surviving(self, mock_llm):
        """When 1 of 3 candidates fails, the surviving 2 are used."""
        mock_llm.side_effect = [
            {"next_action": "profiling", "reasoning": "r1", "confidence": 0.8},
            Exception("LLM fail"),
            {"next_action": "profiling", "reasoning": "r3", "confidence": 0.7},
        ]

        from app.agent.nodes.orchestrator import _generate_candidate_plans

        state = _make_state(step_states={"profiling": "READY"})
        summary = {
            "company_name": "TestCo", "industry": "SaaS",
            "business_context": "Churn", "step_states": '{"profiling": "READY"}',
            "uploaded_files": "test.csv", "target_column": "not identified",
            "errors": "none", "session_doc": "", "denial_history": "No denials.",
            "artifact_summary": "No artifacts yet.", "available_steps": "profiling",
        }
        candidates = await _generate_candidate_plans(state, summary)

        valid = [
            c for c in candidates
            if c.get("next_action") != "__failed__" and c.get("confidence", 0) > 0
        ]
        assert len(valid) >= 2

    def test_select_best_filters_failed(self):
        """_select_best_candidate filters __failed__ markers."""
        from app.agent.nodes.orchestrator import _select_best_candidate

        state = _make_state()
        candidates = [
            {"next_action": "__failed__", "reasoning": "", "confidence": 0.0},
            {"next_action": "profiling", "reasoning": "good", "confidence": 0.8},
            {"next_action": "__failed__", "reasoning": "", "confidence": 0.0},
        ]

        result = _select_best_candidate(candidates, state)
        assert result["next_action"] == "profiling"
        assert result["confidence"] > 0

    def test_all_failed_returns_wait_not_end(self):
        """When all candidates are __failed__, returns 'wait' not 'end'."""
        from app.agent.nodes.orchestrator import _select_best_candidate

        state = _make_state()
        candidates = [
            {"next_action": "__failed__", "reasoning": "", "confidence": 0.0},
            {"next_action": "__failed__", "reasoning": "", "confidence": 0.0},
            {"next_action": "__failed__", "reasoning": "", "confidence": 0.0},
        ]

        result = _select_best_candidate(candidates, state)
        assert result["next_action"] == "wait"


class TestCotScTraceEvents:
    """Test that CoT-SC failures emit trace events."""

    @pytest.mark.asyncio
    @patch("app.agent.nodes.orchestrator.invoke_llm_json")
    async def test_failed_candidate_emits_trace(self, mock_llm):
        """Failed candidate adds a trace event."""
        mock_llm.side_effect = Exception("LLM unavailable")

        from app.agent.nodes.orchestrator import _generate_candidate_plans

        state = _make_state(step_states={"profiling": "READY"})
        summary = {
            "company_name": "TestCo", "industry": "SaaS",
            "business_context": "Churn", "step_states": '{"profiling": "READY"}',
            "uploaded_files": "test.csv", "target_column": "not identified",
            "errors": "none", "session_doc": "", "denial_history": "No denials.",
            "artifact_summary": "No artifacts yet.", "available_steps": "profiling",
        }
        await _generate_candidate_plans(state, summary)

        # Check trace events for failure
        events = state.get("trace_events", [])
        failure_events = [
            e for e in events
            if "failed" in str(e.get("payload", {})).lower()
            or e.get("event_type") == "ERROR"
        ]
        assert len(failure_events) > 0
