"""Model registry service — tracks trained models with metadata.

Provides a central registry for all models trained during a session,
including hyperparameters, metrics, threshold, feature list, and
training date.
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


class ModelRegistry:
    """Registry for trained ML models within a session."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def register_model(
        self,
        session_id: uuid.UUID,
        model_name: str,
        model_path: str | None = None,
        metrics: dict[str, Any] | None = None,
        hyperparams: dict[str, Any] | None = None,
        feature_list: list[str] | None = None,
        threshold: float = 0.5,
        metadata: dict[str, Any] | None = None,
    ) -> Artifact:
        """Register a trained model as an artifact with metadata."""
        model_metadata = {
            "model_name": model_name,
            "metrics": metrics or {},
            "hyperparams": hyperparams or {},
            "feature_list": feature_list or [],
            "threshold": threshold,
            "training_date": datetime.now(timezone.utc).isoformat(),
            **(metadata or {}),
        }

        artifact = Artifact(
            id=uuid.uuid4(),
            session_id=session_id,
            artifact_type="model",
            name=f"model_{model_name}",
            storage_path=model_path or "",
            metadata_=model_metadata,
            step="modeling",
        )
        self.db.add(artifact)
        await self.db.commit()
        await self.db.refresh(artifact)

        logger.info(
            "model_registry.register",
            session_id=str(session_id),
            model_name=model_name,
        )
        return artifact

    async def list_models(
        self, session_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        """List all registered models for a session."""
        stmt = (
            select(Artifact)
            .where(Artifact.session_id == session_id)
            .where(Artifact.artifact_type == "model")
            .order_by(Artifact.created_at.desc())
        )
        result = await self.db.execute(stmt)
        models = []
        for artifact in result.scalars().all():
            meta = artifact.metadata_ or {}
            models.append({
                "id": str(artifact.id),
                "model_name": meta.get("model_name", artifact.name),
                "metrics": meta.get("metrics", {}),
                "hyperparams": meta.get("hyperparams", {}),
                "feature_list": meta.get("feature_list", []),
                "threshold": meta.get("threshold", 0.5),
                "training_date": meta.get("training_date"),
                "storage_path": artifact.storage_path,
            })
        return models

    async def get_model(
        self, model_id: uuid.UUID
    ) -> dict[str, Any] | None:
        """Get a specific model by artifact ID."""
        artifact = await self.db.get(Artifact, model_id)
        if not artifact or artifact.artifact_type != "model":
            return None

        meta = artifact.metadata_ or {}
        return {
            "id": str(artifact.id),
            "model_name": meta.get("model_name", artifact.name),
            "metrics": meta.get("metrics", {}),
            "hyperparams": meta.get("hyperparams", {}),
            "feature_list": meta.get("feature_list", []),
            "threshold": meta.get("threshold", 0.5),
            "training_date": meta.get("training_date"),
            "storage_path": artifact.storage_path,
        }

    async def get_best_model(
        self, session_id: uuid.UUID, metric: str = "f1_score"
    ) -> dict[str, Any] | None:
        """Get the best model for a session based on a metric."""
        models = await self.list_models(session_id)
        if not models:
            return None

        return max(
            models,
            key=lambda m: m.get("metrics", {}).get(metric, 0),
        )

    async def deployment_summary(
        self, session_id: uuid.UUID
    ) -> dict[str, Any]:
        """Generate a deployment-readiness summary."""
        models = await self.list_models(session_id)
        if not models:
            return {"ready": False, "reason": "No models trained"}

        best = await self.get_best_model(session_id)
        return {
            "ready": True,
            "total_models": len(models),
            "best_model": best,
            "all_models": [
                {
                    "name": m["model_name"],
                    "f1": m["metrics"].get("f1_score", 0),
                    "auc_roc": m["metrics"].get("auc_roc", 0),
                }
                for m in models
            ],
        }
