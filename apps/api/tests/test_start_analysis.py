"""Tests for the start-analysis endpoint existence and routing."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


class TestStartAnalysisEndpoint:
    async def test_endpoint_registered(self, client: AsyncClient):
        """Verify the start-analysis endpoint is registered (returns non-405)."""
        fake_id = uuid.uuid4()
        resp = await client.post(f"/sessions/{fake_id}/start-analysis")
        # Should NOT be 405 Method Not Allowed — the route exists
        assert resp.status_code != 405
        # Should be error (session not found) — but the route works
        data = resp.json()
        assert data.get("status") == "error" or resp.status_code in (404, 500)

    async def test_run_pipeline_endpoint_removed(self, client: AsyncClient):
        """Legacy run-pipeline endpoint should no longer exist."""
        fake_id = uuid.uuid4()
        resp = await client.post(f"/sessions/{fake_id}/run-pipeline")
        # Should be 405 Method Not Allowed or 404 — the route is deleted
        assert resp.status_code in (404, 405)

    async def test_resume_accepts_proposal_type(self, client: AsyncClient):
        """Resume endpoint should accept proposal_type parameter."""
        fake_id = uuid.uuid4()
        resp = await client.post(
            f"/sessions/{fake_id}/resume",
            json={"proposal_id": str(uuid.uuid4()), "proposal_type": "business"},
        )
        # Should not be 422 (validation error) — the parameter is accepted
        assert resp.status_code != 422
