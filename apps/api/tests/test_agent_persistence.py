"""Tests for agent result persistence — Phase 2.

Verifies that:
- Session.current_step advances based on furthest DONE pipeline step
- current_step only advances, never regresses
- target_column is persisted to Session DB
- selected_features is persisted to Session DB
"""

import uuid

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.models.session import Session
from app.services.step_state_service import DONE, NOT_STARTED, READY, STEP_ORDER


def _make_state(**overrides):
    """Create minimal AgentState for testing."""
    base = {
        "session_id": None,
        "step_states": {step: NOT_STARTED for step in STEP_ORDER},
        "target_column": "",
        "selected_features": [],
        "trace_events": [],
        "error": None,
        "merged_df_path": "",
        "merge_plan": {},
        "cleaned_df_path": "",
        "features_df_path": "",
    }
    base.update(overrides)
    return base


@pytest.fixture
async def test_session(db_session):
    """Create a test session in the DB."""
    session_id = uuid.uuid4()
    session = Session(
        id=session_id,
        company_name="Test Corp",
        industry="SaaS",
        current_step="onboarding",
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)
    return session


class TestAdvanceCurrentStep:
    """_advance_current_step maps pipeline steps to UI steps and advances."""

    @pytest.mark.asyncio
    async def test_advances_after_profiling_done(self, db_session, test_session):
        from app.services.agent_service import AgentService
        event_service = MagicMock()
        event_service.emit = AsyncMock()
        svc = AgentService(db_session, event_service)

        state = _make_state(session_id=test_session.id)
        state["step_states"]["profiling"] = DONE

        await svc._advance_current_step(test_session.id, state)

        await db_session.refresh(test_session)
        assert test_session.current_step == "profiling"

    @pytest.mark.asyncio
    async def test_advances_after_target_id_done(self, db_session, test_session):
        from app.services.agent_service import AgentService
        event_service = MagicMock()
        event_service.emit = AsyncMock()
        svc = AgentService(db_session, event_service)

        state = _make_state(session_id=test_session.id)
        # Mark several steps done up to target_id
        for step in ["profiling", "dtype_handling", "data_understanding",
                      "merge_planning", "opportunity_analysis", "target_id"]:
            state["step_states"][step] = DONE

        await svc._advance_current_step(test_session.id, state)

        await db_session.refresh(test_session)
        assert test_session.current_step == "target"

    @pytest.mark.asyncio
    async def test_never_regresses(self, db_session, test_session):
        from app.services.agent_service import AgentService
        event_service = MagicMock()
        event_service.emit = AsyncMock()
        svc = AgentService(db_session, event_service)

        # Set current_step to "target" first
        test_session.current_step = "target"
        await db_session.commit()

        # Now run with only profiling done — should NOT regress
        state = _make_state(session_id=test_session.id)
        state["step_states"]["profiling"] = DONE

        await svc._advance_current_step(test_session.id, state)

        await db_session.refresh(test_session)
        assert test_session.current_step == "target"  # No regression

    @pytest.mark.asyncio
    async def test_no_done_steps_no_change(self, db_session, test_session):
        from app.services.agent_service import AgentService
        event_service = MagicMock()
        event_service.emit = AsyncMock()
        svc = AgentService(db_session, event_service)

        state = _make_state(session_id=test_session.id)
        # No steps are DONE

        await svc._advance_current_step(test_session.id, state)

        await db_session.refresh(test_session)
        assert test_session.current_step == "onboarding"  # Unchanged


class TestPersistSessionFields:
    """_persist_session_fields writes target_column and selected_features."""

    @pytest.mark.asyncio
    async def test_persists_target_column(self, db_session, test_session):
        from app.services.agent_service import AgentService
        event_service = MagicMock()
        event_service.emit = AsyncMock()
        svc = AgentService(db_session, event_service)

        state = _make_state(session_id=test_session.id)
        state["target_column"] = "Churn"

        await svc._persist_session_fields(test_session.id, state)

        await db_session.refresh(test_session)
        assert test_session.target_column == "Churn"

    @pytest.mark.asyncio
    async def test_persists_selected_features(self, db_session, test_session):
        from app.services.agent_service import AgentService
        event_service = MagicMock()
        event_service.emit = AsyncMock()
        svc = AgentService(db_session, event_service)

        state = _make_state(session_id=test_session.id)
        state["selected_features"] = ["revenue", "tenure", "support_calls"]

        await svc._persist_session_fields(test_session.id, state)

        await db_session.refresh(test_session)
        assert test_session.selected_features == ["revenue", "tenure", "support_calls"]

    @pytest.mark.asyncio
    async def test_no_change_when_empty(self, db_session, test_session):
        from app.services.agent_service import AgentService
        event_service = MagicMock()
        event_service.emit = AsyncMock()
        svc = AgentService(db_session, event_service)

        # Pre-set target
        test_session.target_column = "Churn"
        await db_session.commit()

        state = _make_state(session_id=test_session.id)
        state["target_column"] = ""  # Empty — should not overwrite
        state["selected_features"] = []  # Empty — should not overwrite

        await svc._persist_session_fields(test_session.id, state)

        await db_session.refresh(test_session)
        assert test_session.target_column == "Churn"  # Unchanged

    @pytest.mark.asyncio
    async def test_target_survives_rebuild(self, db_session, test_session):
        """Verify that target_column set in DB survives state rebuild."""
        from app.services.agent_service import AgentService
        event_service = MagicMock()
        event_service.emit = AsyncMock()
        svc = AgentService(db_session, event_service)

        # Set target in DB
        test_session.target_column = "Churn"
        test_session.current_step = "target"
        await db_session.commit()

        # Rebuild state from DB (simulating restart)
        state = await svc._build_initial_state(test_session.id)
        assert state["target_column"] == "Churn"
