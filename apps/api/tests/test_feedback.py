"""Tests for user feedback submission and listing."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def session_id(client: AsyncClient) -> str:
    resp = await client.post(
        "/sessions",
        json={"company_name": "FeedbackCo", "industry": "Fintech"},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


class TestSubmitFeedback:
    async def test_submit_basic(self, client: AsyncClient, session_id: str):
        resp = await client.post(
            f"/sessions/{session_id}/feedback",
            json={"message": "Focus on churn analysis"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["message"] == "Focus on churn analysis"
        assert data["status"] == "pending"
        assert data["step"] is None
        assert data["session_id"] == session_id

    async def test_submit_with_step(self, client: AsyncClient, session_id: str):
        resp = await client.post(
            f"/sessions/{session_id}/feedback",
            json={
                "message": "Add box plot for revenue column",
                "step": "eda",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["step"] == "eda"
        assert data["message"] == "Add box plot for revenue column"


class TestListFeedback:
    async def test_list_empty(self, client: AsyncClient, session_id: str):
        resp = await client.get(f"/sessions/{session_id}/feedback")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_with_feedback(
        self, client: AsyncClient, session_id: str
    ):
        await client.post(
            f"/sessions/{session_id}/feedback",
            json={"message": "msg1", "step": "eda"},
        )
        await client.post(
            f"/sessions/{session_id}/feedback",
            json={"message": "msg2", "step": "modeling"},
        )

        resp = await client.get(f"/sessions/{session_id}/feedback")
        assert resp.status_code == 200
        feedback_list = resp.json()
        assert len(feedback_list) == 2

    async def test_filter_by_step(
        self, client: AsyncClient, session_id: str
    ):
        await client.post(
            f"/sessions/{session_id}/feedback",
            json={"message": "eda feedback", "step": "eda"},
        )
        await client.post(
            f"/sessions/{session_id}/feedback",
            json={"message": "model feedback", "step": "modeling"},
        )

        resp = await client.get(
            f"/sessions/{session_id}/feedback?step=eda"
        )
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["step"] == "eda"

    async def test_filter_by_status(
        self, client: AsyncClient, session_id: str
    ):
        await client.post(
            f"/sessions/{session_id}/feedback",
            json={"message": "test"},
        )

        resp = await client.get(
            f"/sessions/{session_id}/feedback?status=pending"
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 1

        resp = await client.get(
            f"/sessions/{session_id}/feedback?status=acknowledged"
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 0
