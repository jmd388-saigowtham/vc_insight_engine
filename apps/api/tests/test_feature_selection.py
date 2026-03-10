"""Tests for feature selection endpoints."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.models.session import Session


@pytest.fixture
async def session_for_features(db_session):
    """Create a session with target and features set."""
    session = Session(
        id=uuid.uuid4(),
        company_name="Feature Test Corp",
        industry="SaaS",
        current_step="target",
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)
    return session


class TestFeatureSelectionEndpoints:
    @pytest.mark.asyncio
    async def test_get_feature_selection(self, client: AsyncClient, session_for_features):
        resp = await client.get(
            f"/sessions/{session_for_features.id}/feature-selection"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "target_column" in data
        assert "features" in data
        assert "selected_features" in data

    @pytest.mark.asyncio
    async def test_get_feature_selection_not_found(self, client: AsyncClient):
        fake_id = uuid.uuid4()
        resp = await client.get(f"/sessions/{fake_id}/feature-selection")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_feature_selection(self, client: AsyncClient, session_for_features):
        resp = await client.patch(
            f"/sessions/{session_for_features.id}/feature-selection",
            json={
                "target_column": "churn",
                "selected_features": ["age", "tenure", "monthly_charges"],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["target_column"] == "churn"
        assert data["selected_features"] == ["age", "tenure", "monthly_charges"]

    @pytest.mark.asyncio
    async def test_update_feature_selection_empty_features(
        self, client: AsyncClient, session_for_features
    ):
        resp = await client.patch(
            f"/sessions/{session_for_features.id}/feature-selection",
            json={
                "target_column": "churn",
                "selected_features": [],
            },
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_update_feature_selection_target_in_features(
        self, client: AsyncClient, session_for_features
    ):
        resp = await client.patch(
            f"/sessions/{session_for_features.id}/feature-selection",
            json={
                "target_column": "churn",
                "selected_features": ["churn", "age", "tenure"],
            },
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_step_states_endpoint(self, client: AsyncClient, session_for_features):
        resp = await client.get(
            f"/sessions/{session_for_features.id}/step-states"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "step_states" in data


class TestResumeEndpoint:
    @pytest.mark.asyncio
    async def test_resume_not_found(self, client: AsyncClient):
        fake_id = uuid.uuid4()
        resp = await client.post(f"/sessions/{fake_id}/resume")
        # May return various error codes since session doesn't exist
        assert resp.status_code >= 400


class TestRerunEndpoint:
    @pytest.mark.asyncio
    async def test_rerun_invalid_step(self, client: AsyncClient, session_for_features):
        resp = await client.post(
            f"/sessions/{session_for_features.id}/rerun/nonexistent_step"
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_rerun_valid_step(self, client: AsyncClient, session_for_features):
        # Mock the agent service to avoid invoking the real LangGraph/LLM pipeline
        mock_result = {
            "session_id": str(session_for_features.id),
            "status": "completed",
            "report_path": "",
        }
        with patch(
            "app.services.agent_service.AgentService",
            return_value=AsyncMock(run_step=AsyncMock(return_value=mock_result)),
        ):
            resp = await client.post(
                f"/sessions/{session_for_features.id}/rerun/profiling"
            )
            assert resp.status_code == 200
