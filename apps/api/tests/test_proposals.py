"""Tests for business-logic proposals CRUD and lifecycle."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def session_id(client: AsyncClient) -> str:
    resp = await client.post(
        "/sessions",
        json={"company_name": "TestCo", "industry": "SaaS"},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.fixture
async def proposal_id(client: AsyncClient, session_id: str) -> str:
    """Create a proposal directly via DB for testing endpoints."""
    from app.models.proposal import Proposal
    from sqlalchemy.ext.asyncio import AsyncSession

    # Use the API client to create a proposal through a helper endpoint
    # Since we don't have a direct creation endpoint, we'll use the DB
    from tests.conftest import test_session_factory

    async with test_session_factory() as db:
        proposal = Proposal(
            id=uuid.uuid4(),
            session_id=uuid.UUID(session_id),
            step="merge_planning",
            proposal_type="merge_plan",
            status="pending",
            version=1,
            plan={"tables": ["orders", "customers"], "join_key": "customer_id"},
            summary="Join orders and customers on customer_id",
            ai_reasoning="Both tables share customer_id column",
            alternatives=[
                {"join_key": "email", "reasoning": "Alternative join on email"}
            ],
        )
        db.add(proposal)
        await db.commit()
        return str(proposal.id)


class TestListProposals:
    async def test_list_empty(self, client: AsyncClient, session_id: str):
        resp = await client.get(f"/sessions/{session_id}/proposals")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_with_proposal(
        self, client: AsyncClient, session_id: str, proposal_id: str
    ):
        resp = await client.get(f"/sessions/{session_id}/proposals")
        assert resp.status_code == 200
        proposals = resp.json()
        assert len(proposals) == 1
        assert proposals[0]["id"] == proposal_id
        assert proposals[0]["step"] == "merge_planning"
        assert proposals[0]["proposal_type"] == "merge_plan"

    async def test_list_filter_by_step(
        self, client: AsyncClient, session_id: str, proposal_id: str
    ):
        resp = await client.get(
            f"/sessions/{session_id}/proposals?step=merge_planning"
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 1

        resp = await client.get(
            f"/sessions/{session_id}/proposals?step=eda"
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 0

    async def test_list_filter_by_status(
        self, client: AsyncClient, session_id: str, proposal_id: str
    ):
        resp = await client.get(
            f"/sessions/{session_id}/proposals?status=pending"
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 1

        resp = await client.get(
            f"/sessions/{session_id}/proposals?status=approved"
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 0


class TestPendingProposals:
    async def test_list_pending(
        self, client: AsyncClient, session_id: str, proposal_id: str
    ):
        resp = await client.get(
            f"/sessions/{session_id}/proposals/pending"
        )
        assert resp.status_code == 200
        proposals = resp.json()
        assert len(proposals) == 1
        assert proposals[0]["status"] == "pending"


class TestGetProposal:
    async def test_get_existing(
        self, client: AsyncClient, proposal_id: str
    ):
        resp = await client.get(f"/proposals/{proposal_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == proposal_id
        assert data["plan"]["join_key"] == "customer_id"
        assert data["ai_reasoning"] == "Both tables share customer_id column"

    async def test_get_not_found(self, client: AsyncClient):
        fake_id = str(uuid.uuid4())
        resp = await client.get(f"/proposals/{fake_id}")
        assert resp.status_code == 404


class TestApproveProposal:
    async def test_approve_pending(
        self, client: AsyncClient, proposal_id: str
    ):
        resp = await client.post(f"/proposals/{proposal_id}/approve")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "approved"
        assert data["resolved_at"] is not None

    async def test_approve_already_approved(
        self, client: AsyncClient, proposal_id: str
    ):
        await client.post(f"/proposals/{proposal_id}/approve")
        resp = await client.post(f"/proposals/{proposal_id}/approve")
        assert resp.status_code == 400


class TestReviseProposal:
    async def test_revise_with_feedback(
        self, client: AsyncClient, proposal_id: str
    ):
        resp = await client.post(
            f"/proposals/{proposal_id}/revise",
            json={"feedback": "Use email as join key instead"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "revised"
        assert data["user_feedback"] == "Use email as join key instead"
        assert data["resolved_at"] is not None

    async def test_revise_non_pending(
        self, client: AsyncClient, proposal_id: str
    ):
        await client.post(f"/proposals/{proposal_id}/approve")
        resp = await client.post(
            f"/proposals/{proposal_id}/revise",
            json={"feedback": "Too late"},
        )
        assert resp.status_code == 400


class TestRejectProposal:
    async def test_reject_pending(
        self, client: AsyncClient, proposal_id: str
    ):
        resp = await client.post(
            f"/proposals/{proposal_id}/reject",
            json={"feedback": "I want to use a different approach"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "rejected"
        assert data["user_feedback"] == "I want to use a different approach"

    async def test_reject_without_feedback(
        self, client: AsyncClient, proposal_id: str
    ):
        resp = await client.post(f"/proposals/{proposal_id}/reject")
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"


class TestSelectProposalOption:
    async def test_select_valid_option(
        self, client: AsyncClient, session_id: str
    ):
        from app.models.proposal import Proposal
        from tests.conftest import test_session_factory

        async with test_session_factory() as db:
            proposal = Proposal(
                id=uuid.uuid4(),
                session_id=uuid.UUID(session_id),
                step="opportunity_analysis",
                proposal_type="opportunity_analysis",
                status="pending",
                version=1,
                plan={
                    "options": [
                        {"title": "Churn reduction", "confidence": 0.85},
                        {"title": "Revenue expansion", "confidence": 0.72},
                    ]
                },
                summary="Two value creation opportunities identified",
                ai_reasoning="Based on data patterns",
            )
            db.add(proposal)
            await db.commit()
            pid = str(proposal.id)

        resp = await client.post(
            f"/proposals/{pid}/select",
            json={"selected_index": 0, "feedback": "Focus on churn"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "approved"
        assert data["plan"]["selected_index"] == 0
        assert data["plan"]["selected_option"]["title"] == "Churn reduction"

    async def test_select_invalid_index(
        self, client: AsyncClient, session_id: str
    ):
        from app.models.proposal import Proposal
        from tests.conftest import test_session_factory

        async with test_session_factory() as db:
            proposal = Proposal(
                id=uuid.uuid4(),
                session_id=uuid.UUID(session_id),
                step="opportunity_analysis",
                proposal_type="opportunity_analysis",
                status="pending",
                version=1,
                plan={"options": [{"title": "Option A"}]},
                summary="One option",
                ai_reasoning="test",
            )
            db.add(proposal)
            await db.commit()
            pid = str(proposal.id)

        resp = await client.post(
            f"/proposals/{pid}/select",
            json={"selected_index": 5},
        )
        assert resp.status_code == 400


class TestProposalHistory:
    async def test_get_history(
        self, client: AsyncClient, proposal_id: str
    ):
        resp = await client.get(f"/proposals/{proposal_id}/history")
        assert resp.status_code == 200
        history = resp.json()
        assert len(history) >= 1
        assert history[0]["id"] == proposal_id
