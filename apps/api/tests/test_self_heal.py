"""Tests for self-heal: denial count cycling through alternative strategies."""

from __future__ import annotations

import pytest

from app.agent.nodes.approval_helpers import (
    MAX_DENIALS,
    check_approval_phase,
    clear_approval,
    get_denial_count,
    increment_denial_count,
    mark_step_done,
    set_proposal,
    should_repropose,
)
from app.agent.state import AgentState
from app.services.step_state_service import DONE


def _make_state(**overrides) -> AgentState:
    """Create a minimal AgentState for testing."""
    state: AgentState = {
        "session_id": None,
        "current_step": "",
        "uploaded_files": [],
        "column_profiles": [],
        "step_states": {},
        "denial_counts": {},
        "pending_step": "",
        "pending_code": "",
        "pending_code_description": "",
        "approval_status": "",
        "approved_code": "",
        "next_action": "",
    }
    state.update(overrides)  # type: ignore[typeddict-item]
    return state


class TestCheckApprovalPhase:
    """Test phase detection for code-generating nodes."""

    def test_first_visit_returns_propose(self):
        state = _make_state()
        assert check_approval_phase(state, "modeling") == "propose"

    def test_approved_returns_execute(self):
        state = _make_state(pending_step="modeling", approval_status="approved")
        assert check_approval_phase(state, "modeling") == "execute"

    def test_denied_returns_denied(self):
        state = _make_state(pending_step="modeling", approval_status="denied")
        assert check_approval_phase(state, "modeling") == "denied"

    def test_pending_returns_skip(self):
        state = _make_state(pending_step="modeling", approval_status="pending")
        assert check_approval_phase(state, "modeling") == "skip"

    def test_different_step_returns_propose(self):
        state = _make_state(pending_step="eda", approval_status="approved")
        assert check_approval_phase(state, "modeling") == "propose"


class TestDenialCounts:
    """Test denial counter tracking."""

    def test_initial_count_is_zero(self):
        state = _make_state()
        assert get_denial_count(state, "modeling") == 0

    def test_increment_increases_count(self):
        state = _make_state()
        result = increment_denial_count(state, "modeling")
        assert result == 1
        assert get_denial_count(state, "modeling") == 1

    def test_multiple_increments(self):
        state = _make_state()
        increment_denial_count(state, "modeling")
        increment_denial_count(state, "modeling")
        assert get_denial_count(state, "modeling") == 2

    def test_independent_step_counts(self):
        state = _make_state()
        increment_denial_count(state, "modeling")
        increment_denial_count(state, "eda")
        increment_denial_count(state, "eda")
        assert get_denial_count(state, "modeling") == 1
        assert get_denial_count(state, "eda") == 2


class TestShouldRepropose:
    """Test the reproposal decision logic."""

    def test_should_repropose_first_denial(self):
        state = _make_state()
        assert should_repropose(state, "modeling") is True

    def test_should_repropose_under_max(self):
        state = _make_state(denial_counts={"modeling": MAX_DENIALS - 1})
        assert should_repropose(state, "modeling") is True

    def test_should_not_repropose_at_max(self):
        state = _make_state(denial_counts={"modeling": MAX_DENIALS})
        assert should_repropose(state, "modeling") is False

    def test_should_not_repropose_over_max(self):
        state = _make_state(denial_counts={"modeling": MAX_DENIALS + 1})
        assert should_repropose(state, "modeling") is False


class TestSetProposal:
    """Test proposal state setting."""

    def test_set_proposal_fields(self):
        state = _make_state()
        set_proposal(state, "modeling", "print('hello')", "Test code")
        assert state["pending_step"] == "modeling"
        assert state["pending_code"] == "print('hello')"
        assert state["pending_code_description"] == "Test code"
        assert state["next_action"] == "wait"

    def test_clear_approval_resets_fields(self):
        state = _make_state(
            pending_step="modeling",
            pending_code="x = 1",
            pending_code_description="desc",
            approval_status="approved",
            approved_code="x = 1",
        )
        clear_approval(state)
        assert state["pending_step"] == ""
        assert state["pending_code"] == ""
        assert state["pending_code_description"] == ""
        assert state["approval_status"] == ""
        assert state["approved_code"] == ""


class TestMarkStepDone:
    """Test step completion and dependency propagation."""

    def test_mark_step_done(self):
        state = _make_state(step_states={"modeling": "running"})
        mark_step_done(state, "modeling")
        assert state["step_states"]["modeling"] == DONE


class TestSelfHealWorkflow:
    """End-to-end self-heal workflow simulation."""

    def test_full_deny_repropose_cycle(self):
        """Simulate: propose → deny → repropose (×MAX_DENIALS-1) → deny → skip."""
        state = _make_state()

        # First visit: propose
        assert check_approval_phase(state, "modeling") == "propose"
        set_proposal(state, "modeling", "code v1", "desc v1")

        # Denial 1: should repropose
        state["approval_status"] = "denied"
        assert check_approval_phase(state, "modeling") == "denied"
        clear_approval(state)
        count = increment_denial_count(state, "modeling")
        assert count == 1
        assert should_repropose(state, "modeling") is True

        # Repropose with alternative
        set_proposal(state, "modeling", "code v2", "desc v2")
        assert state["pending_code"] == "code v2"

        # Denial 2: should still repropose (MAX_DENIALS=3)
        state["approval_status"] = "denied"
        assert check_approval_phase(state, "modeling") == "denied"
        clear_approval(state)
        count = increment_denial_count(state, "modeling")
        assert count == 2
        assert should_repropose(state, "modeling") is True

        # Repropose with another alternative
        set_proposal(state, "modeling", "code v3", "desc v3")
        assert state["pending_code"] == "code v3"

        # Denial 3: should NOT repropose (at MAX_DENIALS=3)
        state["approval_status"] = "denied"
        assert check_approval_phase(state, "modeling") == "denied"
        clear_approval(state)
        count = increment_denial_count(state, "modeling")
        assert count == 3
        assert should_repropose(state, "modeling") is False

        # Should skip and mark done
        mark_step_done(state, "modeling")
        assert state["step_states"]["modeling"] == DONE

    def test_approve_after_first_denial(self):
        """Simulate: propose → deny → repropose → approve → execute."""
        state = _make_state()

        # First visit: propose
        assert check_approval_phase(state, "modeling") == "propose"
        set_proposal(state, "modeling", "code v1", "desc v1")

        # Denial
        state["approval_status"] = "denied"
        assert check_approval_phase(state, "modeling") == "denied"
        clear_approval(state)
        increment_denial_count(state, "modeling")

        # Repropose
        set_proposal(state, "modeling", "code v2", "desc v2")

        # Approval
        state["approval_status"] = "approved"
        assert check_approval_phase(state, "modeling") == "execute"

        # Execute
        clear_approval(state)
        mark_step_done(state, "modeling")
        assert state["step_states"]["modeling"] == DONE
