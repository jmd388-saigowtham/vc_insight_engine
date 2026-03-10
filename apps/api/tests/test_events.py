from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import Session
from app.models.trace_event import TraceEvent


async def _create_session(db: AsyncSession, name: str = "Event Corp") -> uuid.UUID:
    session_id = uuid.uuid4()
    session = Session(id=session_id, company_name=name)
    db.add(session)
    await db.commit()
    return session_id


async def _create_event(
    db: AsyncSession,
    session_id: uuid.UUID,
    event_type: str = "PLAN",
    step: str | None = "profiling",
    payload: dict | None = None,
) -> TraceEvent:
    event = TraceEvent(
        id=uuid.uuid4(),
        session_id=session_id,
        event_type=event_type,
        step=step,
        payload=payload or {"message": "test event"},
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


@pytest.mark.asyncio
async def test_get_events_empty(client: AsyncClient, db_session: AsyncSession) -> None:
    session_id = await _create_session(db_session)

    response = await client.get(f"/sessions/{session_id}/events")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_get_events_returns_created(client: AsyncClient, db_session: AsyncSession) -> None:
    session_id = await _create_session(db_session)
    await _create_event(db_session, session_id, "PLAN", "profiling")
    await _create_event(db_session, session_id, "TOOL_CALL", "eda")

    response = await client.get(f"/sessions/{session_id}/events")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


@pytest.mark.asyncio
async def test_get_events_contains_fields(client: AsyncClient, db_session: AsyncSession) -> None:
    session_id = await _create_session(db_session)
    await _create_event(
        db_session, session_id, "ERROR", "modeling", {"error": "Out of memory"}
    )

    response = await client.get(f"/sessions/{session_id}/events")
    assert response.status_code == 200
    event = response.json()[0]
    assert event["event_type"] == "ERROR"
    assert event["step"] == "modeling"
    assert event["payload"]["error"] == "Out of memory"
    assert "id" in event
    assert "created_at" in event


@pytest.mark.asyncio
async def test_get_events_pagination_limit(client: AsyncClient, db_session: AsyncSession) -> None:
    session_id = await _create_session(db_session)
    for i in range(5):
        await _create_event(db_session, session_id, "TOOL_CALL", f"step_{i}")

    response = await client.get(f"/sessions/{session_id}/events?limit=3")
    assert response.status_code == 200
    assert len(response.json()) == 3


@pytest.mark.asyncio
async def test_get_events_pagination_offset(client: AsyncClient, db_session: AsyncSession) -> None:
    session_id = await _create_session(db_session)
    for i in range(5):
        await _create_event(db_session, session_id, "TOOL_CALL", f"step_{i}")

    response = await client.get(f"/sessions/{session_id}/events?limit=50&offset=3")
    assert response.status_code == 200
    assert len(response.json()) == 2


@pytest.mark.asyncio
async def test_get_events_different_types(client: AsyncClient, db_session: AsyncSession) -> None:
    session_id = await _create_session(db_session)
    event_types = ["PLAN", "TOOL_CALL", "TOOL_RESULT", "CODE_PROPOSED", "EXEC_START", "ERROR"]
    for et in event_types:
        await _create_event(db_session, session_id, et, "profiling")

    response = await client.get(f"/sessions/{session_id}/events")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 6
    returned_types = {e["event_type"] for e in data}
    assert returned_types == set(event_types)


@pytest.mark.asyncio
async def test_get_events_isolates_sessions(client: AsyncClient, db_session: AsyncSession) -> None:
    session_a = await _create_session(db_session, "Corp A")
    session_b = await _create_session(db_session, "Corp B")
    await _create_event(db_session, session_a, "PLAN", "step_a")
    await _create_event(db_session, session_b, "ERROR", "step_b")

    resp_a = await client.get(f"/sessions/{session_a}/events")
    resp_b = await client.get(f"/sessions/{session_b}/events")

    assert len(resp_a.json()) == 1
    assert resp_a.json()[0]["event_type"] == "PLAN"
    assert len(resp_b.json()) == 1
    assert resp_b.json()[0]["event_type"] == "ERROR"


@pytest.mark.asyncio
async def test_event_with_null_step(client: AsyncClient, db_session: AsyncSession) -> None:
    session_id = await _create_session(db_session)
    await _create_event(db_session, session_id, "PLAN", step=None)

    response = await client.get(f"/sessions/{session_id}/events")
    assert response.status_code == 200
    assert response.json()[0]["step"] is None


@pytest.mark.asyncio
async def test_event_with_complex_payload(client: AsyncClient, db_session: AsyncSession) -> None:
    session_id = await _create_session(db_session)
    payload = {
        "tools": ["data_ingest", "eda_plots"],
        "metrics": {"accuracy": 0.95, "f1": 0.88},
        "nested": {"a": {"b": 1}},
    }
    await _create_event(db_session, session_id, "TOOL_RESULT", "modeling", payload)

    response = await client.get(f"/sessions/{session_id}/events")
    assert response.status_code == 200
    data = response.json()[0]["payload"]
    assert data["tools"] == ["data_ingest", "eda_plots"]
    assert data["metrics"]["accuracy"] == 0.95
    assert data["nested"]["a"]["b"] == 1
