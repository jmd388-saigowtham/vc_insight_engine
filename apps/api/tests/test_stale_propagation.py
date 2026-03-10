"""Tests for stale propagation — upstream changes mark downstream STALE.

Proves:
- invalidate_downstream marks all downstream steps STALE via BFS
- Source step is marked READY for re-run
- Upstream steps remain DONE
- Dependency graph is correctly configured
- Step state transitions are valid
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import Session
from app.services.step_state_service import (
    DEPENDENCY_GRAPH,
    STEP_ORDER,
    StepStateService,
)


async def _create_test_session(db: AsyncSession) -> uuid.UUID:
    session_id = uuid.uuid4()
    session = Session(id=session_id, company_name="Stale Test Corp")
    db.add(session)
    await db.commit()
    return session_id


class TestDependencyGraph:
    """Test the dependency graph structure."""

    def test_all_steps_in_graph(self):
        """Every step in STEP_ORDER should have a DEPENDENCY_GRAPH entry."""
        for step in STEP_ORDER:
            assert step in DEPENDENCY_GRAPH, f"Step {step} missing from DEPENDENCY_GRAPH"

    def test_profiling_has_no_deps(self):
        assert DEPENDENCY_GRAPH["profiling"] == []

    def test_modeling_depends_on_feature_eng_and_hypothesis(self):
        deps = DEPENDENCY_GRAPH["modeling"]
        assert "feature_eng" in deps
        assert "hypothesis" in deps

    def test_report_depends_on_recommendation(self):
        deps = DEPENDENCY_GRAPH["report"]
        assert "recommendation" in deps

    def test_no_circular_dependencies(self):
        """Verify no circular dependencies by performing topological sort."""
        visited: set[str] = set()
        visiting: set[str] = set()

        def dfs(step: str):
            if step in visiting:
                raise ValueError(f"Circular dependency detected at {step}")
            if step in visited:
                return
            visiting.add(step)
            for dep in DEPENDENCY_GRAPH.get(step, []):
                dfs(dep)
            visiting.remove(step)
            visited.add(step)

        for step in STEP_ORDER:
            dfs(step)
        # If we get here without error, no cycles


class TestStaleInvalidation:
    """Test stale propagation via invalidate_downstream."""

    @pytest.mark.asyncio
    async def test_invalidate_from_profiling(self, db_session: AsyncSession):
        """Invalidating profiling should mark everything downstream STALE."""
        session_id = await _create_test_session(db_session)
        svc = StepStateService(db_session)

        # Set all steps to DONE
        states = {step: "DONE" for step in STEP_ORDER}
        await svc.update_states(session_id, states)

        new_states = await svc.invalidate_downstream(session_id, "profiling")

        # profiling itself should be READY
        assert new_states["profiling"] == "READY"

        # Everything after profiling should be STALE
        prof_idx = STEP_ORDER.index("profiling")
        for step in STEP_ORDER[prof_idx + 1:]:
            assert new_states[step] == "STALE", f"Expected {step} to be STALE"

    @pytest.mark.asyncio
    async def test_invalidate_from_modeling(self, db_session: AsyncSession):
        """Invalidating modeling should only affect downstream steps."""
        session_id = await _create_test_session(db_session)
        svc = StepStateService(db_session)

        states = {step: "DONE" for step in STEP_ORDER}
        await svc.update_states(session_id, states)

        new_states = await svc.invalidate_downstream(session_id, "modeling")

        # modeling should be READY
        assert new_states["modeling"] == "READY"

        # Steps before modeling should remain DONE
        model_idx = STEP_ORDER.index("modeling")
        for step in STEP_ORDER[:model_idx]:
            assert new_states[step] == "DONE", f"Expected {step} to still be DONE"

        # Steps after modeling should be STALE
        downstream_after_modeling = [
            s for s in STEP_ORDER[model_idx + 1:]
        ]
        for step in downstream_after_modeling:
            assert new_states[step] == "STALE", f"Expected {step} to be STALE"

    @pytest.mark.asyncio
    async def test_invalidate_last_step(self, db_session: AsyncSession):
        """Invalidating the last step (report) has minimal effect."""
        session_id = await _create_test_session(db_session)
        svc = StepStateService(db_session)

        states = {step: "DONE" for step in STEP_ORDER}
        await svc.update_states(session_id, states)

        new_states = await svc.invalidate_downstream(session_id, "report")

        # report should be READY
        assert new_states["report"] == "READY"

        # All other steps should remain DONE
        for step in STEP_ORDER[:-1]:
            assert new_states[step] == "DONE"


class TestStepStateTransitions:
    """Test valid state transitions."""

    @pytest.mark.asyncio
    async def test_mark_running(self, db_session: AsyncSession):
        session_id = await _create_test_session(db_session)
        svc = StepStateService(db_session)

        states = svc.initialize_states()
        await svc.update_states(session_id, states)

        new_states = await svc.mark_running(session_id, "profiling")
        assert new_states["profiling"] == "RUNNING"

    @pytest.mark.asyncio
    async def test_mark_done_enables_dependents(self, db_session: AsyncSession):
        session_id = await _create_test_session(db_session)
        svc = StepStateService(db_session)

        states = svc.initialize_states()
        await svc.update_states(session_id, states)

        new_states = await svc.mark_done(session_id, "profiling")
        assert new_states["profiling"] == "DONE"
        # dtype_handling depends on profiling — should be READY now
        assert new_states["dtype_handling"] == "READY"

    @pytest.mark.asyncio
    async def test_mark_failed(self, db_session: AsyncSession):
        session_id = await _create_test_session(db_session)
        svc = StepStateService(db_session)

        states = svc.initialize_states()
        await svc.update_states(session_id, states)

        new_states = await svc.mark_failed(session_id, "profiling")
        assert new_states["profiling"] == "FAILED"

    @pytest.mark.asyncio
    async def test_runnable_steps_after_init(self, db_session: AsyncSession):
        """After initialization, only profiling should be runnable."""
        svc = StepStateService(db_session)
        states = svc.initialize_states()
        runnable = svc.get_runnable_steps(states)
        assert "profiling" in runnable

    @pytest.mark.asyncio
    async def test_has_running_steps(self, db_session: AsyncSession):
        svc = StepStateService(db_session)
        states = svc.initialize_states()
        assert svc.has_running_steps(states) is False

        states["profiling"] = "RUNNING"
        assert svc.has_running_steps(states) is True
