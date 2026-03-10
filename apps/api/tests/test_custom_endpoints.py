from __future__ import annotations

import json
import os
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import Session
from app.models.uploaded_file import UploadedFile


async def _create_session(
    db: AsyncSession,
    target_column: str | None = None,
    selected_features: list[str] | None = None,
) -> uuid.UUID:
    session_id = uuid.uuid4()
    session = Session(
        id=session_id,
        company_name="Custom Test Corp",
        target_column=target_column,
        selected_features=selected_features,
    )
    db.add(session)
    await db.commit()
    return session_id


async def _create_file(
    db: AsyncSession,
    session_id: uuid.UUID,
    storage_path: str,
    file_type: str = "csv",
) -> UploadedFile:
    f = UploadedFile(
        id=uuid.uuid4(),
        session_id=session_id,
        filename="test_data." + file_type,
        file_type=file_type,
        size_bytes=1024,
        storage_path=storage_path,
    )
    db.add(f)
    await db.commit()
    return f


def _write_model_results(artifacts_dir: str, models: list[dict]) -> None:
    os.makedirs(artifacts_dir, exist_ok=True)
    with open(os.path.join(artifacts_dir, "model_results.json"), "w") as f:
        json.dump(models, f)


# ===========================================================================
# POST /sessions/{id}/select-model
# ===========================================================================


@pytest.mark.asyncio
async def test_select_model_success(
    client: AsyncClient, db_session: AsyncSession, tmp_path
) -> None:
    session_id = await _create_session(db_session)

    artifacts_dir = str(tmp_path / str(session_id) / "artifacts")
    _write_model_results(artifacts_dir, [
        {"model_name": "random_forest", "is_best": True, "accuracy": 0.85},
        {"model_name": "logistic_regression", "is_best": False, "accuracy": 0.80},
    ])

    # Patch upload_dir to tmp_path
    from app.config import settings
    original = settings.upload_dir
    settings.upload_dir = str(tmp_path)
    try:
        resp = await client.post(
            f"/sessions/{session_id}/select-model",
            json={"model_name": "logistic_regression"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["selected_model"] == "logistic_regression"
        assert data["session_id"] == str(session_id)
    finally:
        settings.upload_dir = original


@pytest.mark.asyncio
async def test_select_model_session_not_found(client: AsyncClient) -> None:
    fake_id = uuid.uuid4()
    resp = await client.post(
        f"/sessions/{fake_id}/select-model",
        json={"model_name": "random_forest"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_select_model_no_results(
    client: AsyncClient, db_session: AsyncSession, tmp_path
) -> None:
    session_id = await _create_session(db_session)

    from app.config import settings
    original = settings.upload_dir
    settings.upload_dir = str(tmp_path)
    try:
        resp = await client.post(
            f"/sessions/{session_id}/select-model",
            json={"model_name": "random_forest"},
        )
        assert resp.status_code == 404
        assert "No model results" in resp.json()["detail"]
    finally:
        settings.upload_dir = original


@pytest.mark.asyncio
async def test_select_model_invalid_name(
    client: AsyncClient, db_session: AsyncSession, tmp_path
) -> None:
    session_id = await _create_session(db_session)

    artifacts_dir = str(tmp_path / str(session_id) / "artifacts")
    _write_model_results(artifacts_dir, [
        {"model_name": "random_forest", "is_best": True, "accuracy": 0.85},
    ])

    from app.config import settings
    original = settings.upload_dir
    settings.upload_dir = str(tmp_path)
    try:
        resp = await client.post(
            f"/sessions/{session_id}/select-model",
            json={"model_name": "nonexistent_model"},
        )
        assert resp.status_code == 400
        assert "not found" in resp.json()["detail"]
    finally:
        settings.upload_dir = original


# ===========================================================================
# POST /sessions/{id}/train-additional-model
# ===========================================================================


@pytest.mark.asyncio
async def test_train_additional_model_feedback_shim(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Deprecated endpoint now routes through feedback — accepts any model_type."""
    session_id = await _create_session(db_session)
    resp = await client.post(
        f"/sessions/{session_id}/train-additional-model",
        json={"model_type": "invalid_model"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "feedback_submitted"


@pytest.mark.asyncio
async def test_train_additional_model_session_not_found(
    client: AsyncClient,
) -> None:
    fake_id = uuid.uuid4()
    resp = await client.post(
        f"/sessions/{fake_id}/train-additional-model",
        json={"model_type": "random_forest"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_train_additional_model_no_target_feedback_shim(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Deprecated endpoint now routes through feedback — no target validation."""
    session_id = await _create_session(db_session, target_column=None)
    resp = await client.post(
        f"/sessions/{session_id}/train-additional-model",
        json={"model_type": "random_forest"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "feedback_submitted"


# ===========================================================================
# POST /sessions/{id}/eda/custom-plot
# ===========================================================================


@pytest.mark.asyncio
async def test_custom_plot_session_not_found(client: AsyncClient) -> None:
    fake_id = uuid.uuid4()
    resp = await client.post(
        f"/sessions/{fake_id}/eda/custom-plot",
        json={"request": "Show distribution of age"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_custom_plot_feedback_shim(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Deprecated endpoint now routes through feedback — no file validation."""
    session_id = await _create_session(db_session)
    resp = await client.post(
        f"/sessions/{session_id}/eda/custom-plot",
        json={"request": "Show distribution of age"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "feedback_submitted"


# ===========================================================================
# POST /sessions/{id}/hypotheses/custom
# ===========================================================================


@pytest.mark.asyncio
async def test_custom_hypothesis_session_not_found(client: AsyncClient) -> None:
    fake_id = uuid.uuid4()
    resp = await client.post(
        f"/sessions/{fake_id}/hypotheses/custom",
        json={
            "statement": "Age affects churn",
            "test_type": "t_test",
            "variables": ["age", "churn"],
        },
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_custom_hypothesis_feedback_shim(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Deprecated endpoint now routes through feedback — no input validation."""
    session_id = await _create_session(db_session)
    resp = await client.post(
        f"/sessions/{session_id}/hypotheses/custom",
        json={
            "statement": "Age affects churn",
            "test_type": "t_test",
            "variables": ["age", "churn"],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "feedback_submitted"


# ===========================================================================
# POST /sessions/{id}/retrain-threshold
# ===========================================================================


@pytest.mark.asyncio
async def test_retrain_threshold_session_not_found(client: AsyncClient) -> None:
    fake_id = uuid.uuid4()
    resp = await client.post(
        f"/sessions/{fake_id}/retrain-threshold",
        json={"model_name": "random_forest", "threshold": 0.6},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_retrain_threshold_feedback_shim(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Deprecated endpoint now routes through feedback — no threshold validation."""
    session_id = await _create_session(db_session)
    resp = await client.post(
        f"/sessions/{session_id}/retrain-threshold",
        json={"model_name": "random_forest", "threshold": 0.6},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "feedback_submitted"
