"""Tests for step completion semantics — Phase 1.

Verifies that:
- mark_step_failed marks a step FAILED without cascading READY
- mark_step_done marks a step DONE and cascades READY
- mark_step_skipped records reason and delegates to mark_step_done
- revert_step_to_ready sets step to READY
- Failed dependency checking is transitive
- Orchestrator routing respects FAILED dependencies
"""

import pytest

from app.agent.nodes.approval_helpers import (
    mark_step_done,
    mark_step_failed,
    mark_step_skipped,
    revert_step_to_ready,
)
from app.services.step_state_service import (
    DEPENDENCY_GRAPH,
    DONE,
    FAILED,
    NOT_STARTED,
    READY,
    STEP_ORDER,
    StepStateService,
)


def _make_state(**overrides):
    """Create minimal AgentState for testing approval helpers."""
    base = {
        "session_id": None,
        "step_states": {step: NOT_STARTED for step in STEP_ORDER},
        "trace_events": [],
        "error": None,
    }
    base.update(overrides)
    return base


class TestMarkStepFailed:
    """mark_step_failed sets FAILED and does NOT cascade."""

    def test_marks_step_failed(self):
        state = _make_state()
        state["step_states"]["profiling"] = READY
        mark_step_failed(state, "profiling")
        assert state["step_states"]["profiling"] == FAILED

    def test_does_not_cascade_ready(self):
        state = _make_state()
        state["step_states"]["profiling"] = READY
        mark_step_failed(state, "profiling")
        # dtype_handling depends on profiling — should NOT become READY
        assert state["step_states"]["dtype_handling"] == NOT_STARTED

    def test_failed_step_leaves_dependents_unchanged(self):
        state = _make_state()
        # Set up: profiling DONE, dtype_handling READY
        state["step_states"]["profiling"] = DONE
        state["step_states"]["dtype_handling"] = READY
        mark_step_failed(state, "dtype_handling")
        assert state["step_states"]["dtype_handling"] == FAILED
        # data_understanding depends on dtype_handling — stays NOT_STARTED
        assert state["step_states"]["data_understanding"] == NOT_STARTED


class TestMarkStepDone:
    """mark_step_done cascades READY to dependents."""

    def test_marks_step_done(self):
        state = _make_state()
        state["step_states"]["profiling"] = READY
        mark_step_done(state, "profiling")
        assert state["step_states"]["profiling"] == DONE

    def test_cascades_ready_to_dependents(self):
        state = _make_state()
        state["step_states"]["profiling"] = READY
        mark_step_done(state, "profiling")
        # dtype_handling depends only on profiling → becomes READY
        assert state["step_states"]["dtype_handling"] == READY

    def test_does_not_cascade_when_not_all_deps_done(self):
        state = _make_state()
        state["step_states"]["profiling"] = DONE
        state["step_states"]["target_id"] = DONE
        state["step_states"]["opportunity_analysis"] = DONE
        # feature_selection depends on target_id AND profiling — both DONE → READY
        mark_step_done(state, "target_id")
        assert state["step_states"]["feature_selection"] == READY

    def test_multi_dep_not_all_done(self):
        state = _make_state()
        # modeling depends on feature_eng AND hypothesis
        state["step_states"]["feature_eng"] = DONE
        state["step_states"]["hypothesis"] = NOT_STARTED
        # Mark feature_eng done — modeling should NOT become READY (hypothesis not done)
        mark_step_done(state, "feature_eng")
        assert state["step_states"]["modeling"] == NOT_STARTED


class TestMarkStepSkipped:
    """mark_step_skipped records reason and delegates to mark_step_done."""

    def test_records_skip_reason(self):
        state = _make_state()
        state["step_states"]["merge_planning"] = READY
        mark_step_skipped(state, "merge_planning", "single_file")
        assert state.get("skip_reasons", {}).get("merge_planning") == "single_file"

    def test_marks_step_done(self):
        state = _make_state()
        state["step_states"]["merge_planning"] = READY
        mark_step_skipped(state, "merge_planning", "single_file")
        assert state["step_states"]["merge_planning"] == DONE

    def test_cascades_like_done(self):
        state = _make_state()
        # Set all deps for merge_planning as DONE
        state["step_states"]["profiling"] = DONE
        state["step_states"]["dtype_handling"] = DONE
        state["step_states"]["data_understanding"] = DONE
        state["step_states"]["merge_planning"] = READY
        mark_step_skipped(state, "merge_planning", "single_file")
        # opportunity_analysis depends on merge_planning → READY
        assert state["step_states"]["opportunity_analysis"] == READY


