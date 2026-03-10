from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.artifact import Artifact
from app.models.session import Session


async def _create_session(db: AsyncSession) -> uuid.UUID:
    session_id = uuid.uuid4()
    session = Session(id=session_id, company_name="Artifact Corp")
    db.add(session)
    await db.commit()
    return session_id


async def _create_artifact(
    db: AsyncSession,
    session_id: uuid.UUID,
    name: str = "chart.png",
    artifact_type: str = "eda",
    storage_path: str = "/tmp/artifacts/chart.png",
    metadata: dict | None = None,
) -> Artifact:
    artifact = Artifact(
        id=uuid.uuid4(),
        session_id=session_id,
        artifact_type=artifact_type,
        name=name,
        storage_path=storage_path,
        metadata_=metadata or {"step": artifact_type, "title": name, "description": "Test"},
    )
    db.add(artifact)
    await db.commit()
    await db.refresh(artifact)
    return artifact


@pytest.mark.asyncio
async def test_list_artifacts_empty(client: AsyncClient, db_session: AsyncSession) -> None:
    session_id = await _create_session(db_session)

    response = await client.get(f"/sessions/{session_id}/artifacts")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_list_artifacts(client: AsyncClient, db_session: AsyncSession) -> None:
    session_id = await _create_session(db_session)
    await _create_artifact(db_session, session_id, "plot1.png", "eda")
    await _create_artifact(db_session, session_id, "plot2.png", "eda")

    response = await client.get(f"/sessions/{session_id}/artifacts")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


@pytest.mark.asyncio
async def test_list_artifacts_frontend_shape(client: AsyncClient, db_session: AsyncSession) -> None:
    session_id = await _create_session(db_session)
    await _create_artifact(
        db_session, session_id, "dist.png", "eda",
        metadata={"step": "eda", "title": "Distribution", "description": "Histogram"},
    )

    response = await client.get(f"/sessions/{session_id}/artifacts")
    assert response.status_code == 200
    item = response.json()[0]
    # Verify frontend-compatible shape
    assert "id" in item
    assert "session_id" in item
    assert "step" in item
    assert "artifact_type" in item
    assert "title" in item
    assert "description" in item
    assert item["step"] == "eda"
    assert item["title"] == "Distribution"
    assert item["artifact_type"] == "image"  # .png -> image


@pytest.mark.asyncio
async def test_list_artifacts_non_image_type(client: AsyncClient, db_session: AsyncSession) -> None:
    session_id = await _create_session(db_session)
    await _create_artifact(db_session, session_id, "report.json", "report", "/tmp/report.json")

    response = await client.get(f"/sessions/{session_id}/artifacts")
    data = response.json()[0]
    assert data["artifact_type"] == "report"  # non-image keeps original type
    assert data["file_path"] is None  # non-image has no file_path


@pytest.mark.asyncio
async def test_list_artifacts_image_has_file_path(client: AsyncClient, db_session: AsyncSession) -> None:
    session_id = await _create_session(db_session)
    art = await _create_artifact(db_session, session_id, "chart.png", "eda")

    response = await client.get(f"/sessions/{session_id}/artifacts")
    data = response.json()[0]
    assert data["file_path"] == f"/artifacts/{art.id}/file"


@pytest.mark.asyncio
async def test_list_artifacts_isolates_sessions(client: AsyncClient, db_session: AsyncSession) -> None:
    session_a = await _create_session(db_session)
    session_b = await _create_session(db_session)
    await _create_artifact(db_session, session_a, "a.png", "eda")
    await _create_artifact(db_session, session_b, "b.png", "modeling")

    resp_a = await client.get(f"/sessions/{session_a}/artifacts")
    resp_b = await client.get(f"/sessions/{session_b}/artifacts")
    assert len(resp_a.json()) == 1
    assert len(resp_b.json()) == 1


@pytest.mark.asyncio
async def test_get_artifact_by_id(client: AsyncClient, db_session: AsyncSession) -> None:
    session_id = await _create_session(db_session)
    art = await _create_artifact(db_session, session_id, "model.pkl", "modeling")

    response = await client.get(f"/artifacts/{art.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "model.pkl"
    assert data["artifact_type"] == "modeling"


@pytest.mark.asyncio
async def test_get_artifact_not_found(client: AsyncClient) -> None:
    fake_id = uuid.uuid4()
    response = await client.get(f"/artifacts/{fake_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_artifact_metadata_jsonb(client: AsyncClient, db_session: AsyncSession) -> None:
    session_id = await _create_session(db_session)
    meta = {
        "step": "modeling",
        "title": "Feature Importance",
        "description": "SHAP values",
        "metrics": {"accuracy": 0.92, "f1": 0.88},
    }
    art = await _create_artifact(db_session, session_id, "shap.png", "modeling", metadata=meta)

    response = await client.get(f"/artifacts/{art.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["metadata_"]["metrics"]["accuracy"] == 0.92
