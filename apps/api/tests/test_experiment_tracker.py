"""Tests for experiment tracking service."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import Session
from app.services.experiment_tracker import ExperimentTracker

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def session_id(db_session: AsyncSession) -> uuid.UUID:
    session = Session(
        id=uuid.uuid4(),
        company_name="ExperimentCo",
        industry="Healthcare",
        current_step="models",
    )
    db_session.add(session)
    await db_session.commit()
    return session.id


class TestExperimentTracker:
    async def test_log_and_list_runs(self, db_session, session_id):
        tracker = ExperimentTracker(db_session)

        await tracker.log_run(
            session_id=session_id,
            run_name="rf_v1",
            model_type="random_forest",
            parameters={"n_estimators": 100},
            metrics={"f1_score": 0.85, "auc_roc": 0.90},
        )

        runs = await tracker.list_runs(session_id)
        assert len(runs) == 1
        assert runs[0]["run_name"] == "rf_v1"
        assert runs[0]["metrics"]["f1_score"] == 0.85

    async def test_compare_runs(self, db_session, session_id):
        tracker = ExperimentTracker(db_session)

        await tracker.log_run(
            session_id=session_id,
            run_name="lr_v1",
            model_type="logistic_regression",
            parameters={"C": 1.0},
            metrics={"f1_score": 0.75},
        )
        await tracker.log_run(
            session_id=session_id,
            run_name="rf_v1",
            model_type="random_forest",
            parameters={"n_estimators": 100},
            metrics={"f1_score": 0.85},
        )
        await tracker.log_run(
            session_id=session_id,
            run_name="gb_v1",
            model_type="gradient_boosting",
            parameters={"n_estimators": 200},
            metrics={"f1_score": 0.82},
        )

        comparison = await tracker.compare_runs(session_id, metric="f1_score")
        assert len(comparison["runs"]) == 3
        assert comparison["best_run"]["run_name"] == "rf_v1"
        # Should be sorted descending by f1
        assert comparison["runs"][0]["metrics"]["f1_score"] >= comparison["runs"][1]["metrics"]["f1_score"]

    async def test_get_best_run(self, db_session, session_id):
        tracker = ExperimentTracker(db_session)

        await tracker.log_run(
            session_id=session_id,
            run_name="run1",
            model_type="rf",
            parameters={},
            metrics={"f1_score": 0.80},
        )
        await tracker.log_run(
            session_id=session_id,
            run_name="run2",
            model_type="gb",
            parameters={},
            metrics={"f1_score": 0.90},
        )

        best = await tracker.get_best_run(session_id, metric="f1_score")
        assert best is not None
        assert best["run_name"] == "run2"

    async def test_empty_tracker(self, db_session, session_id):
        tracker = ExperimentTracker(db_session)
        runs = await tracker.list_runs(session_id)
        assert runs == []

        best = await tracker.get_best_run(session_id)
        assert best is None
