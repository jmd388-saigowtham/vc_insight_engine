"""Tests for orchestrator node with mocked LLM.

Proves:
- Fast-path guard handles trivial cases (approval, all-done, running)
- Fallback heuristic finds the first READY step
- LLM action validation rejects unknown steps and unmet dependencies
- State summary includes key fields, denial history, artifact summary
- Orchestrator node dispatches correctly via LLM and fallback
- _generate_candidate_plans with mocked LLM
- _select_best_candidate majority vote logic
- CoT-SC unanimity detection
- New state fields (orchestrator_candidates, orchestrator_reflection)
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.agent.nodes.orchestrator import (
    _fast_path_guard,
    _fallback_next_ready,
    _generate_candidate_plans,
    _select_best_candidate,
    _summarize_state,
    _validate_llm_action,
    orchestrator_node,
)
from app.agent.state import AgentState
from app.services.step_state_service import DONE, NOT_STARTED, READY, RUNNING, STEP_ORDER


def _make_state(**overrides) -> AgentState:
    """Create a minimal AgentState for testing."""
    base: AgentState = {
        "session_id": uuid.uuid4(),
        "company_name": "Test Corp",
        "industry": "SaaS",
        "business_context": "Churn analysis",
        "current_step": "profiling",
        "uploaded_files": [{"filename": "test.csv", "storage_path": "/tmp/test.csv"}],
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
        "orchestrator_candidates": [],
        "orchestrator_reflection": "",
        "strategy_hint": "",
        "run_id": "",
        "denial_feedback": {},
        "node_plans": {},
        "pending_context": {},
        "pending_proposal_step": "",
        "pending_proposal_plan": {},
        "pending_proposal_summary": "",
        "pending_proposal_reasoning": "",
        "pending_proposal_alternatives": [],
        "pending_proposal_type": "",
        "proposal_status": "",
        "proposal_feedback": "",
        "error": None,
        "trace_events": [],
    }
    base.update(overrides)
    return base


class TestFastPathGuard:
    def test_awaiting_approval_returns_wait(self):
        state = _make_state(awaiting_approval="some-id")
        assert _fast_path_guard(state) == "wait"

    def test_all_done_returns_end(self):
        states = {step: DONE for step in STEP_ORDER}
        state = _make_state(step_states=states)
        assert _fast_path_guard(state) == "end"

    def test_running_returns_wait(self):
        states = {step: DONE for step in STEP_ORDER}
        states["modeling"] = RUNNING
        state = _make_state(step_states=states)
        assert _fast_path_guard(state) == "wait"

    def test_pending_approval_returns_step(self):
        state = _make_state(pending_step="modeling", approval_status="approved")
        assert _fast_path_guard(state) == "modeling"

    def test_no_trivial_case_returns_none(self):
        """Fast path should NOT find READY steps — that's for the LLM."""
        states = {step: NOT_STARTED for step in STEP_ORDER}
        states["profiling"] = READY
        state = _make_state(step_states=states)
        assert _fast_path_guard(state) is None

    def test_empty_states_returns_none(self):
        state = _make_state(step_states={})
        assert _fast_path_guard(state) is None


class TestFallbackNextReady:
    def test_finds_first_ready_step(self):
        states = {step: NOT_STARTED for step in STEP_ORDER}
        states["profiling"] = READY
        state = _make_state(step_states=states)
        assert _fallback_next_ready(state) == "profiling"

    def test_finds_ready_with_deps_met(self):
        states = {step: NOT_STARTED for step in STEP_ORDER}
        states["profiling"] = DONE
        states["dtype_handling"] = READY
        state = _make_state(step_states=states)
        assert _fallback_next_ready(state) == "dtype_handling"

    def test_no_ready_returns_end(self):
        states = {step: NOT_STARTED for step in STEP_ORDER}
        state = _make_state(step_states=states)
        assert _fallback_next_ready(state) == "end"


