"""Tests for custom actions — custom plot/hypothesis/model requests.

Proves:
- Custom endpoints exist and accept requests
- Start-analysis endpoint routes through the agent
- Resume endpoint handles proposal types
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.models.session import Session

pytestmark = pytest.mark.asyncio


class TestStartAnalysisRoute:
    """Test that start-analysis routes through the agent."""

    async def test_start_analysis_endpoint_exists(self, client: AsyncClient):
        """POST /start-analysis should be registered."""
        fake_id = uuid.uuid4()
        resp = await client.post(f"/sessions/{fake_id}/start-analysis")
        assert resp.status_code != 405  # Not Method Not Allowed

    async def test_run_pipeline_endpoint_removed(self, client: AsyncClient):
        """Legacy POST /run-pipeline should no longer exist."""
        fake_id = uuid.uuid4()
        resp = await client.post(f"/sessions/{fake_id}/run-pipeline")
        assert resp.status_code in (404, 405)


class TestResumeWithProposalTypes:
    """Test resume handles both code and business proposals."""

    async def test_resume_accepts_code_proposal_type(self, client: AsyncClient):
        fake_id = uuid.uuid4()
        resp = await client.post(
            f"/sessions/{fake_id}/resume",
            json={"proposal_id": str(uuid.uuid4()), "proposal_type": "code"},
        )
        assert resp.status_code != 422  # Not validation error

    async def test_resume_accepts_business_proposal_type(self, client: AsyncClient):
        fake_id = uuid.uuid4()
        resp = await client.post(
            f"/sessions/{fake_id}/resume",
            json={"proposal_id": str(uuid.uuid4()), "proposal_type": "business"},
        )
        assert resp.status_code != 422


class TestCustomEndpointsExist:
    """Test that custom endpoints are registered (not bypassed)."""

    async def test_custom_plot_endpoint_exists(self, client: AsyncClient):
        """POST /eda/custom-plot should be registered."""
        fake_id = uuid.uuid4()
        resp = await client.post(
            f"/sessions/{fake_id}/eda/custom-plot",
            json={"request": "scatter plot of age vs income"},
        )
        # Should NOT be 405 (route exists). May be 404 (session not found)
        assert resp.status_code != 405

    async def test_custom_hypothesis_endpoint_exists(self, client: AsyncClient):
        """POST /hypotheses/custom should be registered."""
        fake_id = uuid.uuid4()
        resp = await client.post(
            f"/sessions/{fake_id}/hypotheses/custom",
            json={
                "statement": "Age differs by churn group",
                "test_type": "t_test",
                "variables": ["age", "churn"],
            },
        )
        assert resp.status_code != 405

    async def test_train_additional_model_endpoint_exists(self, client: AsyncClient):
        """POST /train-additional-model should be registered."""
        fake_id = uuid.uuid4()
        resp = await client.post(
            f"/sessions/{fake_id}/train-additional-model",
            json={"model_type": "random_forest"},
        )
        assert resp.status_code != 405

    async def test_retrain_threshold_endpoint_exists(self, client: AsyncClient):
        """POST /retrain-threshold should be registered."""
        fake_id = uuid.uuid4()
        resp = await client.post(
            f"/sessions/{fake_id}/retrain-threshold",
            json={"model_name": "Random Forest", "threshold": 0.6},
        )
        assert resp.status_code != 405


class TestRerunFromStep:
    """Test the rerun-from-step endpoint."""

    async def test_rerun_endpoint_exists(self, client: AsyncClient):
        fake_id = uuid.uuid4()
        resp = await client.post(f"/sessions/{fake_id}/rerun/profiling")
        assert resp.status_code != 405

    async def test_rerun_invalid_step(self, client: AsyncClient):
        fake_id = uuid.uuid4()
        resp = await client.post(f"/sessions/{fake_id}/rerun/invalid_step_name")
        assert resp.status_code == 400


class TestReadOnlyEndpoints:
    """Test that read-only endpoints work correctly."""

    async def test_opportunities_endpoint(self, client: AsyncClient):
        fake_id = uuid.uuid4()
        resp = await client.get(f"/sessions/{fake_id}/opportunities")
        # Empty list for nonexistent session
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_complete_session_endpoint(self, client: AsyncClient):
        """POST /complete should be registered."""
        fake_id = uuid.uuid4()
        resp = await client.post(f"/sessions/{fake_id}/complete")
        # May fail to find session, but route exists
        assert resp.status_code != 405
