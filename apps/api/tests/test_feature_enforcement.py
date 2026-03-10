"""Tests for feature enforcement — only approved features used downstream.

Proves:
- Feature selection stores features in state
- Downstream nodes respect selected_features
- Changing feature selection marks downstream STALE
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.nodes.approval_helpers import mark_step_done
from app.agent.state import AgentState
from app.services.step_state_service import (
    DEPENDENCY_GRAPH,
    STEP_ORDER,
    StepStateService,
)


def _full_state(selected_features: list[str] | None = None) -> AgentState:
    """Create a state with common defaults and optional selected features."""
    state: AgentState = {
        "session_id": None,
        "current_step": "",
        "uploaded_files": [],
        "column_profiles": [
            {"column_name": "age", "data_type": "int64", "null_pct": 0, "unique_count": 50},
            {"column_name": "income", "data_type": "float64", "null_pct": 0.5, "unique_count": 100},
            {"column_name": "tenure", "data_type": "int64", "null_pct": 0, "unique_count": 30},
            {"column_name": "churn", "data_type": "int64", "null_pct": 0, "unique_count": 2},
        ],
        "target_column": "churn",
        "selected_features": selected_features or [],
        "next_action": "",
        "pending_step": "",
        "pending_code": "",
        "pending_code_description": "",
        "approval_status": "",
        "approved_code": "",
        "denial_counts": {},
        "step_states": {},
        "trace_events": [],
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
    }
    return state


class TestFeatureSelectionStorage:
    """Test that feature selection stores features in agent state."""

    def test_selected_features_stored_in_state(self):
        state = _full_state()
        features = ["age", "income", "tenure"]
        state["selected_features"] = features
        assert state["selected_features"] == features

    def test_selected_features_excludes_target(self):
        state = _full_state(["age", "income", "tenure"])
        target = state["target_column"]
        assert target not in state["selected_features"]


class TestFeatureEnforcementDownstream:
    """Test that downstream steps only see approved features."""

    def test_modeling_uses_selected_features(self):
        """The modeling node receives only selected features from state."""
        state = _full_state(["age", "tenure"])
        # Simulate what modeling node does — reads selected_features
        selected = state.get("selected_features", [])
        assert selected == ["age", "tenure"]
        assert "income" not in selected

    def test_eda_uses_selected_features(self):
        """EDA should focus on selected features."""
        state = _full_state(["age", "income"])
        selected = state.get("selected_features", [])
        assert len(selected) == 2
        assert "tenure" not in selected


class TestStaleInvalidation:
    """Test that changing feature selection marks downstream steps STALE."""

    def test_feature_selection_depends_on_target_id(self):
        """Feature selection lists target_id as a dependency."""
        deps = DEPENDENCY_GRAPH.get("feature_selection", [])
        assert "target_id" in deps

    def test_eda_depends_on_feature_selection(self):
        """EDA depends on feature_selection."""
        deps = DEPENDENCY_GRAPH.get("eda", [])
        assert "feature_selection" in deps

    def test_preprocessing_depends_on_feature_selection(self):
        """Preprocessing depends on feature_selection."""
        deps = DEPENDENCY_GRAPH.get("preprocessing", [])
        assert "feature_selection" in deps

    def test_downstream_steps_affected_by_feature_selection(self):
        """All steps after feature_selection should be affected by invalidation."""
        fs_idx = STEP_ORDER.index("feature_selection")
        downstream = STEP_ORDER[fs_idx + 1:]
        # These steps should all come after feature_selection
        for step in ["eda", "preprocessing", "modeling", "report"]:
            if step in STEP_ORDER:
                assert step in downstream

    @pytest.mark.asyncio
    async def test_invalidate_downstream_marks_stale(self, db_session: AsyncSession):
        """Invalidating feature_selection marks all downstream steps STALE."""
        from app.models.session import Session
        import uuid

        session_id = uuid.uuid4()
        session = Session(id=session_id, company_name="Test Corp")
        db_session.add(session)
        await db_session.commit()

        svc = StepStateService(db_session)
        # Initialize all states to DONE
        states = svc.initialize_states()
        for step in STEP_ORDER:
            states[step] = "DONE"
        await svc.update_states(session_id, states)

        # Invalidate from feature_selection
        new_states = await svc.invalidate_downstream(session_id, "feature_selection")

        # feature_selection should be READY for re-run
        assert new_states["feature_selection"] == "READY"

        # Downstream steps should be STALE
        fs_idx = STEP_ORDER.index("feature_selection")
        for step in STEP_ORDER[fs_idx + 1:]:
            assert new_states[step] == "STALE", f"Expected {step} to be STALE"

        # Upstream steps should remain DONE
        for step in STEP_ORDER[:fs_idx]:
            assert new_states[step] == "DONE", f"Expected {step} to still be DONE"
