"""Tests for step state service."""

from __future__ import annotations

import uuid

import pytest

from app.models.session import Session
from app.services.step_state_service import (
    DEPENDENCY_GRAPH,
    DONE,
    FAILED,
    NOT_STARTED,
    READY,
    RUNNING,
    STALE,
    STEP_ORDER,
    StepStateService,
)


@pytest.fixture
async def session_with_states(db_session):
    """Create a session for testing step states."""
    session = Session(
        id=uuid.uuid4(),
        company_name="Test Corp",
        industry="Tech",
        current_step="profiling",
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)
    return session


class TestStepStateService:
    def test_initialize_states(self, db_session):
        svc = StepStateService(db_session)
        states = svc.initialize_states()
        assert states["profiling"] == READY
        assert states["merge_planning"] == NOT_STARTED
        assert states["report"] == NOT_STARTED
        assert len(states) == len(STEP_ORDER)

    def test_infer_states_from_profiling(self, db_session):
        svc = StepStateService(db_session)
        states = svc.infer_states_from_current_step("profiling")
        # DEPRECATED: prior steps marked READY (not DONE) — no completion evidence
        assert states["profiling"] == READY
        assert states["dtype_handling"] == READY
        assert states["merge_planning"] == NOT_STARTED

    def test_infer_states_from_report(self, db_session):
        svc = StepStateService(db_session)
        states = svc.infer_states_from_current_step("report")
        # DEPRECATED: all steps marked READY (not DONE) — no completion evidence
        for step in STEP_ORDER:
            assert states[step] == READY

    def test_infer_states_from_onboarding(self, db_session):
        svc = StepStateService(db_session)
        states = svc.infer_states_from_current_step("onboarding")
        assert states["profiling"] == READY

    def test_infer_states_from_unknown(self, db_session):
        svc = StepStateService(db_session)
        states = svc.infer_states_from_current_step("nonexistent")
        assert states["profiling"] == READY

    @pytest.mark.asyncio
    async def test_get_states_backward_compat(self, db_session, session_with_states):
        """When step_states is None, infer from current_step (deprecated)."""
        svc = StepStateService(db_session)
        states = await svc.get_states(session_with_states.id)
        # DEPRECATED: inferred steps are READY (not DONE) — no completion evidence
        assert states["profiling"] == READY

    @pytest.mark.asyncio
    async def test_mark_running(self, db_session, session_with_states):
        svc = StepStateService(db_session)
        # Initialize states first
        init_states = svc.initialize_states()
        await svc.update_states(session_with_states.id, init_states)

        states = await svc.mark_running(session_with_states.id, "profiling")
        assert states["profiling"] == RUNNING

    @pytest.mark.asyncio
    async def test_mark_done_unlocks_dependents(self, db_session, session_with_states):
        svc = StepStateService(db_session)
        init_states = svc.initialize_states()
        await svc.update_states(session_with_states.id, init_states)

        states = await svc.mark_done(session_with_states.id, "profiling")
        assert states["profiling"] == DONE
        assert states["dtype_handling"] == READY

    @pytest.mark.asyncio
    async def test_mark_failed(self, db_session, session_with_states):
        svc = StepStateService(db_session)
        init_states = svc.initialize_states()
        await svc.update_states(session_with_states.id, init_states)

        states = await svc.mark_failed(session_with_states.id, "profiling")
        assert states["profiling"] == FAILED

    @pytest.mark.asyncio
    async def test_invalidate_downstream(self, db_session, session_with_states):
        svc = StepStateService(db_session)
        # Set up: mark several steps as done
        states = {step: DONE for step in STEP_ORDER}
        await svc.update_states(session_with_states.id, states)

        # Invalidate from feature_selection
        result = await svc.invalidate_downstream(session_with_states.id, "feature_selection")
        assert result["feature_selection"] == READY
        assert result["eda"] == STALE
        assert result["preprocessing"] == STALE
        assert result["modeling"] == STALE
        assert result["report"] == STALE
        # Upstream should be untouched
        assert result["profiling"] == DONE
        assert result["target_id"] == DONE

    def test_get_runnable_steps(self, db_session):
        svc = StepStateService(db_session)
        states = {step: NOT_STARTED for step in STEP_ORDER}
        states["profiling"] = DONE
        states["dtype_handling"] = DONE
        states["data_understanding"] = DONE
        states["merge_planning"] = DONE
        states["opportunity_analysis"] = DONE
        states["target_id"] = DONE
        states["feature_selection"] = READY
        runnable = svc.get_runnable_steps(states)
        assert "feature_selection" in runnable
        assert len(runnable) == 1

    def test_has_running_steps(self, db_session):
        svc = StepStateService(db_session)
        states = {step: DONE for step in STEP_ORDER}
        assert not svc.has_running_steps(states)

        states["modeling"] = RUNNING
        assert svc.has_running_steps(states)

    def test_dependency_graph_complete(self):
        """Every step in STEP_ORDER has an entry in DEPENDENCY_GRAPH."""
        for step in STEP_ORDER:
            assert step in DEPENDENCY_GRAPH

    def test_feature_selection_in_step_order(self):
        """feature_selection is between target_id and eda."""
        idx_target = STEP_ORDER.index("target_id")
        idx_fs = STEP_ORDER.index("feature_selection")
        idx_eda = STEP_ORDER.index("eda")
        assert idx_target < idx_fs < idx_eda


class TestFakeCompletionPrevention:
    """Phase 9B: Verify that fake completion is prevented."""

    def test_infer_states_does_not_mark_all_prior_done(self, db_session):
        """DEPRECATED infer_states_from_current_step should NOT mark steps DONE."""
        svc = StepStateService(db_session)
        states = svc.infer_states_from_current_step("models")
        # All prior steps should be READY, not DONE
        for step in STEP_ORDER:
            assert states[step] != DONE, (
                f"Step '{step}' should not be DONE via inference — "
                "no completion evidence exists"
            )

    @pytest.mark.asyncio
    async def test_validate_completion_requires_proposal_or_artifact(
        self, db_session, session_with_states,
    ):
        """validate_completion returns False when no proposal or artifact exists."""
        svc = StepStateService(db_session)
        result = await svc.validate_completion(session_with_states.id, "eda")
        assert result is False

    @pytest.mark.asyncio
    async def test_validate_completion_returns_true_for_done_step(
        self, db_session, session_with_states,
    ):
        """validate_completion returns True when step is already DONE in states."""
        svc = StepStateService(db_session)
        states = svc.initialize_states()
        states["profiling"] = DONE
        await svc.update_states(session_with_states.id, states)
        result = await svc.validate_completion(session_with_states.id, "profiling")
        assert result is True

    @pytest.mark.asyncio
    async def test_validate_completion_true_with_approved_proposal(
        self, db_session, session_with_states,
    ):
        """validate_completion returns True when an approved proposal exists."""
        import uuid as _uuid
        from app.models.proposal import Proposal
        proposal = Proposal(
            id=_uuid.uuid4(),
            session_id=session_with_states.id,
            step="eda",
            proposal_type="eda_plan",
            status="approved",
            plan={"plots": []},
            summary="Test EDA plan",
            ai_reasoning="Test",
        )
        db_session.add(proposal)
        await db_session.commit()

        svc = StepStateService(db_session)
        result = await svc.validate_completion(session_with_states.id, "eda")
        assert result is True
