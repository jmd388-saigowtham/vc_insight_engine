"""Tests for threshold calibration node."""

from __future__ import annotations

import pytest

from app.agent.nodes.threshold_calibration import threshold_calibration_node
from app.services.step_state_service import DONE, READY

pytestmark = pytest.mark.asyncio


def _make_state(**overrides):
    state = {
        "session_id": "00000000-0000-0000-0000-000000000001",
        "company_name": "TestCo",
        "industry": "SaaS",
        "business_context": "Churn prediction",
        "step_states": {"threshold_calibration": READY},
        "model_results": {},
        "selected_opportunity": {},
        "threshold_config": {},
        "pending_proposal_step": "",
        "pending_proposal_plan": {},
        "proposal_status": "",
        "proposal_feedback": "",
        "proposal_revision_count": {},
        "next_action": "",
        "trace_events": [],
    }
    state.update(overrides)
    return state


class TestThresholdCalibration:
    async def test_no_model_results_skips(self):
        state = _make_state(model_results={})
        result = await threshold_calibration_node(state)
        assert result["step_states"]["threshold_calibration"] == DONE
        assert result["threshold_config"]["threshold"] == 0.5

    async def test_propose_threshold(self):
        model_results = {
            "best_model": "random_forest",
            "models": [
                {
                    "model_name": "random_forest",
                    "precision": 0.82,
                    "recall": 0.75,
                    "f1_score": 0.78,
                    "auc_roc": 0.85,
                }
            ],
        }
        state = _make_state(model_results=model_results)
        result = await threshold_calibration_node(state)
        assert result["next_action"] == "wait"
        assert result["pending_proposal_step"] == "threshold_calibration"
        plan = result["pending_proposal_plan"]
        assert "recommended_threshold" in plan
        assert "threshold_analysis" in plan

    async def test_churn_prefers_lower_threshold(self):
        model_results = {
            "best_model": "rf",
            "models": [{"model_name": "rf", "precision": 0.8, "recall": 0.7, "f1_score": 0.75}],
        }
        state = _make_state(
            model_results=model_results,
            business_context="Predict customer churn",
        )
        result = await threshold_calibration_node(state)
        plan = result["pending_proposal_plan"]
        assert plan["recommended_threshold"] < 0.5

    async def test_execute_after_approval(self):
        state = _make_state(
            pending_proposal_step="threshold_calibration",
            proposal_status="approved",
            pending_proposal_plan={
                "recommended_threshold": 0.4,
                "best_model": "random_forest",
                "business_rationale": "Churn requires high recall",
                "current_metrics": {"precision": 0.8, "recall": 0.75},
            },
        )
        result = await threshold_calibration_node(state)
        assert result["step_states"]["threshold_calibration"] == DONE
        assert result["threshold_config"]["threshold"] == 0.4
        assert result["threshold_config"]["method"] == "optimized"

    async def test_reject_uses_default(self):
        state = _make_state(
            pending_proposal_step="threshold_calibration",
            proposal_status="rejected",
        )
        result = await threshold_calibration_node(state)
        assert result["step_states"]["threshold_calibration"] == DONE
        assert result["threshold_config"]["threshold"] == 0.5
