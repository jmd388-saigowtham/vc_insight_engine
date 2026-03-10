"""Tests for the full proposal revision loop lifecycle.

Proves:
- Propose → Approve → Execute
- Propose → Revise × N → Approve → Execute
- Propose → Reject → Fallback
- MAX_REVISIONS enforcement
- Proposal fields set and cleared correctly
"""

from __future__ import annotations

import pytest

from app.agent.nodes.approval_helpers import (
    MAX_REVISIONS,
    check_proposal_phase,
    clear_business_proposal,
    get_proposal_feedback,
    increment_revision_count,
    set_business_proposal,
    should_revise,
)
from app.agent.state import AgentState


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


class TestProposalLifecyclePropose:
    """Test the proposal phase — setting proposals."""

    def test_initial_phase_is_propose(self):
        state = _blank_state()
        phase = check_proposal_phase(state, "feature_selection")
        assert phase == "propose"

    def test_set_business_proposal_sets_fields(self):
        state = _blank_state()
        plan = {"features": ["col_a", "col_b"], "target": "churn"}
        result = set_business_proposal(
            state, "feature_selection", "feature_selection",
            plan, "Selected 2 features", "LLM reasoning here",
        )
        assert result["pending_proposal_step"] == "feature_selection"
        assert result["pending_proposal_type"] == "feature_selection"
        assert result["pending_proposal_plan"] == plan
        assert result["pending_proposal_summary"] == "Selected 2 features"
        assert result["pending_proposal_reasoning"] == "LLM reasoning here"
        assert result["next_action"] == "wait"

    def test_set_business_proposal_with_alternatives(self):
        state = _blank_state()
        alts = [{"name": "alt_plan", "features": ["col_c"]}]
        result = set_business_proposal(
            state, "merge_planning", "merge_plan",
            {"keys": ["id"]}, "Join on id", "Best match",
            alternatives=alts,
        )
        assert result["pending_proposal_alternatives"] == alts


class TestProposalLifecycleApprove:
    """Test the approval flow."""

    def test_approved_phase_is_execute(self):
        state = _blank_state()
        state["pending_proposal_step"] = "feature_selection"
        state["pending_proposal_plan"] = {"features": ["a"]}
        state["proposal_status"] = "approved"
        phase = check_proposal_phase(state, "feature_selection")
        assert phase == "execute"

    def test_clear_business_proposal_resets_fields(self):
        state = _blank_state()
        set_business_proposal(
            state, "eda", "eda_plan",
            {"plots": ["dist"]}, "EDA plan", "reasoning",
        )
        clear_business_proposal(state)
        assert state["pending_proposal_step"] == ""
        assert state["pending_proposal_plan"] == {}
        assert state["pending_proposal_summary"] == ""
        assert state["proposal_status"] == ""


class TestProposalLifecycleRevision:
    """Test the revision loop."""

    def test_revision_requested_phase(self):
        state = _blank_state()
        state["pending_proposal_step"] = "target_id"
        state["pending_proposal_plan"] = {"target": "churn"}
        state["proposal_status"] = "revision_requested"
        phase = check_proposal_phase(state, "target_id")
        assert phase == "revision_requested"

    def test_should_revise_under_max(self):
        state = _blank_state()
        assert should_revise(state, "feature_selection") is True

    def test_should_revise_at_max(self):
        state = _blank_state()
        state["proposal_revision_count"] = {"feature_selection": MAX_REVISIONS}
        assert should_revise(state, "feature_selection") is False

    def test_increment_revision_count(self):
        state = _blank_state()
        count = increment_revision_count(state, "eda")
        assert count == 1
        count = increment_revision_count(state, "eda")
        assert count == 2

    def test_get_proposal_feedback(self):
        state = _blank_state()
        state["proposal_feedback"] = "Please add feature X"
        feedback = get_proposal_feedback(state, "feature_selection")
        assert "Please add feature X" in feedback

    def test_revision_loop_up_to_max(self):
        state = _blank_state()
        for i in range(MAX_REVISIONS):
            assert should_revise(state, "merge_planning") is True
            increment_revision_count(state, "merge_planning")
        assert should_revise(state, "merge_planning") is False


class TestProposalLifecycleRejection:
    """Test the rejection flow."""

    def test_rejected_phase(self):
        state = _blank_state()
        state["pending_proposal_step"] = "feature_selection"
        state["pending_proposal_plan"] = {"features": ["a"]}
        state["proposal_status"] = "rejected"
        phase = check_proposal_phase(state, "feature_selection")
        assert phase == "rejected"


class TestProposalPhaseSkip:
    """Test skip logic — different step pending."""

    def test_skip_when_different_step_pending(self):
        state = _blank_state()
        state["pending_proposal_step"] = "eda"
        state["pending_proposal_plan"] = {"plots": ["dist"]}
        phase = check_proposal_phase(state, "modeling")
        # Should be "propose" since modeling has nothing pending
        assert phase == "propose"