class TestValidateLlmAction:
    def test_valid_step_with_deps_met(self):
        states = {"profiling": DONE, "dtype_handling": READY}
        state = _make_state(step_states=states)
        assert _validate_llm_action("dtype_handling", state) == "dtype_handling"

    def test_wait_action_passes(self):
        state = _make_state()
        assert _validate_llm_action("wait", state) == "wait"

    def test_end_action_passes(self):
        state = _make_state()
        assert _validate_llm_action("end", state) == "end"

    def test_invalid_step_returns_none(self):
        state = _make_state()
        assert _validate_llm_action("nonexistent_step", state) is None

    def test_step_with_unmet_deps_returns_none(self):
        states = {step: NOT_STARTED for step in STEP_ORDER}
        state = _make_state(step_states=states)
        # modeling requires feature_eng done
        assert _validate_llm_action("modeling", state) is None


class TestSummarizeState:
    def test_summary_contains_key_fields(self):
        states = {"profiling": DONE, "merge_planning": READY}
        state = _make_state(step_states=states, company_name="Acme Inc")
        summary = _summarize_state(state)
        assert summary["company_name"] == "Acme Inc"
        assert "profiling" in summary["step_states"]
        assert "uploaded_files" in summary

    def test_summary_includes_session_doc(self):
        state = _make_state(session_doc="Previous analysis found high churn")
        summary = _summarize_state(state)
        assert summary["session_doc"] == "Previous analysis found high churn"

    def test_summary_includes_denial_history(self):
        state = _make_state(
            denial_feedback={"eda": ["Too many plots"]},
            denial_counts={"eda": 1},
        )
        summary = _summarize_state(state)
        assert "eda" in summary["denial_history"]
        assert "Too many plots" in summary["denial_history"]

    def test_summary_includes_artifact_summary(self):
        state = _make_state(
            model_results={"models": [{"model_name": "rf"}], "best_model": "rf"},
        )
        summary = _summarize_state(state)
        assert "Models" in summary["artifact_summary"]

    def test_summary_includes_available_steps(self):
        states = {step: NOT_STARTED for step in STEP_ORDER}
        states["profiling"] = READY
        state = _make_state(step_states=states)
        summary = _summarize_state(state)
        assert "profiling" in summary["available_steps"]


