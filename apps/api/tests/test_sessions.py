from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_session(client: AsyncClient) -> None:
    response = await client.post(
        "/sessions",
        json={"company_name": "Acme Corp", "industry": "Technology"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["company_name"] == "Acme Corp"
    assert data["industry"] == "Technology"
    assert data["current_step"] == "onboarding"
    assert data["status"] == "active"
    assert "id" in data


@pytest.mark.asyncio
async def test_get_session(client: AsyncClient) -> None:
    create_resp = await client.post(
        "/sessions",
        json={"company_name": "Test Inc"},
    )
    session_id = create_resp.json()["id"]

    response = await client.get(f"/sessions/{session_id}")
    assert response.status_code == 200
    assert response.json()["company_name"] == "Test Inc"


@pytest.mark.asyncio
async def test_get_session_not_found(client: AsyncClient) -> None:
    response = await client.get("/sessions/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_session(client: AsyncClient) -> None:
    create_resp = await client.post(
        "/sessions",
        json={"company_name": "Old Name"},
    )
    session_id = create_resp.json()["id"]

    response = await client.patch(
        f"/sessions/{session_id}",
        json={"company_name": "New Name", "industry": "Finance"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["company_name"] == "New Name"
    assert data["industry"] == "Finance"


@pytest.mark.asyncio
async def test_list_sessions(client: AsyncClient) -> None:
    await client.post("/sessions", json={"company_name": "A"})
    await client.post("/sessions", json={"company_name": "B"})

    response = await client.get("/sessions")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 2


@pytest.mark.asyncio
async def test_update_business_context(client: AsyncClient) -> None:
    create_resp = await client.post(
        "/sessions",
        json={"company_name": "Context Corp"},
    )
    session_id = create_resp.json()["id"]

    response = await client.post(
        f"/sessions/{session_id}/business-context",
        json={"business_context": "We are a SaaS company focused on B2B"},
    )
    assert response.status_code == 200
    assert response.json()["business_context"] == "We are a SaaS company focused on B2B"
