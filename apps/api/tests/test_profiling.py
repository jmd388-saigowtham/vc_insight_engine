from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.column_profile import ColumnProfile
from app.models.session import Session
from app.models.uploaded_file import UploadedFile


async def _create_session_and_file(db: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    """Helper: create a session and uploaded file, return (session_id, file_id)."""
    session_id = uuid.uuid4()
    file_id = uuid.uuid4()

    session = Session(
        id=session_id,
        company_name="Profile Corp",
        industry="Tech",
    )
    db.add(session)

    uploaded = UploadedFile(
        id=file_id,
        session_id=session_id,
        filename="data.csv",
        storage_path="/tmp/fake.csv",
        file_type="csv",
        size_bytes=1024,
        row_count=100,
        column_count=3,
    )
    db.add(uploaded)
    await db.commit()
    return session_id, file_id


async def _create_column_profile(
    db: AsyncSession,
    file_id: uuid.UUID,
    column_name: str = "age",
    dtype: str = "int64",
    description: str | None = None,
) -> ColumnProfile:
    profile = ColumnProfile(
        id=uuid.uuid4(),
        file_id=file_id,
        column_name=column_name,
        dtype=dtype,
        null_count=5,
        null_pct=5.0,
        unique_count=50,
        min_value="18",
        max_value="65",
        mean_value=35.2,
        sample_values=[25, 30, 45, 50, 60],
        description=description,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


@pytest.mark.asyncio
async def test_get_file_profile_empty(client: AsyncClient, db_session: AsyncSession) -> None:
    _, file_id = await _create_session_and_file(db_session)

    response = await client.get(f"/files/{file_id}/profile")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_get_file_profile_with_columns(client: AsyncClient, db_session: AsyncSession) -> None:
    _, file_id = await _create_session_and_file(db_session)
    await _create_column_profile(db_session, file_id, "age", "int64")
    await _create_column_profile(db_session, file_id, "name", "object")

    response = await client.get(f"/files/{file_id}/profile")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    names = {col["column_name"] for col in data}
    assert names == {"age", "name"}


@pytest.mark.asyncio
async def test_get_file_profile_returns_stats(client: AsyncClient, db_session: AsyncSession) -> None:
    _, file_id = await _create_session_and_file(db_session)
    await _create_column_profile(db_session, file_id, "score", "float64")

    response = await client.get(f"/files/{file_id}/profile")
    assert response.status_code == 200
    col = response.json()[0]
    assert col["column_name"] == "score"
    assert col["null_count"] == 5
    assert col["null_pct"] == 5.0
    assert col["unique_count"] == 50
    assert col["min_value"] == "18"
    assert col["max_value"] == "65"
    assert col["mean_value"] == 35.2


@pytest.mark.asyncio
async def test_update_column_description(client: AsyncClient, db_session: AsyncSession) -> None:
    _, file_id = await _create_session_and_file(db_session)
    profile = await _create_column_profile(db_session, file_id, "age", "int64")

    response = await client.patch(
        f"/columns/{profile.id}/description",
        json={"description": "Customer age in years"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["description"] == "Customer age in years"
    assert data["column_name"] == "age"


@pytest.mark.asyncio
async def test_update_column_description_not_found(client: AsyncClient) -> None:
    fake_id = uuid.uuid4()
    response = await client.patch(
        f"/columns/{fake_id}/description",
        json={"description": "Does not exist"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_session_tables(client: AsyncClient, db_session: AsyncSession) -> None:
    session_id, file_id = await _create_session_and_file(db_session)
    await _create_column_profile(db_session, file_id, "revenue", "float64")

    response = await client.get(f"/sessions/{session_id}/tables")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    table = data[0]
    assert table["filename"] == "data.csv"
    assert table["row_count"] == 100
    assert table["column_count"] == 3
    assert len(table["columns"]) == 1
    assert table["columns"][0]["column_name"] == "revenue"


@pytest.mark.asyncio
async def test_get_session_tables_empty(client: AsyncClient, db_session: AsyncSession) -> None:
    session_id = uuid.uuid4()
    session = Session(id=session_id, company_name="Empty Corp")
    db_session.add(session)
    await db_session.commit()

    response = await client.get(f"/sessions/{session_id}/tables")
    assert response.status_code == 200
    assert response.json() == []


class TestProfilingServiceSampling:
    """Test that profiling service has correct sampling configuration."""

    def test_sample_rows_is_100k(self) -> None:
        """Verify the SAMPLE_ROWS constant is 100,000."""
        from app.services.profiling_service import SAMPLE_ROWS
        assert SAMPLE_ROWS == 100_000

    def test_large_file_threshold_is_100mb(self) -> None:
        """Verify the LARGE_FILE_THRESHOLD constant is 100MB."""
        from app.services.profiling_service import LARGE_FILE_THRESHOLD
        assert LARGE_FILE_THRESHOLD == 100 * 1024 * 1024