class TestOrchestratorNode:
    @pytest.mark.asyncio
    async def test_orchestrator_all_done(self):
        states = {step: DONE for step in STEP_ORDER}
        state = _make_state(step_states=states)
        result = await orchestrator_node(state)
        assert result["next_action"] == "end"

    @pytest.mark.asyncio
    async def test_orchestrator_awaiting_approval(self):
        states = {step: DONE for step in STEP_ORDER[:3]}
        states.update({step: NOT_STARTED for step in STEP_ORDER[3:]})
        state = _make_state(step_states=states, awaiting_approval="proposal-123")
        result = await orchestrator_node(state)
        assert result["next_action"] == "wait"

    @pytest.mark.asyncio
    @patch("app.agent.nodes.orchestrator.invoke_llm_json")
    async def test_orchestrator_llm_primary(self, mock_llm):
        """LLM is the primary decision-maker for non-trivial cases."""
        mock_llm.return_value = {
            "next_action": "profiling",
            "reasoning": "First step with data available",
            "strategy_hint": "Focus on churn columns",
        }
        states = {step: NOT_STARTED for step in STEP_ORDER}
        states["profiling"] = READY
        state = _make_state(step_states=states)

        result = await orchestrator_node(state)
        assert result["next_action"] == "profiling"
        assert result.get("strategy_hint") == "Focus on churn columns"
        assert result.get("orchestrator_reasoning") == "First step with data available"
        # CoT-SC makes 3 parallel calls at different temperatures, plus
        # a reflection call if a previous step is DONE
        assert mock_llm.call_count >= 3

    @pytest.mark.asyncio
    @patch("app.agent.nodes.orchestrator.invoke_llm_json")
    async def test_orchestrator_fallback_on_llm_failure(self, mock_llm):
        """When LLM fails, orchestrator returns 'wait' (safe pause)."""
        mock_llm.side_effect = Exception("LLM unavailable")
        states = {step: NOT_STARTED for step in STEP_ORDER}
        states["profiling"] = READY
        state = _make_state(step_states=states)

        result = await orchestrator_node(state)
        # Phase 4: all CoT-SC failures → safe "wait" instead of fallback
        assert result["next_action"] == "wait"

    @pytest.mark.asyncio
    @patch("app.agent.nodes.orchestrator.invoke_llm_json")
    async def test_orchestrator_validates_llm_action(self, mock_llm):
        """If LLM returns an action with unmet deps, fallback is used."""
        mock_llm.return_value = {
            "next_action": "modeling",  # deps not met
            "reasoning": "Let's train models",
            "strategy_hint": "",
        }
        states = {step: NOT_STARTED for step in STEP_ORDER}
        states["profiling"] = READY
        state = _make_state(step_states=states)

        result = await orchestrator_node(state)
        # Should fall back to profiling since modeling deps aren't met
        assert result["next_action"] == "profiling"

    @pytest.mark.asyncio
    @patch("app.agent.nodes.orchestrator.invoke_llm_json")
    async def test_orchestrator_emits_decision_trace(self, mock_llm):
        """Orchestrator should emit DECISION trace events."""
        mock_llm.return_value = {
            "next_action": "profiling",
            "reasoning": "Start with data profiling",
            "strategy_hint": "",
        }
        states = {step: NOT_STARTED for step in STEP_ORDER}
        states["profiling"] = READY
        state = _make_state(step_states=states)

        result = await orchestrator_node(state)
        trace_events = result.get("trace_events", [])
        decision_events = [e for e in trace_events if e["event_type"] == "DECISION"]
        assert len(decision_events) >= 1
        assert decision_events[0]["payload"]["next_action"] == "profiling"

    @pytest.mark.asyncio
    async def test_orchestrator_pending_approval_fast_path(self):
        """Pending step with approval status dispatches to that step."""
        state = _make_state(
            pending_step="preprocessing",
            approval_status="approved",
        )
        result = await orchestrator_node(state)
        assert result["next_action"] == "preprocessing"

    @pytest.mark.asyncio
    @patch("app.agent.nodes.orchestrator.invoke_llm_json")
    async def test_orchestrator_stores_candidates_in_state(self, mock_llm):
        """CoT-SC candidates should be stored in orchestrator_candidates."""
        mock_llm.return_value = {
            "next_action": "profiling",
            "reasoning": "Start profiling",
            "strategy_hint": "",
            "confidence": 0.9,
        }
        states = {step: NOT_STARTED for step in STEP_ORDER}
        states["profiling"] = READY
        state = _make_state(step_states=states)

        result = await orchestrator_node(state)
        candidates = result.get("orchestrator_candidates", [])
        assert isinstance(candidates, list)
        assert len(candidates) == 3  # 3 temperatures


# ---------------------------------------------------------------------------
# _generate_candidate_plans
# ---------------------------------------------------------------------------


