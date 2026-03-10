"""Step state management with dependency graph and invalidation.

Replaces the old high-water-mark step regression guard with a proper
DAG-based state machine that supports go-back-and-edit workflows.
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import Session
from app.schemas.event import TraceEventCreate
from app.services.event_service import EventService

logger = structlog.get_logger()


# Step states
NOT_STARTED = "NOT_STARTED"
READY = "READY"
RUNNING = "RUNNING"
DONE = "DONE"
STALE = "STALE"
FAILED = "FAILED"

VALID_STATES = {NOT_STARTED, READY, RUNNING, DONE, STALE, FAILED}

# Canonical step order (full agentic pipeline)
STEP_ORDER = [
    "profiling",
    "dtype_handling",
    "data_understanding",
    "merge_planning",
    "opportunity_analysis",
    "target_id",
    "feature_selection",
    "eda",
    "preprocessing",
    "hypothesis",
    "feature_eng",
    "modeling",
    "threshold_calibration",
    "explainability",
    "recommendation",
    "report",
]

# UI step order (includes non-pipeline UI steps)
UI_STEP_ORDER = [
    "onboarding",
    "upload",
    "profiling",
    "workspace",
    "target",
    "feature-selection",
    "eda",
    "hypotheses",
    "hypothesis-results",
    "models",
    "shap",
    "report",
]

# Dependency graph: each step depends on these preceding steps
DEPENDENCY_GRAPH: dict[str, list[str]] = {
    "profiling": [],
    "dtype_handling": ["profiling"],
    "data_understanding": ["dtype_handling"],
    "merge_planning": ["data_understanding"],
    "opportunity_analysis": ["merge_planning"],
    "target_id": ["opportunity_analysis"],
    "feature_selection": ["target_id", "profiling"],
    "eda": ["feature_selection"],
    "preprocessing": ["feature_selection"],
    "hypothesis": ["eda", "preprocessing"],
    "feature_eng": ["preprocessing"],
    "modeling": ["feature_eng", "hypothesis"],
    "threshold_calibration": ["modeling"],
    "explainability": ["threshold_calibration"],
    "recommendation": ["explainability"],
    "report": ["recommendation"],
}

# Reverse dependency graph: for each step, which steps depend on it
_REVERSE_DEPS: dict[str, list[str]] = {step: [] for step in STEP_ORDER}
for _step, _deps in DEPENDENCY_GRAPH.items():
    for _dep in _deps:
        _REVERSE_DEPS[_dep].append(_step)


class StepStateService:
    """Manages pipeline step states for a session."""

    def __init__(self, db: AsyncSession, event_service: EventService | None = None):
        self.db = db
        self.event_service = event_service

    def initialize_states(self) -> dict[str, str]:
        """Create default step states for a new session."""
        states: dict[str, str] = {}
        for step in STEP_ORDER:
            deps = DEPENDENCY_GRAPH[step]
            if not deps:
                states[step] = READY
            else:
                states[step] = NOT_STARTED
        return states

    def infer_states_from_current_step(self, current_step: str) -> dict[str, str]:
        """DEPRECATED: Backward compatibility inference from current_step.

        Does NOT mark prior steps as DONE — only as READY, since there's
        no evidence of actual agent execution.
        """
        logger.warning(
            "DEPRECATED: infer_states_from_current_step called — "
            "sessions should have explicit step_states",
            current_step=current_step,
        )
        states = {}

        # Map UI steps to pipeline steps
        ui_to_pipeline = {
            "onboarding": None,
            "upload": None,
            "profiling": "profiling",
            "workspace": "data_understanding",
            "target": "target_id",
            "feature-selection": "feature_selection",
            "eda": "eda",
            "hypotheses": "hypothesis",
            "hypothesis-results": "hypothesis",
            "models": "modeling",
            "shap": "explainability",
            "report": "report",
        }

        pipeline_step = ui_to_pipeline.get(current_step)

        if pipeline_step is None:
            return self.initialize_states()

        try:
            pipeline_idx = STEP_ORDER.index(pipeline_step)
        except ValueError:
            return self.initialize_states()

        # DEPRECATED: Do NOT mark all prior steps DONE
        for i, step in enumerate(STEP_ORDER):
            if i <= pipeline_idx:
                states[step] = READY  # Not DONE — agent must verify
            elif i == pipeline_idx + 1:
                states[step] = READY
            else:
                states[step] = NOT_STARTED

        return states

    async def get_states(self, session_id: uuid.UUID) -> dict[str, str]:
        """Get step states for a session, with backward compatibility."""
        session = await self.db.get(Session, session_id)
        if session is None:
            raise ValueError(f"Session {session_id} not found")

        step_states = getattr(session, "step_states", None)
        if step_states:
            return step_states

        # Backward compat: infer from current_step
        return self.infer_states_from_current_step(session.current_step)

    async def update_states(
        self, session_id: uuid.UUID, states: dict[str, str]
    ) -> dict[str, str]:
        """Persist step states to the session."""
        session = await self.db.get(Session, session_id)
        if session is None:
            raise ValueError(f"Session {session_id} not found")
        session.step_states = states
        await self.db.commit()
        await self.db.refresh(session)
        return states

    async def mark_running(self, session_id: uuid.UUID, step: str) -> dict[str, str]:
        """Mark a step as RUNNING."""
        states = await self.get_states(session_id)
        states[step] = RUNNING
        return await self.update_states(session_id, states)

    async def mark_done(self, session_id: uuid.UUID, step: str) -> dict[str, str]:
        """Mark a step as DONE and make its dependents READY."""
        states = await self.get_states(session_id)
        states[step] = DONE

        # Make dependents ready if all their dependencies are done
        for dependent in _REVERSE_DEPS.get(step, []):
            deps = DEPENDENCY_GRAPH[dependent]
            if all(states.get(d) == DONE for d in deps):
                if states.get(dependent) == NOT_STARTED:
                    states[dependent] = READY

        return await self.update_states(session_id, states)

    async def mark_failed(self, session_id: uuid.UUID, step: str) -> dict[str, str]:
        """Mark a step as FAILED."""
        states = await self.get_states(session_id)
        states[step] = FAILED
        return await self.update_states(session_id, states)

    async def invalidate_downstream(
        self, session_id: uuid.UUID, step: str
    ) -> dict[str, str]:
        """Mark all downstream steps of `step` as STALE.

        Uses BFS through the reverse dependency graph.
        Emits STEP_STALE events for each invalidated step.
        """
        states = await self.get_states(session_id)

        # BFS to find all downstream steps
        queue = list(_REVERSE_DEPS.get(step, []))
        visited: set[str] = set()
        stale_steps: list[str] = []

        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)

            if states.get(current) in (DONE, RUNNING):
                states[current] = STALE
                stale_steps.append(current)

            queue.extend(_REVERSE_DEPS.get(current, []))

        # Mark the step itself as READY (it's being re-run)
        states[step] = READY

        updated = await self.update_states(session_id, states)

        # Emit STEP_STALE events
        if self.event_service and stale_steps:
            for stale_step in stale_steps:
                try:
                    await self.event_service.emit(
                        self.db,
                        session_id,
                        TraceEventCreate(
                            event_type="STEP_STALE",
                            step=stale_step,
                            payload={"message": f"Step '{stale_step}' invalidated"},
                        ),
                    )
                except Exception as e:
                    logger.warning("Failed to emit STEP_STALE event", error=str(e))

        logger.info(
            "step_state_service.invalidate_downstream",
            session_id=str(session_id),
            from_step=step,
            stale_steps=stale_steps,
        )

        return updated

    def get_runnable_steps(self, states: dict[str, str]) -> list[str]:
        """Return steps that are READY (all dependencies met, none FAILED)."""
        runnable = []
        for step in STEP_ORDER:
            if states.get(step) == READY:
                deps = DEPENDENCY_GRAPH[step]
                if all(states.get(d) == DONE for d in deps):
                    # Also check no transitive dependency is FAILED
                    if not self._has_failed_dependency(step, states):
                        runnable.append(step)
        return runnable

    @staticmethod
    def _has_failed_dependency(step: str, states: dict[str, str]) -> bool:
        """Check if any dependency (transitive) of a step is FAILED."""
        deps = DEPENDENCY_GRAPH.get(step, [])
        for d in deps:
            if states.get(d) == FAILED:
                return True
            if StepStateService._has_failed_dependency(d, states):
                return True
        return False

    def has_running_steps(self, states: dict[str, str]) -> bool:
        """Check if any step is currently RUNNING."""
        return any(s == RUNNING for s in states.values())

    async def validate_completion(
        self, session_id: uuid.UUID, step: str
    ) -> bool:
        """Check if a step has real completion evidence.

        Returns True if:
        - The step_states dict has this step as DONE, OR
        - An approved proposal exists for this step, OR
        - An artifact exists for this step
        """
        from sqlalchemy import select

        # Check step_states first
        states = await self.get_states(session_id)
        if states.get(step) == DONE:
            return True

        # Check for approved proposals
        try:
            from app.models.proposal import Proposal

            stmt = select(Proposal).where(
                Proposal.session_id == session_id,
                Proposal.step == step,
                Proposal.status == "approved",
            )
            result = await self.db.execute(stmt)
            if result.scalar_one_or_none():
                return True
        except Exception:
            pass

        # Check for artifacts
        try:
            from app.models.artifact import Artifact

            stmt = select(Artifact).where(
                Artifact.session_id == session_id,
                Artifact.step == step,
            )
            result = await self.db.execute(stmt)
            if result.scalar_one_or_none():
                return True
        except Exception:
            pass

        return False

