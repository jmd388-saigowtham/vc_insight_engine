"""Tests for model registry service."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import Session
from app.services.model_registry import ModelRegistry

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def session_id(db_session: AsyncSession) -> uuid.UUID:
    session = Session(
        id=uuid.uuid4(),
        company_name="RegistryCo",
        industry="Fintech",
        current_step="models",
    )
    db_session.add(session)
    await db_session.commit()
    return session.id


class TestModelRegistry:
    async def test_register_and_list(self, db_session, session_id):
        registry = ModelRegistry(db_session)

        await registry.register_model(
            session_id=session_id,
            model_name="random_forest",
            metrics={"f1_score": 0.85, "auc_roc": 0.90},
            hyperparams={"n_estimators": 100, "max_depth": 10},
            feature_list=["age", "tenure", "usage"],
            threshold=0.45,
        )

        models = await registry.list_models(session_id)
        assert len(models) == 1
        assert models[0]["model_name"] == "random_forest"
        assert models[0]["metrics"]["f1_score"] == 0.85
        assert models[0]["threshold"] == 0.45

    async def test_get_model(self, db_session, session_id):
        registry = ModelRegistry(db_session)

        artifact = await registry.register_model(
            session_id=session_id,
            model_name="gradient_boosting",
            metrics={"f1_score": 0.88},
        )

        model = await registry.get_model(artifact.id)
        assert model is not None
        assert model["model_name"] == "gradient_boosting"

    async def test_get_model_not_found(self, db_session):
        registry = ModelRegistry(db_session)
        result = await registry.get_model(uuid.uuid4())
        assert result is None

    async def test_get_best_model(self, db_session, session_id):
        registry = ModelRegistry(db_session)

        await registry.register_model(
            session_id=session_id,
            model_name="logistic_regression",
            metrics={"f1_score": 0.75, "auc_roc": 0.80},
        )
        await registry.register_model(
            session_id=session_id,
            model_name="random_forest",
            metrics={"f1_score": 0.85, "auc_roc": 0.90},
        )
        await registry.register_model(
            session_id=session_id,
            model_name="gradient_boosting",
            metrics={"f1_score": 0.82, "auc_roc": 0.88},
        )

        best = await registry.get_best_model(session_id, metric="f1_score")
        assert best is not None
        assert best["model_name"] == "random_forest"

        best_auc = await registry.get_best_model(session_id, metric="auc_roc")
        assert best_auc is not None
        assert best_auc["model_name"] == "random_forest"

    async def test_empty_registry(self, db_session, session_id):
        registry = ModelRegistry(db_session)
        models = await registry.list_models(session_id)
        assert models == []

        best = await registry.get_best_model(session_id)
        assert best is None

    async def test_deployment_summary(self, db_session, session_id):
        registry = ModelRegistry(db_session)

        # Empty
        summary = await registry.deployment_summary(session_id)
        assert not summary["ready"]

        # With models
        await registry.register_model(
            session_id=session_id,
            model_name="rf",
            metrics={"f1_score": 0.85, "auc_roc": 0.90},
        )
        summary = await registry.deployment_summary(session_id)
        assert summary["ready"]
        assert summary["total_models"] == 1