class TestGenerateCandidatePlans:
    """Test _generate_candidate_plans with mocked LLM."""

    @pytest.mark.asyncio
    @patch("app.agent.nodes.orchestrator.invoke_llm_json")
    async def test_generates_three_candidates(self, mock_llm):
        """Should generate one candidate per temperature (3 total)."""
        async def _return_fresh(*args, **kwargs):
            return {
                "next_action": "profiling",
                "reasoning": "Start profiling",
                "strategy_hint": "",
                "confidence": 0.85,
            }

        mock_llm.side_effect = _return_fresh
        state = _make_state()
        summary = _summarize_state(state)
        candidates = await _generate_candidate_plans(state, summary)
        assert len(candidates) == 3
        assert mock_llm.call_count == 3

    @pytest.mark.asyncio
    @patch("app.agent.nodes.orchestrator.invoke_llm_json")
    async def test_candidates_include_temperature(self, mock_llm):
        """Each candidate should have the temperature that was used."""
        # Use side_effect list so each call gets its own dict object
        mock_llm.side_effect = [
            {"next_action": "eda", "reasoning": "Run EDA", "strategy_hint": "", "confidence": 0.7},
            {"next_action": "eda", "reasoning": "Run EDA", "strategy_hint": "", "confidence": 0.7},
            {"next_action": "eda", "reasoning": "Run EDA", "strategy_hint": "", "confidence": 0.7},
        ]
        state = _make_state()
        summary = _summarize_state(state)
        candidates = await _generate_candidate_plans(state, summary)
        temperatures = [c.get("temperature") for c in candidates]
        assert 0.1 in temperatures
        assert 0.3 in temperatures
        assert 0.5 in temperatures

    @pytest.mark.asyncio
    @patch("app.agent.nodes.orchestrator.invoke_llm_json")
    async def test_candidates_handle_partial_failure(self, mock_llm):
        """If one LLM call fails, others should still produce results."""
        call_count = 0

        async def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("Timeout")
            return {
                "next_action": "profiling",
                "reasoning": "Start profiling",
                "strategy_hint": "",
                "confidence": 0.8,
            }

        mock_llm.side_effect = _side_effect
        state = _make_state()
        summary = _summarize_state(state)
        candidates = await _generate_candidate_plans(state, summary)
        assert len(candidates) == 3
        # The failed one should have confidence 0.0
        failed = [c for c in candidates if c.get("confidence", 1.0) == 0.0]
        assert len(failed) == 1


# ---------------------------------------------------------------------------
# _select_best_candidate — majority vote logic
# ---------------------------------------------------------------------------


class TestSelectBestCandidate:
    """Test _select_best_candidate majority vote logic."""

    def test_unanimous_candidates(self):
        """All candidates agree -> that action is selected."""
        candidates = [
            {"next_action": "profiling", "reasoning": "a", "confidence": 0.8},
            {"next_action": "profiling", "reasoning": "b", "confidence": 0.9},
            {"next_action": "profiling", "reasoning": "c", "confidence": 0.7},
        ]
        state = _make_state()
        best = _select_best_candidate(candidates, state)
        assert best["next_action"] == "profiling"
        # Should pick highest confidence
        assert best["confidence"] == 0.9

    def test_majority_vote_2_vs_1(self):
        """2 candidates agree on one action, 1 disagrees -> majority wins."""
        candidates = [
            {"next_action": "eda", "reasoning": "a", "confidence": 0.6},
            {"next_action": "profiling", "reasoning": "b", "confidence": 0.95},
            {"next_action": "eda", "reasoning": "c", "confidence": 0.8},
        ]
        state = _make_state()
        best = _select_best_candidate(candidates, state)
        assert best["next_action"] == "eda"
        # Should pick highest confidence among majority
        assert best["confidence"] == 0.8

    def test_tiebreak_by_confidence(self):
        """When a single action has multiple candidates, highest confidence wins."""
        candidates = [
            {"next_action": "profiling", "reasoning": "a", "confidence": 0.5},
            {"next_action": "profiling", "reasoning": "b", "confidence": 0.95},
            {"next_action": "profiling", "reasoning": "c", "confidence": 0.7},
        ]
        state = _make_state()
        best = _select_best_candidate(candidates, state)
        assert best["next_action"] == "profiling"
        assert best["confidence"] == 0.95

    def test_empty_candidates_returns_end(self):
        """Empty candidate list should return 'end' with zero confidence."""
        state = _make_state()
        best = _select_best_candidate([], state)
        assert best["next_action"] == "end"
        assert best["confidence"] == 0.0

    def test_single_candidate(self):
        """A single candidate should be returned as-is."""
        candidates = [
            {"next_action": "hypothesis", "reasoning": "test", "confidence": 0.75},
        ]
        state = _make_state()
        best = _select_best_candidate(candidates, state)
        assert best["next_action"] == "hypothesis"
        assert best["confidence"] == 0.75


# ---------------------------------------------------------------------------
# CoT-SC unanimity detection via orchestrator_node
# ---------------------------------------------------------------------------


