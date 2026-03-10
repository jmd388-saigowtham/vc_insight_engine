from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.graph import compiled_graph
from app.agent.state import AgentState
from app.config import settings
from app.models.artifact import Artifact
from app.models.code_proposal import CodeProposal
from app.models.column_profile import ColumnProfile
from app.models.proposal import Proposal
from app.models.session import Session
from app.models.uploaded_file import UploadedFile
from app.models.user_feedback import UserFeedback
from app.schemas.event import TraceEventCreate
from app.services.dataset_registry import DatasetRegistry
from app.services.event_service import EventService
from app.services.step_state_service import StepStateService

logger = structlog.get_logger()


class AgentService:
    def __init__(self, db: AsyncSession, event_service: EventService):
        self.db = db
        self.event_service = event_service
        self.step_state_service = StepStateService(db, event_service)

    async def _emit(self, session_id: uuid.UUID, event_type: str, step: str, payload: dict):
        try:
            await self.event_service.emit(
                self.db,
                session_id,
                TraceEventCreate(event_type=event_type, step=step, payload=payload),
            )
        except Exception as e:
            logger.warning("Failed to emit event", error=str(e))

    async def _build_initial_state(self, session_id: uuid.UUID) -> AgentState:
        """Build the initial AgentState from database records."""
        session = await self.db.get(Session, session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        stmt = select(UploadedFile).where(UploadedFile.session_id == session_id)
        result = await self.db.execute(stmt)
        files = list(result.scalars().all())

        uploaded_files: list[dict[str, Any]] = []
        for f in files:
            storage_path = f.storage_path
            p = Path(storage_path)
            if not p.is_absolute():
                # Resolve relative paths to absolute so downstream nodes
                # don't double-prepend upload_dir
                if p.exists():
                    storage_path = str(p.resolve())
                else:
                    full = Path(settings.upload_dir) / storage_path
                    if full.exists():
                        storage_path = str(full.resolve())
                    else:
                        # Try just the filename
                        name_only = Path(settings.upload_dir) / p.name
                        if name_only.exists():
                            storage_path = str(name_only.resolve())
            uploaded_files.append({
                "id": str(f.id),
                "filename": f.filename,
                "file_type": f.file_type,
                "storage_path": storage_path,
                "row_count": f.row_count,
                "column_count": f.column_count,
            })

        # Load column profiles from DB
        column_profiles: list[dict[str, Any]] = []
        file_ids = [f.id for f in files]
        if file_ids:
            profile_stmt = (
                select(ColumnProfile)
                .where(ColumnProfile.file_id.in_(file_ids))
                .order_by(ColumnProfile.column_name)
            )
            profile_result = await self.db.execute(profile_stmt)
            for cp in profile_result.scalars().all():
                column_profiles.append({
                    "file_id": str(cp.file_id),
                    "column_name": cp.column_name,
                    "data_type": cp.dtype,
                    "null_count": cp.null_count,
                    "null_pct": cp.null_pct,
                    "unique_count": cp.unique_count,
                    "min_value": cp.min_value,
                    "max_value": cp.max_value,
                    "mean_value": cp.mean_value,
                    "sample_values": cp.sample_values,
                    "description": cp.description,
                })

        # Get step states (with backward compat)
        step_states = await self.step_state_service.get_states(session_id)

        # Get target_column and selected_features from session if available
        target_column = getattr(session, "target_column", "") or ""
        selected_features = getattr(session, "selected_features", None) or []

        # Initialize and read session doc
        session_doc = ""
        try:
            from session_doc.server import initialize, read
            # Ensure session doc is created with scaffolding at session start
            initialize(
                str(session_id),
                company_name=session.company_name or "",
                industry=getattr(session, "industry", ""),
                business_context=session.business_context or "",
            )
            doc = read(str(session_id))
            session_doc = doc.document
        except Exception:
            pass

        # Generate unique run_id for this invocation
        run_id = str(uuid.uuid4())

        # ── Load persisted dataset paths from dataset_registry ──
        merged_df_path = ""
        cleaned_df_path = ""
        features_df_path = ""
        try:
            dataset_registry = DatasetRegistry(self.db)
            merged_ds = await dataset_registry.get_latest(session_id, "merged")
            if merged_ds and merged_ds.file_path and Path(merged_ds.file_path).exists():
                merged_df_path = merged_ds.file_path

            preprocessed_ds = await dataset_registry.get_latest(session_id, "preprocessed")
            if preprocessed_ds and preprocessed_ds.file_path and Path(preprocessed_ds.file_path).exists():
                cleaned_df_path = preprocessed_ds.file_path

            features_ds = await dataset_registry.get_latest(session_id, "features")
            if features_ds and features_ds.file_path and Path(features_ds.file_path).exists():
                features_df_path = features_ds.file_path
        except Exception as e:
            logger.warning("Failed to load dataset paths from registry", error=str(e))

        # ── Load persisted model results from model_registry ──
        model_results: dict[str, Any] = {}
        try:
            from app.services.model_registry import ModelRegistry
            model_reg = ModelRegistry(self.db)
            registered_models = await model_reg.list_models(session_id)
            if registered_models:
                model_dicts = []
                best_model_name = None
                best_f1 = -1.0
                for rm in registered_models:
                    m_dict = {
                        "model_name": rm["model_name"],
                        "model_path": rm["storage_path"],
                        "metrics": rm.get("metrics", {}),
                        "best": False,
                    }
                    f1 = rm.get("metrics", {}).get("f1", rm.get("metrics", {}).get("f1_score", 0))
                    if f1 > best_f1:
                        best_f1 = f1
                        best_model_name = rm["model_name"]
                    model_dicts.append(m_dict)
                # Mark best
                for m_dict in model_dicts:
                    if m_dict["model_name"] == best_model_name:
                        m_dict["best"] = True
                model_results = {
                    "models": model_dicts,
                    "best_model": best_model_name,
                    "output_dir": str(Path(settings.upload_dir) / str(session_id) / "models"),
                }
        except Exception as e:
            logger.warning("Failed to load model results from registry", error=str(e))

        state: AgentState = {
            "session_id": session_id,
            "company_name": session.company_name or "",
            "industry": getattr(session, "industry", ""),
            "business_context": session.business_context or "",
            "current_step": "profiling",
            "uploaded_files": uploaded_files,
            "column_profiles": column_profiles,
            "merge_plan": {},
            "merged_df_path": merged_df_path,
            "target_column": target_column,
            "selected_features": selected_features,
            "eda_results": {},
            "preprocessing_plan": {},
            "cleaned_df_path": cleaned_df_path,
            "hypotheses": [],
            "feature_plan": {},
            "features_df_path": features_df_path,
            "model_results": model_results,
            "explainability_results": {},
            "recommendations": [],
            "report_path": "",
            "next_action": "",
            "llm_plan": "",
            "awaiting_approval": None,
            "step_states": step_states,
            "session_doc": session_doc,
            # Approval gate fields
            "pending_step": "",
            "pending_code": "",
            "pending_code_description": "",
            "approval_status": "",
            "approved_code": "",
            "denial_counts": {},
            # Business-logic proposal gate
            "pending_proposal_step": "",
            "pending_proposal_plan": {},
            "pending_proposal_summary": "",
            "pending_proposal_reasoning": "",
            "pending_proposal_alternatives": [],
            "pending_proposal_type": "",
            "proposal_status": "",
            "proposal_feedback": "",
            "proposal_revision_count": {},
            "user_feedback": {},
            # New pipeline stage results
            "data_understanding_summary": {},
            "opportunity_recommendations": [],
            "selected_opportunity": {},
            "dtype_decisions": {},
            "threshold_config": {},
            # LLM-driven orchestration
            "orchestrator_reasoning": "",
            "strategy_hint": "",
            "orchestrator_candidates": [],
            "orchestrator_reflection": "",
            "run_id": run_id,
            "denial_feedback": {},
            "node_plans": {},
            "pending_context": {},
            "error": None,
            "trace_events": [],
            "_loop_history": [],
        }

        return state

    async def _create_code_proposal(
        self,
        session_id: uuid.UUID,
        step: str,
        code: str,
        description: str,
        context: dict[str, Any] | None = None,
    ) -> CodeProposal:
        """Create a CodeProposal in the DB and emit CODE_PROPOSED event."""
        proposal = CodeProposal(
            id=uuid.uuid4(),
            session_id=session_id,
            step=step,
            code=code,
            language="python",
            status="pending",
            description=description,
            context=context,
        )
        self.db.add(proposal)
        await self.db.commit()
        await self.db.refresh(proposal)

        payload: dict[str, Any] = {
            "proposal_id": str(proposal.id),
            "code": code,
            "language": "python",
            "description": description,
        }
        if context:
            payload["context"] = context

        await self._emit(session_id, "CODE_PROPOSED", step, payload)

        logger.info(
            "agent_service: code proposal created",
            session_id=str(session_id),
            proposal_id=str(proposal.id),
            step=step,
        )
        return proposal

    async def _create_business_proposal(
        self,
        session_id: uuid.UUID,
        step: str,
        proposal_type: str,
        plan: dict[str, Any],
        summary: str,
        reasoning: str,
        alternatives: list[dict[str, Any]] | None = None,
        parent_id: uuid.UUID | None = None,
        version: int = 1,
    ) -> Proposal:
        """Create a business-logic Proposal in the DB and emit event."""
        proposal = Proposal(
            id=uuid.uuid4(),
            session_id=session_id,
            step=step,
            proposal_type=proposal_type,
            status="pending",
            version=version,
            plan=plan,
            summary=summary,
            ai_reasoning=reasoning,
            alternatives=alternatives,
            parent_id=parent_id,
        )
        self.db.add(proposal)
        await self.db.commit()
        await self.db.refresh(proposal)

        await self._emit(
            session_id,
            "PROPOSAL_CREATED",
            step,
            {
                "proposal_id": str(proposal.id),
                "proposal_type": proposal_type,
                "version": version,
                "summary": summary,
            },
        )

        logger.info(
            "agent_service: business proposal created",
            session_id=str(session_id),
            proposal_id=str(proposal.id),
            step=step,
            proposal_type=proposal_type,
        )
        return proposal

    async def _load_user_feedback(
        self, session_id: uuid.UUID
    ) -> dict[str, list[str]]:
        """Load pending user feedback grouped by step."""
        stmt = (
            select(UserFeedback)
            .where(UserFeedback.session_id == session_id)
            .where(UserFeedback.status == "pending")
            .order_by(UserFeedback.created_at.asc())
        )
        result = await self.db.execute(stmt)
        feedback_map: dict[str, list[str]] = {}
        for fb in result.scalars().all():
            key = fb.step or "general"
            feedback_map.setdefault(key, []).append(fb.message)
        return feedback_map

    async def _persist_step_states(
        self, session_id: uuid.UUID, final_state: AgentState
    ) -> None:
        """Persist step_states from the final agent state to the DB."""
        step_states = final_state.get("step_states")
        if step_states:
            try:
                await self.step_state_service.update_states(session_id, step_states)
            except Exception as e:
                logger.warning("Failed to persist step_states", error=str(e))

        # Advance current_step based on furthest DONE pipeline step
        await self._advance_current_step(session_id, final_state)

        # Persist target_column and selected_features to Session
        await self._persist_session_fields(session_id, final_state)

        # Persist artifacts (EDA plots, SHAP plots, etc.) to DB
        await self._persist_artifacts(session_id, final_state)

        # Register datasets produced during the pipeline
        await self._register_datasets(session_id, final_state)

    async def _persist_artifacts(
        self, session_id: uuid.UUID, final_state: AgentState
    ) -> None:
        """Create Artifact DB records for files produced by agent nodes."""
        try:
            created = 0

            # EDA plots
            eda_results = final_state.get("eda_results", {})
            eda_plots = eda_results.get("plots", [])
            for plot in eda_plots:
                if not plot.get("success"):
                    continue
                plot_path = plot.get("plot_path", "")
                if not plot_path or not Path(plot_path).exists():
                    continue
                # Check if artifact already registered (idempotent)
                stmt = select(Artifact).where(
                    Artifact.session_id == session_id,
                    Artifact.storage_path == plot_path,
                )
                existing = (await self.db.execute(stmt)).scalar_one_or_none()
                if existing:
                    continue
                name = Path(plot_path).name
                artifact = Artifact(
                    id=uuid.uuid4(),
                    session_id=session_id,
                    artifact_type="eda",
                    name=name,
                    storage_path=plot_path,
                    step="eda",
                    metadata_={
                        "step": "eda",
                        "plot_type": plot.get("plot_type", "unknown"),
                        "title": plot.get("description", name),
                        "description": plot.get("description", ""),
                    },
                )
                self.db.add(artifact)
                created += 1

            # Explainability / SHAP plots
            shap_results = final_state.get("explainability_results", {})
            summary_plot = shap_results.get("summary_plot_path", "")
            if summary_plot and Path(summary_plot).exists():
                stmt = select(Artifact).where(
                    Artifact.session_id == session_id,
                    Artifact.storage_path == summary_plot,
                )
                existing = (await self.db.execute(stmt)).scalar_one_or_none()
                if not existing:
                    artifact = Artifact(
                        id=uuid.uuid4(),
                        session_id=session_id,
                        artifact_type="shap",
                        name=Path(summary_plot).name,
                        storage_path=summary_plot,
                        step="explainability",
                        metadata_={
                            "step": "explainability",
                            "plot_type": "shap_summary",
                            "title": "SHAP Summary Plot",
                            "description": f"SHAP feature importance for {shap_results.get('model_name', 'best model')}",
                        },
                    )
                    self.db.add(artifact)
                    created += 1

            for wp in shap_results.get("waterfall_plots", []):
                wp_path = wp if isinstance(wp, str) else wp.get("path", "")
                if not wp_path or not Path(wp_path).exists():
                    continue
                stmt = select(Artifact).where(
                    Artifact.session_id == session_id,
                    Artifact.storage_path == wp_path,
                )
                existing = (await self.db.execute(stmt)).scalar_one_or_none()
                if existing:
                    continue
                artifact = Artifact(
                    id=uuid.uuid4(),
                    session_id=session_id,
                    artifact_type="shap",
                    name=Path(wp_path).name,
                    storage_path=wp_path,
                    step="explainability",
                    metadata_={
                        "step": "explainability",
                        "plot_type": "shap_waterfall",
                        "title": f"SHAP Waterfall - {Path(wp_path).stem}",
                        "description": "SHAP waterfall plot for individual prediction",
                    },
                )
                self.db.add(artifact)
                created += 1

            if created:
                await self.db.commit()
                logger.info(
                    "agent_service: persisted artifacts",
                    session_id=str(session_id),
                    count=created,
                )
        except Exception as e:
            logger.warning("Failed to persist artifacts", error=str(e))

    async def _advance_current_step(
        self, session_id: uuid.UUID, final_state: AgentState
    ) -> None:
        """Compute and advance Session.current_step based on furthest DONE step.

        Maps pipeline steps to UI steps and only advances (never regresses).
        """
        from app.services.step_state_service import DONE, STEP_ORDER

        PIPELINE_TO_UI_MAP = {
            "profiling": "profiling",
            "data_understanding": "workspace",
            "dtype_handling": "workspace",
            "merge_planning": "workspace",
            "opportunity_analysis": "workspace",
            "target_id": "target",
            "feature_selection": "feature-selection",
            "eda": "eda",
            "preprocessing": "eda",
            "hypothesis": "hypotheses",
            "feature_eng": "hypotheses",
            "modeling": "models",
            "threshold_calibration": "models",
            "explainability": "shap",
            "recommendation": "report",
            "report": "report",
        }

        UI_STEP_ORDER = [
            "onboarding", "upload", "profiling", "workspace", "target",
            "feature-selection", "eda", "hypotheses", "hypothesis-results",
            "models", "shap", "report",
        ]

        step_states = final_state.get("step_states", {})

        # Find furthest DONE pipeline step
        furthest_ui_step = None
        for pipeline_step in reversed(STEP_ORDER):
            if step_states.get(pipeline_step) == DONE:
                ui_step = PIPELINE_TO_UI_MAP.get(pipeline_step)
                if ui_step:
                    furthest_ui_step = ui_step
                    break

        if not furthest_ui_step:
            return

        try:
            session = await self.db.get(Session, session_id)
            if not session:
                return

            current = session.current_step or "onboarding"
            current_idx = (
                UI_STEP_ORDER.index(current) if current in UI_STEP_ORDER else 0
            )
            new_idx = (
                UI_STEP_ORDER.index(furthest_ui_step)
                if furthest_ui_step in UI_STEP_ORDER
                else 0
            )

            # Only advance, never regress
            if new_idx > current_idx:
                session.current_step = furthest_ui_step
                await self.db.commit()
                logger.info(
                    "agent_service: advanced current_step",
                    session_id=str(session_id),
                    from_step=current,
                    to_step=furthest_ui_step,
                )
        except Exception as e:
            logger.warning("Failed to advance current_step", error=str(e))

    async def _persist_session_fields(
        self, session_id: uuid.UUID, final_state: AgentState
    ) -> None:
        """Persist target_column and selected_features to Session DB."""
        try:
            session = await self.db.get(Session, session_id)
            if not session:
                return

            changed = False

            target = final_state.get("target_column", "")
            if target and target != (session.target_column or ""):
                session.target_column = target
                changed = True

            features = final_state.get("selected_features", [])
            if features and features != (session.selected_features or []):
                session.selected_features = features
                changed = True

            if changed:
                await self.db.commit()
                logger.info(
                    "agent_service: persisted session fields",
                    session_id=str(session_id),
                    target_column=target or "(unchanged)",
                    features_count=len(features) if features else "(unchanged)",
                )
        except Exception as e:
            logger.warning("Failed to persist session fields", error=str(e))

    async def _register_datasets(
        self, session_id: uuid.UUID, final_state: AgentState
    ) -> None:
        """Register any new datasets created during pipeline execution."""
        registry = DatasetRegistry(self.db)

        try:
            # Register merged dataset
            merged_path = final_state.get("merged_df_path", "")
            merge_plan = final_state.get("merge_plan", {})
            if merged_path and merge_plan.get("status") == "merged":
                existing = await registry.get_latest(session_id, "merged")
                if not existing or existing.file_path != merged_path:
                    await registry.register(
                        session_id=session_id,
                        source_type="merged",
                        name=Path(merged_path).name,
                        file_path=merged_path,
                        row_count=merge_plan.get("output_rows"),
                        column_count=merge_plan.get("output_columns"),
                        metadata={"merge_plan": merge_plan},
                    )

            # Register preprocessed dataset
            cleaned_path = final_state.get("cleaned_df_path", "")
            if cleaned_path:
                existing = await registry.get_latest(session_id, "preprocessed")
                if not existing or existing.file_path != cleaned_path:
                    await registry.register(
                        session_id=session_id,
                        source_type="preprocessed",
                        name=Path(cleaned_path).name,
                        file_path=cleaned_path,
                    )

            # Register feature-engineered dataset
            features_path = final_state.get("features_df_path", "")
            if features_path:
                existing = await registry.get_latest(session_id, "features")
                if not existing or existing.file_path != features_path:
                    await registry.register(
                        session_id=session_id,
                        source_type="features",
                        name=Path(features_path).name,
                        file_path=features_path,
                    )
        except Exception as e:
            logger.warning("Failed to register datasets", error=str(e))

    async def _handle_final_state(
        self, session_id: uuid.UUID, final_state: AgentState, step: str
    ) -> dict:
        """Common logic for handling the final state after graph invocation."""
        # Persist step_states to DB
        await self._persist_step_states(session_id, final_state)

        # Check if a node is proposing a business-logic plan for approval
        pending_proposal_plan = final_state.get("pending_proposal_plan")
        pending_proposal_step = final_state.get("pending_proposal_step")
        if pending_proposal_plan and pending_proposal_step:
            proposal = await self._create_business_proposal(
                session_id=session_id,
                step=pending_proposal_step,
                proposal_type=final_state.get("pending_proposal_type", "generic"),
                plan=pending_proposal_plan,
                summary=final_state.get("pending_proposal_summary", ""),
                reasoning=final_state.get("pending_proposal_reasoning", ""),
                alternatives=final_state.get("pending_proposal_alternatives"),
            )
            await self._emit(
                session_id,
                "INFO",
                pending_proposal_step,
                {"message": "Pipeline paused — waiting for plan approval"},
            )
            return {
                "session_id": str(session_id),
                "status": "waiting_proposal",
                "proposal_id": str(proposal.id),
                "proposal_type": final_state.get("pending_proposal_type", "generic"),
            }

        # Check if a node is proposing code for approval
        pending_code = final_state.get("pending_code")
        pending_step = final_state.get("pending_step")
        if pending_code and pending_step:
            # Extract context from pending_context
            pending_context = final_state.get("pending_context") or None
            proposal = await self._create_code_proposal(
                session_id=session_id,
                step=pending_step,
                code=pending_code,
                description=final_state.get("pending_code_description", ""),
                context=pending_context,
            )
            await self._emit(
                session_id, "INFO", pending_step,
                {"message": "Pipeline paused — waiting for code approval"},
            )
            return {
                "session_id": str(session_id),
                "status": "waiting",
                "proposal_id": str(proposal.id),
            }

        error = final_state.get("error")
        if error:
            await self._emit(
                session_id, "ERROR", final_state.get("current_step", step),
                {"message": f"Pipeline error: {error}"},
            )
            return {"session_id": str(session_id), "status": "error", "error": error}

        await self._emit(
            session_id, "PLAN", "pipeline",
            {"message": "Pipeline completed successfully!"},
        )

        # Mark consumed feedback
        try:
            await self._mark_feedback_consumed(session_id)
        except Exception as e:
            logger.warning("Failed to mark feedback consumed", error=str(e))

        return {
            "session_id": str(session_id),
            "status": "completed",
            "report_path": final_state.get("report_path", ""),
        }

    async def run_step(self, session_id: uuid.UUID, step: str) -> dict:
        """Run the full LangGraph agent pipeline for a session."""
        logger.info("agent_service.run_step", session_id=str(session_id), step=step)

        await self._emit(
            session_id, "PLAN", "pipeline",
            {"message": f"Starting AI analysis pipeline from step: {step}"},
        )

        try:
            initial_state = await self._build_initial_state(session_id)
            final_state = initial_state
            last_event_count = 0
            async for state_update in compiled_graph.astream(initial_state):
                for node_name, node_state in state_update.items():
                    final_state = {**final_state, **node_state}
                    # Emit STAGE_RUNNING at start of each node
                    await self._emit(session_id, "STAGE_RUNNING", node_name,
                        {"message": f"Running {node_name}..."})
                    # Persist new trace events incrementally
                    events = final_state.get("trace_events", [])
                    new_events = events[last_event_count:]
                    for event in new_events:
                        await self._emit(session_id,
                            event.get("event_type", "INFO"),
                            event.get("step", "pipeline"),
                            event.get("payload", {}))
                    last_event_count = len(events)

            # Signal that all stages have finished
            await self._emit(session_id, "STAGE_DONE", "pipeline",
                {"message": "All pipeline stages completed"})

            return await self._handle_final_state(session_id, final_state, step)

        except Exception as e:
            logger.error("agent_service.run_step failed", error=str(e))
            # Persist whatever step_states we have so progress isn't lost
            try:
                await self._persist_step_states(session_id, final_state)
            except Exception:
                pass
            await self._emit(
                session_id, "ERROR", step,
                {"message": f"Pipeline failed: {e}"},
            )
            return {"session_id": str(session_id), "status": "error", "error": str(e)}

    async def resume(
        self,
        session_id: uuid.UUID,
        proposal_id: str | None = None,
        proposal_type: str | None = None,
    ) -> dict:
        """Resume pipeline after approval/denial.

        Handles both code proposals (CodeProposal) and business-logic
        proposals (Proposal). The orchestrator will pick up from where
        it left off.
        """
        logger.info(
            "agent_service.resume",
            session_id=str(session_id),
            proposal_id=proposal_id,
            proposal_type=proposal_type,
        )

        # Check for running steps
        states = await self.step_state_service.get_states(session_id)
        if self.step_state_service.has_running_steps(states):
            logger.warning("agent_service.resume: steps already running")
            return {
                "session_id": str(session_id),
                "status": "conflict",
                "error": "Steps are already running",
            }

        # Build initial state and inject approval decision
        initial_state = await self._build_initial_state(session_id)
        initial_state["awaiting_approval"] = None

        # Load pending user feedback
        user_feedback = await self._load_user_feedback(session_id)
        if user_feedback:
            initial_state["user_feedback"] = user_feedback
            # Merge into denial_feedback so nodes can read it
            existing = dict(initial_state.get("denial_feedback", {}))
            for step_key, messages in user_feedback.items():
                if step_key != "general":
                    existing.setdefault(step_key, []).extend(messages)
            initial_state["denial_feedback"] = existing

        if proposal_id:
            pid = uuid.UUID(proposal_id)

            if proposal_type == "business":
                # Handle business-logic proposal
                bp = await self.db.get(Proposal, pid)
                if bp:
                    status_map = {
                        "approved": "approved",
                        "revised": "revision_requested",
                        "rejected": "rejected",
                    }
                    mapped_status = status_map.get(bp.status, bp.status)

                    initial_state["pending_proposal_step"] = bp.step
                    initial_state["pending_proposal_type"] = bp.proposal_type
                    initial_state["proposal_status"] = mapped_status
                    initial_state["pending_proposal_plan"] = bp.plan or {}

                    if bp.user_feedback:
                        initial_state["proposal_feedback"] = bp.user_feedback

                    # If approved with selection (opportunity analysis)
                    if bp.status == "approved" and bp.plan:
                        selected = bp.plan.get("selected_option")
                        if selected:
                            initial_state["selected_opportunity"] = selected

                    await self._emit(
                        session_id,
                        f"PROPOSAL_{bp.status.upper()}",
                        bp.step,
                        {
                            "proposal_id": str(bp.id),
                            "status": bp.status,
                        },
                    )
            else:
                # Handle code proposal (existing logic)
                proposal = await self.db.get(CodeProposal, pid)
                if proposal:
                    event_type = (
                        "CODE_APPROVED"
                        if proposal.status == "approved"
                        else "CODE_DENIED"
                    )
                    await self._emit(
                        session_id,
                        event_type,
                        proposal.step,
                        {
                            "proposal_id": str(proposal.id),
                            "status": proposal.status,
                        },
                    )

                    initial_state["pending_step"] = proposal.step
                    initial_state["approval_status"] = proposal.status
                    initial_state["approved_code"] = (
                        proposal.code if proposal.status == "approved" else ""
                    )

                    if proposal.status == "denied" and proposal.result_stderr:
                        denial_feedback = dict(
                            initial_state.get("denial_feedback", {})
                        )
                        step_feedback = list(
                            denial_feedback.get(proposal.step, [])
                        )
                        step_feedback.append(proposal.result_stderr)
                        denial_feedback[proposal.step] = step_feedback
                        initial_state["denial_feedback"] = denial_feedback

        await self._emit(
            session_id,
            "PLAN",
            "pipeline",
            {"message": "Resuming pipeline after approval decision"},
        )

        try:
            final_state = initial_state
            last_event_count = 0
            async for state_update in compiled_graph.astream(initial_state):
                for node_name, node_state in state_update.items():
                    final_state = {**final_state, **node_state}
                    # Emit STAGE_RUNNING at start of each node
                    await self._emit(session_id, "STAGE_RUNNING", node_name,
                        {"message": f"Running {node_name}..."})
                    # Persist new trace events incrementally
                    events = final_state.get("trace_events", [])
                    new_events = events[last_event_count:]
                    for event in new_events:
                        await self._emit(session_id,
                            event.get("event_type", "INFO"),
                            event.get("step", "pipeline"),
                            event.get("payload", {}))
                    last_event_count = len(events)

            # Signal that all stages have finished
            await self._emit(session_id, "STAGE_DONE", "pipeline",
                {"message": "All pipeline stages completed"})

            return await self._handle_final_state(
                session_id, final_state, "pipeline"
            )

        except Exception as e:
            logger.error("agent_service.resume failed", error=str(e))
            # Persist whatever step_states we have so progress isn't lost
            try:
                await self._persist_step_states(session_id, final_state)
            except Exception:
                pass
            await self._emit(
                session_id,
                "ERROR",
                "pipeline",
                {"message": f"Resume failed: {e}"},
            )
            return {
                "session_id": str(session_id),
                "status": "error",
                "error": str(e),
            }

    async def submit_feedback(
        self, session_id: uuid.UUID, message: str, step: str | None = None
    ) -> dict:
        """Submit user feedback and optionally trigger agent re-run."""
        feedback = UserFeedback(
            id=uuid.uuid4(),
            session_id=session_id,
            step=step,
            message=message,
            status="pending",
        )
        self.db.add(feedback)
        await self.db.commit()

        await self._emit(
            session_id,
            "USER_FEEDBACK",
            step or "general",
            {"message": message, "feedback_id": str(feedback.id)},
        )

        return {
            "session_id": str(session_id),
            "feedback_id": str(feedback.id),
            "status": "submitted",
        }

    async def _mark_feedback_consumed(self, session_id: uuid.UUID) -> None:
        """Mark all pending feedback for a session as consumed."""
        stmt = (
            select(UserFeedback)
            .where(UserFeedback.session_id == session_id)
            .where(UserFeedback.status == "pending")
        )
        result = await self.db.execute(stmt)
        for fb in result.scalars().all():
            fb.status = "consumed"
        await self.db.commit()

    async def get_status(self, session_id: uuid.UUID) -> dict:
        """Get the current agent state for a session."""
        logger.info("agent_service.get_status", session_id=str(session_id))
        states = await self.step_state_service.get_states(session_id)
        running = self.step_state_service.has_running_steps(states)
        return {
            "session_id": str(session_id),
            "status": "running" if running else "idle",
            "step_states": states,
        }