class TestRevertStepToReady:
    """revert_step_to_ready sets step back to READY."""

    def test_reverts_to_ready(self):
        state = _make_state()
        state["step_states"]["target_id"] = DONE
        revert_step_to_ready(state, "target_id")
        assert state["step_states"]["target_id"] == READY

    def test_reverts_from_failed(self):
        state = _make_state()
        state["step_states"]["target_id"] = FAILED
        revert_step_to_ready(state, "target_id")
        assert state["step_states"]["target_id"] == READY


class TestFailedDependencyCheck:
    """StepStateService._has_failed_dependency checks transitively."""

    def test_direct_failed_dependency(self):
        states = {step: NOT_STARTED for step in STEP_ORDER}
        states["profiling"] = FAILED
        assert StepStateService._has_failed_dependency("dtype_handling", states) is True

    def test_transitive_failed_dependency(self):
        states = {step: NOT_STARTED for step in STEP_ORDER}
        states["profiling"] = FAILED
        # data_understanding → dtype_handling → profiling (FAILED)
        assert StepStateService._has_failed_dependency("data_understanding", states) is True

    def test_no_failed_dependency(self):
        states = {step: NOT_STARTED for step in STEP_ORDER}
        states["profiling"] = DONE
        states["dtype_handling"] = DONE
        assert StepStateService._has_failed_dependency("data_understanding", states) is False

    def test_deep_transitive_failed(self):
        states = {step: DONE for step in STEP_ORDER}
        states["profiling"] = FAILED
        # report → recommendation → explainability → ... → profiling (FAILED)
        assert StepStateService._has_failed_dependency("report", states) is True

    def test_no_deps_no_failed(self):
        states = {step: NOT_STARTED for step in STEP_ORDER}
        # profiling has no deps
        assert StepStateService._has_failed_dependency("profiling", states) is False


class TestGetRunnableSteps:
    """get_runnable_steps respects FAILED dependencies."""

    def test_basic_runnable(self):
        svc = StepStateService(db=None)
        states = {step: NOT_STARTED for step in STEP_ORDER}
        states["profiling"] = READY
        runnable = svc.get_runnable_steps(states)
        assert "profiling" in runnable

    def test_failed_dep_blocks_runnable(self):
        svc = StepStateService(db=None)
        states = {step: NOT_STARTED for step in STEP_ORDER}
        states["profiling"] = FAILED
        states["dtype_handling"] = READY
        runnable = svc.get_runnable_steps(states)
        assert "dtype_handling" not in runnable

    def test_transitive_failed_blocks(self):
        svc = StepStateService(db=None)
        states = {step: NOT_STARTED for step in STEP_ORDER}
        states["profiling"] = FAILED
        states["dtype_handling"] = READY
        states["data_understanding"] = READY
        runnable = svc.get_runnable_steps(states)
        assert "dtype_handling" not in runnable
        assert "data_understanding" not in runnable

    def test_failed_step_itself_not_runnable(self):
        svc = StepStateService(db=None)
        states = {step: NOT_STARTED for step in STEP_ORDER}
        states["profiling"] = FAILED
        runnable = svc.get_runnable_steps(states)
        assert "profiling" not in runnable

    def test_merge_failure_blocks_all_downstream(self):
        """Failed merge blocks target_id, feature_selection, and everything downstream."""
        svc = StepStateService(db=None)
        states = {step: DONE for step in STEP_ORDER}
        states["merge_planning"] = FAILED
        # Mark some downstream steps as READY
        states["opportunity_analysis"] = READY
        states["target_id"] = READY
        runnable = svc.get_runnable_steps(states)
        assert "opportunity_analysis" not in runnable
        assert "target_id" not in runnable