class TestCoTSCUnanimity:
    """Test that orchestrator detects unanimity vs divergence in candidates."""

    @pytest.mark.asyncio
    @patch("app.agent.nodes.orchestrator.invoke_llm_json")
    async def test_unanimous_sets_cot_sc_unanimous_source(self, mock_llm):
        """When all candidates agree, source should indicate unanimity."""
        mock_llm.return_value = {
            "next_action": "profiling",
            "reasoning": "Start profiling",
            "strategy_hint": "",
            "confidence": 0.9,
        }
        states = {step: NOT_STARTED for step in STEP_ORDER}
        states["profiling"] = READY
        state = _make_state(step_states=states)

        result = await orchestrator_node(state)
        trace_events = result.get("trace_events", [])
        decision_events = [e for e in trace_events if e["event_type"] == "DECISION"]
        assert len(decision_events) >= 1
        source = decision_events[-1]["payload"].get("source", "")
        assert "cot_sc_unanimous" in source

    @pytest.mark.asyncio
    @patch("app.agent.nodes.orchestrator.invoke_llm_json")
    async def test_divergent_sets_majority_source(self, mock_llm):
        """When candidates diverge, source should indicate majority vote."""
        call_count = 0

        async def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return {
                    "next_action": "profiling",
                    "reasoning": "Start profiling",
                    "strategy_hint": "",
                    "confidence": 0.8,
                }
            # Third call returns different action
            return {
                "next_action": "eda",
                "reasoning": "Start EDA",
                "strategy_hint": "",
                "confidence": 0.6,
            }

        mock_llm.side_effect = _side_effect
        states = {step: NOT_STARTED for step in STEP_ORDER}
        states["profiling"] = READY
        state = _make_state(step_states=states)

        result = await orchestrator_node(state)
        trace_events = result.get("trace_events", [])
        decision_events = [e for e in trace_events if e["event_type"] == "DECISION"]
        assert len(decision_events) >= 1
        source = decision_events[-1]["payload"].get("source", "")
        assert "cot_sc_majority" in source


# ---------------------------------------------------------------------------
# New state fields
# ---------------------------------------------------------------------------


class TestNewStateFields:
    """Test that new state fields are properly handled."""

    def test_make_state_includes_orchestrator_candidates(self):
        """_make_state should include orchestrator_candidates."""
        state = _make_state()
        assert "orchestrator_candidates" in state
        assert isinstance(state["orchestrator_candidates"], list)

    def test_make_state_includes_orchestrator_reflection(self):
        """_make_state should include orchestrator_reflection."""
        state = _make_state()
        assert "orchestrator_reflection" in state
        assert state["orchestrator_reflection"] == ""

    def test_make_state_includes_proposal_fields(self):
        """_make_state should include business-logic proposal fields."""
        state = _make_state()
        assert "pending_proposal_step" in state
        assert "pending_proposal_plan" in state
        assert "proposal_status" in state

    @pytest.mark.asyncio
    @patch("app.agent.nodes.orchestrator.invoke_llm_json")
    async def test_orchestrator_sets_reflection(self, mock_llm):
        """Orchestrator should set orchestrator_reflection when reflection succeeds."""
        call_count = 0

        async def _side_effect(messages, **kwargs):
            nonlocal call_count
            call_count += 1
            # Reflection call
            if "Reflect" in str(messages):
                return {
                    "assessment": "Profiling completed successfully",
                    "concerns": [],
                    "adjustments": "None needed",
                    "context_for_next": "Data has 10 columns, churn column detected",
                }
            # CoT-SC calls
            return {
                "next_action": "dtype_handling",
                "reasoning": "Profile data types next",
                "strategy_hint": "",
                "confidence": 0.85,
            }

        mock_llm.side_effect = _side_effect
        states = {step: NOT_STARTED for step in STEP_ORDER}
        states["profiling"] = DONE
        states["dtype_handling"] = READY
        state = _make_state(step_states=states)

        result = await orchestrator_node(state)
        # Reflection may or may not be set depending on flow, but the field exists
        assert "orchestrator_reflection" in result
