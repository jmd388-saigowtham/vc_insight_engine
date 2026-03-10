from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.preprocessing import LabelEncoder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.artifact import Artifact
from app.models.session import Session
from app.models.uploaded_file import UploadedFile
from app.schemas.event import TraceEventCreate
from app.services.event_service import EventService

import structlog

logger = structlog.get_logger()


class PipelineService:
    """Read-only service for accessing pipeline artifacts and session data.

    All execution is handled by the LangGraph agent (AgentService).
    This service provides read-only access to data files, artifacts,
    and analysis results stored on disk.
    """

    def __init__(self, db: AsyncSession, event_service: EventService):
        self.db = db
        self.event_service = event_service

    async def _emit(self, session_id: uuid.UUID, event_type: str, step: str, payload: dict):
        """Emit a trace event."""
        try:
            await self.event_service.emit(
                self.db,
                session_id,
                TraceEventCreate(event_type=event_type, step=step, payload=payload),
            )
        except Exception as e:
            logger.warning("Failed to emit event", error=str(e))

    async def _get_session(self, session_id: uuid.UUID) -> Session:
        session = await self.db.get(Session, session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        return session

    async def _get_files(self, session_id: uuid.UUID) -> list[UploadedFile]:
        stmt = select(UploadedFile).where(UploadedFile.session_id == session_id)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    def _load_dataframe(self, file: UploadedFile) -> pd.DataFrame:
        """Load a file into a pandas DataFrame."""
        file_path = Path(file.storage_path)
        if not file_path.exists():
            # Try relative to upload_dir
            file_path = Path(settings.upload_dir) / file.storage_path
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file.storage_path}")

        if file.file_type == "csv":
            return pd.read_csv(file_path, nrows=100000)
        elif file.file_type == "xlsx":
            return pd.read_excel(file_path, nrows=100000)
        raise ValueError(f"Unsupported file type: {file.file_type}")

    def _identify_target_column(self, df: pd.DataFrame) -> str | None:
        """Heuristic to find the best target variable."""
        # Look for common target column names
        target_names = [
            "churn", "target", "label", "class", "outcome", "churned",
            "is_churn", "attrition", "default", "fraud", "spam",
        ]
        for col in df.columns:
            if col.lower().strip() in target_names:
                return col

        # Look for binary columns with target-like values
        for col in df.columns:
            unique = df[col].nunique()
            if unique == 2 and df[col].dtype in ["object", "bool", "int64", "float64"]:
                vals = set(str(v).lower() for v in df[col].dropna().unique())
                if vals & {"yes", "no", "true", "false", "0", "1", "y", "n"}:
                    return col

        return None

    async def _get_artifact(self, session_id: uuid.UUID, name: str) -> Artifact | None:
        stmt = select(Artifact).where(
            Artifact.session_id == session_id,
            Artifact.name == name,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    # ============ READ-ONLY API HANDLERS ============

    async def get_opportunities(self, session_id: uuid.UUID) -> list[dict[str, Any]]:
        """Return value creation opportunities.

        Agent-data-first: reads from approved proposals, then session doc,
        then falls back to heuristic column scanning.
        """
        # --- Agent-data-first: check proposals ---
        try:
            from app.models.proposal import Proposal
            stmt = select(Proposal).where(
                Proposal.session_id == session_id,
                Proposal.step == "opportunity_analysis",
                Proposal.status == "approved",
            ).order_by(Proposal.created_at.desc()).limit(1)
            result = await self.db.execute(stmt)
            proposal = result.scalar_one_or_none()
            if proposal and proposal.plan:
                plan = proposal.plan
                options = plan.get("options") or plan.get("opportunities", [])
                if options:
                    opportunities = []
                    for opt in options:
                        opportunities.append({
                            "id": opt.get("id", str(uuid.uuid4())),
                            "title": opt.get("title", "Opportunity"),
                            "description": opt.get("description", ""),
                            "type": opt.get("type", "general"),
                            "confidence": opt.get("confidence", 0.0),
                            "key_metrics": opt.get("key_metrics", []),
                            "ai_reasoning": opt.get("reasoning", ""),
                        })
                    return opportunities
        except Exception as e:
            logger.debug("get_opportunities: proposal read failed", error=str(e))

        # --- Agent-data-first: check session doc ---
        try:
            from session_doc.server import get_section
            section = get_section(str(session_id), "Value Creation Analysis")
            if section and section != "_Pending_":
                import json as _json
                try:
                    parsed = _json.loads(section) if isinstance(section, str) else section
                    if isinstance(parsed, list) and parsed:
                        return parsed
                except (ValueError, TypeError):
                    pass
        except Exception as e:
            logger.debug("get_opportunities: session doc read failed", error=str(e))

        # DEPRECATED: heuristic fallback — remove after agent-data-first migration verified
        files = await self._get_files(session_id)
        if not files:
            return []

        try:
            df = self._load_dataframe(files[0])
        except Exception:
            return []

        opportunities: list[dict[str, Any]] = []
        target = self._identify_target_column(df)

        # Check for churn-related columns
        churn_cols = [
            c for c in df.columns if "churn" in c.lower() or "attrition" in c.lower()
        ]
        if churn_cols or (target and "churn" in target.lower()):
            target_col_for_rate = churn_cols[0] if churn_cols else target
            if target_col_for_rate:
                target_dist = df[target_col_for_rate].value_counts(normalize=True)
                churn_rate = float(target_dist.min()) if len(target_dist) == 2 else 0.25
            else:
                churn_rate = 0.25
            opportunities.append(
                {
                    "id": str(uuid.uuid4()),
                    "title": "Churn Prediction & Prevention",
                    "description": (
                        f"Predict customer churn with {churn_rate * 100:.0f}% base rate. "
                        "Identify at-risk customers and key churn drivers to enable "
                        "proactive retention strategies."
                    ),
                    "type": "churn",
                    "confidence": 0.92,
                    "key_metrics": ["Churn Rate", "Customer Lifetime Value", "Retention Cost"],
                }
            )

        # Check for revenue/spending columns
        rev_cols = [
            c
            for c in df.columns
            if any(
                kw in c.lower()
                for kw in (
                    "revenue", "spend", "amount", "value", "price",
                    "cost", "income", "mou", "rev", "charge", "fee",
                )
            )
        ]
        if rev_cols:
            opportunities.append(
                {
                    "id": str(uuid.uuid4()),
                    "title": "Revenue Expansion Analysis",
                    "description": (
                        f"Analyze {len(rev_cols)} revenue-related metrics to identify "
                        "upsell and cross-sell opportunities across the customer base."
                    ),
                    "type": "expansion",
                    "confidence": 0.78,
                    "key_metrics": [c[:30] for c in rev_cols[:3]],
                }
            )

        # Check for product/service columns
        prod_cols = [
            c
            for c in df.columns
            if any(
                kw in c.lower()
                for kw in ("product", "service", "plan", "subscription", "category")
            )
        ]
        if prod_cols:
            opportunities.append(
                {
                    "id": str(uuid.uuid4()),
                    "title": "Cross-Sell Optimization",
                    "description": (
                        "Identify which products and services are commonly purchased "
                        "together to optimize cross-selling strategies."
                    ),
                    "type": "cross_sell",
                    "confidence": 0.71,
                    "key_metrics": ["Product Penetration", "Bundle Rate", "Conversion"],
                }
            )

        # Always offer a general upsell opportunity
        opportunities.append(
            {
                "id": str(uuid.uuid4()),
                "title": "Customer Segmentation & Upsell",
                "description": (
                    f"Segment {df.shape[0]:,} customers to identify high-value "
                    "targets for premium tier migration."
                ),
                "type": "upsell",
                "confidence": 0.65,
                "key_metrics": ["ARPU", "Segment Size", "Upgrade Probability"],
            }
        )

        return opportunities

    async def get_target_config(self, session_id: uuid.UUID) -> dict[str, Any]:
        """Get target variable and feature configuration.

        Agent-data-first: uses session.target_column and proposal data
        before falling back to heuristic column matching.
        """
        session = await self._get_session(session_id)

        # --- Agent-data-first: session target_column ---
        agent_target = getattr(session, "target_column", None)
        ai_explanation = None
        alternatives = None

        if agent_target:
            # Try to get AI reasoning from proposals
            try:
                from app.models.proposal import Proposal
                stmt = select(Proposal).where(
                    Proposal.session_id == session_id,
                    Proposal.step == "target_id",
                ).order_by(Proposal.created_at.desc()).limit(1)
                result = await self.db.execute(stmt)
                proposal = result.scalar_one_or_none()
                if proposal:
                    ai_explanation = proposal.ai_reasoning
                    alternatives = proposal.alternatives
            except Exception as e:
                logger.debug("get_target_config: proposal read failed", error=str(e))

        # --- Fall through to heuristic if no agent target ---
        files = await self._get_files(session_id)
        if not files:
            raise ValueError("No files uploaded")
        df = self._load_dataframe(files[0])

        if agent_target and agent_target in df.columns:
            target = agent_target
        else:
            # DEPRECATED: heuristic fallback — remove after agent-data-first migration verified
            target = self._identify_target_column(df)
            if target is None:
                target = df.columns[-1]

        # Calculate feature importance using correlation with target
        target_series = df[target].copy()
        if target_series.dtype == "object" or target_series.dtype.name in ("string", "str", "StringDtype"):
            le = LabelEncoder()
            target_series = pd.Series(le.fit_transform(target_series.astype(str)))

        features: list[dict[str, Any]] = []
        for col in df.columns:
            if col == target:
                continue
            try:
                if df[col].dtype in ["int64", "float64"]:
                    corr = abs(float(df[col].corr(target_series)))
                    if np.isnan(corr):
                        corr = 0.0
                else:
                    corr = 0.3  # Default for categorical
                features.append(
                    {
                        "name": col,
                        "included": corr > 0.01,
                        "importance": round(min(corr, 1.0), 3),
                    }
                )
            except Exception:
                features.append({"name": col, "included": True, "importance": 0.1})

        # Sort by importance
        features.sort(key=lambda x: x["importance"], reverse=True)

        # Get preview rows
        preview_df = df.head(5).fillna("")
        preview: list[dict[str, Any]] = []
        for _, row in preview_df.iterrows():
            preview.append({k: str(v) for k, v in row.items()})

        return {
            "target_variable": target,
            "features": features,
            "preview": preview,
            "ai_explanation": ai_explanation,
            "alternatives": alternatives,
        }

    async def get_hypotheses(
        self, session_id: uuid.UUID, with_results: bool = False
    ) -> list[dict[str, Any]]:
        """Get hypotheses from stored artifacts or session doc (read-only)."""
        artifact = await self._get_artifact(session_id, "hypotheses.json")

        if artifact is not None:
            try:
                with open(artifact.storage_path) as f:
                    return json.load(f)
            except Exception:
                pass

        # Fallback: read from session doc metadata
        try:
            import sys
            mcp_path = str(Path(__file__).resolve().parents[5] / "packages" / "mcp-servers" / "src")
            if mcp_path not in sys.path:
                sys.path.insert(0, mcp_path)
            from session_doc.server import get_section_metadata
            meta = get_section_metadata(str(session_id), "Hypotheses & Results")
            if meta and "hypotheses" in meta:
                hypotheses = []
                for i, h in enumerate(meta["hypotheses"]):
                    supported = h.get("conclusion", "").lower() in ("supported", "support")
                    hypotheses.append({
                        "id": f"h-{i}",
                        "session_id": str(session_id),
                        "statement": h.get("statement", ""),
                        "test_type": h.get("test_type", "unknown"),
                        "variables": h.get("variables", []),
                        "expected_outcome": h.get("expected_outcome", ""),
                        "status": "approved",
                        "result": {
                            "test_statistic": h.get("test_statistic", 0.0),
                            "p_value": h.get("p_value", 0.0),
                            "conclusion": h.get("conclusion", ""),
                            "supported": supported,
                        },
                    })
                return hypotheses
        except Exception as e:
            logger.debug("get_hypotheses: session doc read failed", error=str(e))

        return []

    async def update_hypothesis(self, hypothesis_id: str, status: str) -> dict[str, Any]:
        """Update hypothesis status."""
        # Find the hypothesis in artifacts
        stmt = select(Artifact).where(Artifact.name == "hypotheses.json")
        result = await self.db.execute(stmt)
        artifacts = list(result.scalars().all())

        for artifact in artifacts:
            try:
                with open(artifact.storage_path) as f:
                    hypotheses = json.load(f)

                for h in hypotheses:
                    if h["id"] == hypothesis_id:
                        h["status"] = status
                        with open(artifact.storage_path, "w") as f:
                            json.dump(hypotheses, f, indent=2)
                        return h
            except Exception:
                continue

        raise ValueError(f"Hypothesis {hypothesis_id} not found")

    async def get_models(self, session_id: uuid.UUID) -> list[dict[str, Any]]:
        """Get model results from stored artifacts or model registry."""
        # Try model_results.json artifact first
        artifact = await self._get_artifact(session_id, "model_results.json")
        if artifact is not None:
            try:
                with open(artifact.storage_path) as f:
                    return json.load(f)
            except Exception:
                pass

        # Fallback: load from model registry (Artifact table with type='model')
        from app.services.model_registry import ModelRegistry
        registry = ModelRegistry(db=self.db)
        registered = await registry.list_models(session_id)
        if not registered:
            return []

        # Find best model by F1 score
        best_f1 = -1.0
        best_name = None
        for m in registered:
            f1 = m.get("metrics", {}).get("f1", m.get("metrics", {}).get("f1_score", 0))
            if f1 > best_f1:
                best_f1 = f1
                best_name = m["model_name"]

        results = []
        for m in registered:
            metrics = m.get("metrics", {})
            results.append({
                "id": m.get("id", ""),
                "session_id": str(session_id),
                "model_name": m["model_name"],
                "accuracy": metrics.get("accuracy", 0),
                "precision": metrics.get("precision", 0),
                "recall": metrics.get("recall", 0),
                "f1_score": metrics.get("f1", metrics.get("f1_score", 0)),
                "auc_roc": metrics.get("auc_roc", metrics.get("roc_auc", 0)),
                "is_best": m["model_name"] == best_name,
                "model_path": m.get("storage_path", ""),
                "diagnostics": {},
            })
        return results

    async def get_report(self, session_id: uuid.UUID) -> dict[str, Any] | None:
        """Get report from stored artifacts (read-only)."""
        artifact = await self._get_artifact(session_id, "report.json")

        if artifact is not None:
            try:
                with open(artifact.storage_path) as f:
                    return json.load(f)
            except Exception:
                pass

        # Fallback: read from disk (agent writes report.json to artifacts dir)
        report_path = Path(settings.upload_dir) / str(session_id) / "artifacts" / "report.json"
        if report_path.exists():
            try:
                with open(report_path) as f:
                    return json.load(f)
            except Exception:
                pass

        return None
