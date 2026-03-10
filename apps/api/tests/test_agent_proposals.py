"""Tests for agent-level proposal integration.

Proves that nodes correctly create proposals, orchestrator handles
proposal states, and resume works after approval/revision.
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
from app.agent.nodes.orchestrator import _fast_path_guard
from app.services.step_state_service import DONE, READY, STEP_ORDER

pytestmark = pytest.mark.asyncio


def _make_state(**overrides):
    state = {
        "session_id": "00000000-0000-0000-0000-000000000001",
        "step_states": {s: READY for s in STEP_ORDER},
        "pending_proposal_step": "",
        "pending_proposal_plan": {},
        "pending_proposal_summary": "",
        "pending_proposal_reasoning": "",
        "pending_proposal_alternatives": [],
        "pending_proposal_type": "",
        "proposal_status": "",
        "proposal_feedback": "",
        "proposal_revision_count": {},
        "pending_step": "",
        "pending_code": "",
        "pending_code_description": "",
        "approval_status": "",
        "approved_code": "",
        "denial_counts": {},
        "awaiting_approval": None,
        "next_action": "",
        "trace_events": [],
    }
    state.update(overrides)
    return state


class TestCheckProposalPhase:
    def test_propose_when_no_pending(self):
        state = _make_state()
        assert check_proposal_phase(state, "merge_planning") == "propose"

    def test_execute_when_approved(self):
        state = _make_state(
            pending_proposal_step="merge_planning",
            proposal_status="approved",
        )
        assert check_proposal_phase(state, "merge_planning") == "execute"

    def test_revision_requested(self):
        state = _make_state(
            pending_proposal_step="eda",
            proposal_status="revision_requested",
        )
        assert check_proposal_phase(state, "eda") == "revision_requested"

    def test_rejected(self):
        state = _make_state(
            pending_proposal_step="target_id",
            proposal_status="rejected",
        )
        assert check_proposal_phase(state, "target_id") == "rejected"

    def test_skip_when_pending_no_status(self):
        state = _make_state(
            pending_proposal_step="modeling",
            proposal_status="",
        )
        assert check_proposal_phase(state, "modeling") == "skip"

    def test_different_step_returns_propose(self):
        state = _make_state(
            pending_proposal_step="eda",
            proposal_status="approved",
        )
        assert check_proposal_phase(state, "modeling") == "propose"


class TestSetBusinessProposal:
    def test_sets_all_fields(self):
        state = _make_state()
        result = set_business_proposal(
            state,
            "merge_planning",
            "merge_plan",
            {"tables": ["a", "b"]},
            "Join A and B",
            "They share a key column",
            [{"alt": "use email"}],
        )
        assert result["pending_proposal_step"] == "merge_planning"
        assert result["pending_proposal_type"] == "merge_plan"
        assert result["pending_proposal_plan"] == {"tables": ["a", "b"]}
        assert result["pending_proposal_summary"] == "Join A and B"
        assert result["pending_proposal_reasoning"] == "They share a key column"
        assert result["next_action"] == "wait"

    def test_sets_empty_alternatives_by_default(self):
        state = _make_state()
        result = set_business_proposal(
            state, "eda", "eda_plan", {}, "summary", "reasoning"
        )
        assert result["pending_proposal_alternatives"] == []


class TestClearBusinessProposal:
    def test_clears_all_fields(self):
        state = _make_state(
            pending_proposal_step="merge_planning",
            pending_proposal_plan={"foo": "bar"},
            proposal_status="approved",
            proposal_feedback="some feedback",
        )
        result = clear_business_proposal(state)
        assert result["pending_proposal_step"] == ""
        assert result["pending_proposal_plan"] == {}
        assert result["proposal_status"] == ""
        assert result["proposal_feedback"] == ""


class TestRevisionCount:
    def test_should_revise_under_limit(self):
        state = _make_state()
        assert should_revise(state, "eda") is True

    def test_should_not_revise_at_limit(self):
        state = _make_state(
            proposal_revision_count={"eda": MAX_REVISIONS}
        )
        assert should_revise(state, "eda") is False

    def test_increment_revision_count(self):
        state = _make_state()
        count = increment_revision_count(state, "eda")
        assert count == 1
        count = increment_revision_count(state, "eda")
        assert count == 2

    def test_get_proposal_feedback(self):
        state = _make_state(proposal_feedback="Use different features")
        fb = get_proposal_feedback(state, "feature_selection")
        assert fb == "Use different features"


class TestOrchestratorProposalRouting:
    def test_fast_path_proposal_approved(self):
        """When a proposal is approved, fast-path routes to that step."""
        state = _make_state(
            pending_proposal_step="merge_planning",
            proposal_status="approved",
        )
        action = _fast_path_guard(state)
        assert action == "merge_planning"

    def test_fast_path_proposal_revision(self):
        """When a proposal needs revision, fast-path routes to that step."""
        state = _make_state(
            pending_proposal_step="eda",
            proposal_status="revision_requested",
        )
        action = _fast_path_guard(state)
        assert action == "eda"

    def test_fast_path_proposal_pending(self):
        """When a proposal is pending (no status), wait."""
        state = _make_state(
            pending_proposal_step="modeling",
            proposal_status="",
        )
        action = _fast_path_guard(state)
        assert action == "wait"

    def test_fast_path_no_proposal(self):
        """No pending proposal → delegate to LLM."""
        state = _make_state()
        action = _fast_path_guard(state)
        assert action is None  # LLM decides

    def test_fast_path_all_done(self):
        """All steps done → end."""
        state = _make_state(
            step_states={s: DONE for s in STEP_ORDER},
        )
        action = _fast_path_guard(state)
        assert action == "end"
