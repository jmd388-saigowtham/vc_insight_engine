"""Experiment tracking service — logs and compares training runs.

Provides structured tracking of ML experiments including parameters,
metrics, and artifacts. Enables run comparison and best-run selection.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.artifact import Artifact

logger = structlog.get_logger()


class ExperimentTracker:
    """Tracks ML training runs with parameters and metrics."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def log_run(
        self,
        session_id: uuid.UUID,
        run_name: str,
        parameters: dict[str, Any],
        metrics: dict[str, Any],
        model_type: str = "",
        artifacts: list[str] | None = None,
        notes: str = "",
    ) -> Artifact:
        """Log a training run."""
        run_metadata = {
            "run_type": "experiment",
            "run_name": run_name,
            "model_type": model_type,
            "parameters": parameters,
            "metrics": metrics,
            "artifacts": artifacts or [],
            "notes": notes,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        artifact = Artifact(
            id=uuid.uuid4(),
            session_id=session_id,
            artifact_type="experiment_run",
            name=f"run_{run_name}",
            storage_path="",
            metadata_=run_metadata,
            step="modeling",
        )
        self.db.add(artifact)
        await self.db.commit()
        await self.db.refresh(artifact)

        logger.info(
            "experiment_tracker.log_run",
            session_id=str(session_id),
            run_name=run_name,
        )
        return artifact

    async def list_runs(
        self, session_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        """List all experiment runs for a session."""
        stmt = (
            select(Artifact)
            .where(Artifact.session_id == session_id)
            .where(Artifact.artifact_type == "experiment_run")
            .order_by(Artifact.created_at.desc())
        )
        result = await self.db.execute(stmt)
        runs = []
        for artifact in result.scalars().all():
            meta = artifact.metadata_ or {}
            runs.append({
                "id": str(artifact.id),
                "run_name": meta.get("run_name", artifact.name),
                "model_type": meta.get("model_type", ""),
                "parameters": meta.get("parameters", {}),
                "metrics": meta.get("metrics", {}),
                "timestamp": meta.get("timestamp"),
                "notes": meta.get("notes", ""),
            })
        return runs

    async def compare_runs(
        self,
        session_id: uuid.UUID,
        metric: str = "f1_score",
    ) -> dict[str, Any]:
        """Compare all runs for a session, ranked by metric."""
        runs = await self.list_runs(session_id)
        if not runs:
            return {"runs": [], "best_run": None}

        sorted_runs = sorted(
            runs,
            key=lambda r: r.get("metrics", {}).get(metric, 0),
            reverse=True,
        )

        return {
            "runs": sorted_runs,
            "best_run": sorted_runs[0] if sorted_runs else None,
            "comparison_metric": metric,
        }

    async def get_best_run(
        self,
        session_id: uuid.UUID,
        metric: str = "f1_score",
    ) -> dict[str, Any] | None:
        """Get the best experiment run by metric."""
        comparison = await self.compare_runs(session_id, metric)
        return comparison.get("best_run")
