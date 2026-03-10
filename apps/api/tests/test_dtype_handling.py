"""Tests for dtype handling node."""

from __future__ import annotations

import pytest

from app.agent.nodes.dtype_handling import (
    _suggest_type,
    _type_reasoning,
    dtype_handling_node,
)
from app.services.step_state_service import DONE, READY

pytestmark = pytest.mark.asyncio


def _make_state(**overrides):
    state = {
        "session_id": "00000000-0000-0000-0000-000000000001",
        "company_name": "TestCo",
        "industry": "SaaS",
        "business_context": "Churn analysis",
        "step_states": {"dtype_handling": READY},
        "column_profiles": [],
        "dtype_decisions": {},
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


class TestSuggestType:
    def test_date_column_from_string(self):
        result = _suggest_type("object", ["2024-01-01", "2024-02-01"], "created_date")
        assert result == "datetime64"

    def test_id_column_from_int(self):
        result = _suggest_type("int64", [1001, 1002], "customer_id")
        assert result == "object"

    def test_no_change_needed(self):
        result = _suggest_type("float64", [1.5, 2.3], "revenue")
        assert result is None

    def test_boolean_flag(self):
        result = _suggest_type("float64", [0, 1, 0, 1], "is_active")
        assert result == "bool"


class TestTypeReasoning:
    def test_datetime_reasoning(self):
        r = _type_reasoning("date_col", "object", "datetime64", [])
        assert "date" in r.lower()

    def test_id_reasoning(self):
        r = _type_reasoning("customer_id", "int64", "object", [])
        assert "identifier" in r.lower()


class TestDtypeHandlingNode:
    async def test_no_profiles_skips(self):
        state = _make_state(column_profiles=[])
        result = await dtype_handling_node(state)
        assert result["step_states"]["dtype_handling"] == DONE
        assert result["next_action"] == "orchestrator"

    async def test_propose_corrections(self):
        profiles = [
            {
                "column_name": "created_date",
                "data_type": "object",
                "null_pct": 0,
                "sample_values": ["2024-01-01"],
                "unique_count": 10,
            },
            {
                "column_name": "revenue",
                "data_type": "float64",
                "null_pct": 5,
                "sample_values": [100.5, 200.3],
                "unique_count": 50,
            },
        ]
        state = _make_state(column_profiles=profiles)
        result = await dtype_handling_node(state)
        # Should propose a correction for created_date
        assert result["next_action"] == "wait"
        assert result["pending_proposal_step"] == "dtype_handling"
        plan = result["pending_proposal_plan"]
        assert plan["columns_to_fix"] >= 1

    async def test_execute_after_approval(self):
        state = _make_state(
            pending_proposal_step="dtype_handling",
            proposal_status="approved",
            pending_proposal_plan={
                "corrections": [
                    {
                        "column": "date_col",
                        "current_type": "object",
                        "suggested_type": "datetime64",
                    }
                ]
            },
        )
        result = await dtype_handling_node(state)
        assert result["step_states"]["dtype_handling"] == DONE
        assert result["dtype_decisions"]["status"] == "applied"

    async def test_reject_uses_originals(self):
        state = _make_state(
            pending_proposal_step="dtype_handling",
            proposal_status="rejected",
        )
        result = await dtype_handling_node(state)
        assert result["step_states"]["dtype_handling"] == DONE
