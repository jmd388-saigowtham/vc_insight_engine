from __future__ import annotations

import csv
import io
import json
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_db_session, get_event_service
from app.models.session import Session
from app.services.event_service import EventService
from app.services.pipeline_service import PipelineService

router = APIRouter()


# ============ SCHEMAS ============


class OpportunityResponse(BaseModel):
    id: str
    title: str
    description: str
    type: str  # churn, expansion, cross_sell, upsell
    confidence: float
    key_metrics: list[str]


class TargetConfigResponse(BaseModel):
    target_variable: str
    features: list[dict[str, Any]]
    preview: list[dict[str, Any]]
    ai_explanation: str | None = None
    alternatives: list[dict[str, Any]] | None = None


class HypothesisResultSchema(BaseModel):
    test_statistic: float
    p_value: float
    conclusion: str
    supported: bool


class HypothesisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    statement: str
    test_type: str
    variables: list[str]
    expected_outcome: str
    status: str
    result: HypothesisResultSchema | None = None


class HypothesisUpdate(BaseModel):
    status: str


class ThresholdInfo(BaseModel):
    threshold: float = 0.5
    method: str = "default"
    f1_at_threshold: float | None = None
    precision_at_threshold: float | None = None
    recall_at_threshold: float | None = None


class ModelResultResponse(BaseModel):
    id: str
    session_id: str
    model_name: str
    accuracy: float
    precision: float
    recall: float
    f1_score: float
    auc_roc: float
    is_best: bool
    confusion_matrix: list[list[int]] | None = None
    train_metrics: dict[str, float] | None = None
    val_metrics: dict[str, float] | None = None
    diagnostics: dict[str, Any] | None = None
    threshold_info: ThresholdInfo | None = None


class ReportResponse(BaseModel):
    id: str
    session_id: str
    executive_summary: str
    key_findings: list[str]
    recommendations: list[str]
    export_urls: dict[str, str]


class ResumeRequest(BaseModel):
    proposal_id: str | None = None
    proposal_type: str | None = None  # "code" (default) or "business"


class FeatureSelectionUpdate(BaseModel):
    target_column: str
    selected_features: list[str]


class FeatureSelectionResponse(BaseModel):
    target_column: str
    features: list[dict[str, Any]]
    selected_features: list[str]


class SelectModelRequest(BaseModel):
    model_name: str


class SelectModelResponse(BaseModel):
    session_id: str
    selected_model: str


VALID_MODEL_TYPES = {
    "logistic_regression",
    "random_forest",
    "gradient_boosting",
    "svm",
    "extra_trees",
}


class TrainAdditionalModelRequest(BaseModel):
    model_type: str


class TrainAdditionalModelResponse(BaseModel):
    status: str
    model_type: str
    result: dict[str, Any] | None = None


class CustomPlotRequest(BaseModel):
    request: str


class CustomPlotResponse(BaseModel):
    status: str
    plot_path: str | None = None
    plot_type: str | None = None
    description: str | None = None
    artifact_id: str | None = None
    errors: list[str] | None = None


class CustomHypothesisRequest(BaseModel):
    statement: str
    test_type: str  # t_test, chi_square, correlation, anova
    variables: list[str]


class CustomHypothesisResponse(BaseModel):
    id: str
    session_id: str
    statement: str
    test_type: str
    variables: list[str]
    status: str
    result: HypothesisResultSchema | None = None


class RetrainThresholdRequest(BaseModel):
    model_name: str
    threshold: float


class RetrainThresholdResponse(BaseModel):
    model_name: str
    threshold: float
    metrics: dict[str, float]
    threshold_info: ThresholdInfo


# ============ ENDPOINTS ============


def _get_pipeline_service(
    db: AsyncSession = Depends(get_db_session),
    event_service: EventService = Depends(get_event_service),
) -> PipelineService:
    return PipelineService(db, event_service)


@router.post("/sessions/{session_id}/start-analysis")
async def start_analysis(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    event_service: EventService = Depends(get_event_service),
):
    """Start the AI analysis pipeline via the LangGraph agent.

    This is the primary entry point. Triggers the agent from the profiling
    step, which then proceeds autonomously with proposal/approval gates.
    """
    from app.services.agent_service import AgentService

    agent_svc = AgentService(db, event_service)
    result = await agent_svc.run_step(session_id, "profiling")
    return result


@router.get("/sessions/{session_id}/opportunities", response_model=list[OpportunityResponse])
async def get_opportunities(
    session_id: uuid.UUID,
    service: PipelineService = Depends(_get_pipeline_service),
):
    """Get AI-identified value creation opportunities."""
    return await service.get_opportunities(session_id)


@router.get("/sessions/{session_id}/target", response_model=TargetConfigResponse)
async def get_target_config(
    session_id: uuid.UUID,
    service: PipelineService = Depends(_get_pipeline_service),
):
    """Get the identified target variable and features."""
    try:
        return await service.get_target_config(session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/sessions/{session_id}/hypotheses", response_model=list[HypothesisResponse])
async def get_hypotheses(
    session_id: uuid.UUID,
    with_results: bool = False,
    service: PipelineService = Depends(_get_pipeline_service),
):
    """Get generated hypotheses, optionally with test results."""
    return await service.get_hypotheses(session_id, with_results=with_results)


@router.patch("/hypotheses/{hypothesis_id}", response_model=HypothesisResponse)
async def update_hypothesis(
    hypothesis_id: str,
    data: HypothesisUpdate,
    service: PipelineService = Depends(_get_pipeline_service),
):
    """Approve or reject a hypothesis."""
    try:
        return await service.update_hypothesis(hypothesis_id, data.status)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/sessions/{session_id}/models", response_model=list[ModelResultResponse])
async def get_models(
    session_id: uuid.UUID,
    service: PipelineService = Depends(_get_pipeline_service),
):
    """Get model training results."""
    return await service.get_models(session_id)


@router.get("/sessions/{session_id}/report", response_model=ReportResponse)
async def get_report(
    session_id: uuid.UUID,
    service: PipelineService = Depends(_get_pipeline_service),
):
    """Get the final analysis report."""
    report = await service.get_report(session_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not yet generated")
    # Inject required fields that may not be in the on-disk JSON
    report.setdefault("id", str(session_id))
    report.setdefault("session_id", str(session_id))
    report.setdefault("executive_summary", report.get("title", ""))
    report.setdefault("key_findings", [])
    report.setdefault("recommendations", [])
    # Always inject export URLs so download buttons appear
    report["export_urls"] = {
        "json": f"/sessions/{session_id}/report/json",
        "csv": f"/sessions/{session_id}/report/csv",
        "pdf": f"/sessions/{session_id}/report/pdf",
    }
    return report


async def _load_report_json(session_id: uuid.UUID) -> dict:
    """Load report.json from disk for a session."""
    report_path = Path(settings.upload_dir) / str(session_id) / "artifacts" / "report.json"
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="Report not yet generated")
    with open(report_path) as f:
        return json.load(f)


@router.get("/sessions/{session_id}/report/json")
async def export_report_json(session_id: uuid.UUID):
    """Export report as JSON file download."""
    report = await _load_report_json(session_id)
    content = json.dumps(report, indent=2)
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="report_{session_id}.json"'},
    )


@router.get("/sessions/{session_id}/report/csv")
async def export_report_csv(session_id: uuid.UUID):
    """Export report as CSV with model metrics, hypotheses, and recommendations."""
    report = await _load_report_json(session_id)
    output = io.StringIO()
    writer = csv.writer(output)

    # Section 1: Summary
    writer.writerow(["Section", "Key", "Value"])
    writer.writerow(["Summary", "Title", report.get("title", "")])
    writer.writerow(["Summary", "Executive Summary", report.get("executive_summary", "")])

    # Section 2: Key Findings
    for i, finding in enumerate(report.get("key_findings", []), 1):
        writer.writerow(["Key Findings", f"Finding {i}", finding])

    # Section 3: Model Summary
    model_summary = report.get("model_summary", {})
    writer.writerow(["Model", "Best Model", model_summary.get("best_model", "")])
    writer.writerow(["Model", "Models Trained", model_summary.get("models_trained", "")])
    metrics = model_summary.get("metrics", {})
    for metric_name, metric_value in metrics.items():
        writer.writerow(["Model Metrics", metric_name, metric_value])

    # Section 4: Hypothesis Summary
    hyp_summary = report.get("hypothesis_summary", {})
    writer.writerow(["Hypotheses", "Total", hyp_summary.get("total", "")])
    writer.writerow(["Hypotheses", "Supported", hyp_summary.get("supported", "")])
    writer.writerow(["Hypotheses", "Rejected", hyp_summary.get("rejected", "")])

    # Section 5: Recommendations
    for i, rec in enumerate(report.get("recommendations", []), 1):
        writer.writerow(["Recommendations", f"Recommendation {i}", rec])

    content = output.getvalue()
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="report_{session_id}.csv"'},
    )


@router.get("/sessions/{session_id}/report/pdf")
async def export_report_pdf(session_id: uuid.UUID):
    """Export report as a PDF document."""
    report = await _load_report_json(session_id)

    try:
        from matplotlib.backends.backend_pdf import PdfPages
        import matplotlib.pyplot as plt

        buf = io.BytesIO()
        with PdfPages(buf) as pdf:
            # Page 1: Title & Executive Summary
            fig, ax = plt.subplots(figsize=(8.5, 11))
            ax.axis("off")

            title = report.get("title", "Analysis Report")
            summary = report.get("executive_summary", "")

            y = 0.95
            ax.text(0.5, y, title, transform=ax.transAxes, fontsize=16,
                    fontweight="bold", ha="center", va="top")
            y -= 0.06
            ax.text(0.5, y, "=" * 60, transform=ax.transAxes, fontsize=8,
                    ha="center", va="top", color="gray")
            y -= 0.04

            ax.text(0.05, y, "Executive Summary", transform=ax.transAxes,
                    fontsize=13, fontweight="bold", va="top")
            y -= 0.04

            # Word-wrap the summary
            for line in _wrap_text(summary, 90):
                ax.text(0.05, y, line, transform=ax.transAxes, fontsize=9, va="top")
                y -= 0.025
                if y < 0.05:
                    break

            # Key Findings
            y -= 0.03
            if y > 0.15:
                ax.text(0.05, y, "Key Findings", transform=ax.transAxes,
                        fontsize=13, fontweight="bold", va="top")
                y -= 0.04
                for finding in report.get("key_findings", []):
                    for line in _wrap_text(f"• {finding}", 85):
                        ax.text(0.07, y, line, transform=ax.transAxes,
                                fontsize=9, va="top")
                        y -= 0.025
                        if y < 0.05:
                            break
                    if y < 0.05:
                        break

            pdf.savefig(fig)
            plt.close(fig)

            # Page 2: Model Results & Recommendations
            fig, ax = plt.subplots(figsize=(8.5, 11))
            ax.axis("off")
            y = 0.95

            # Model Summary
            model_summary = report.get("model_summary", {})
            ax.text(0.05, y, "Model Results", transform=ax.transAxes,
                    fontsize=13, fontweight="bold", va="top")
            y -= 0.04
            best = model_summary.get("best_model", "N/A")
            ax.text(0.07, y, f"Best Model: {best}", transform=ax.transAxes,
                    fontsize=10, va="top")
            y -= 0.03
            metrics = model_summary.get("metrics", {})
            for k, v in metrics.items():
                val = f"{v:.1%}" if isinstance(v, float) else str(v)
                ax.text(0.07, y, f"  {k}: {val}", transform=ax.transAxes,
                        fontsize=9, va="top")
                y -= 0.025

            # Hypothesis Summary
            y -= 0.03
            hyp = report.get("hypothesis_summary", {})
            ax.text(0.05, y, "Hypothesis Results", transform=ax.transAxes,
                    fontsize=13, fontweight="bold", va="top")
            y -= 0.04
            ax.text(0.07, y,
                    f"Total: {hyp.get('total', 0)}  |  "
                    f"Supported: {hyp.get('supported', 0)}  |  "
                    f"Rejected: {hyp.get('rejected', 0)}",
                    transform=ax.transAxes, fontsize=10, va="top")
            y -= 0.05

            # Recommendations
            ax.text(0.05, y, "Recommendations", transform=ax.transAxes,
                    fontsize=13, fontweight="bold", va="top")
            y -= 0.04
            for rec in report.get("recommendations", []):
                for line in _wrap_text(f"• {rec}", 85):
                    ax.text(0.07, y, line, transform=ax.transAxes,
                            fontsize=9, va="top")
                    y -= 0.025
                    if y < 0.05:
                        break
                if y < 0.05:
                    break

            pdf.savefig(fig)
            plt.close(fig)

        content = buf.getvalue()
        return Response(
            content=content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="report_{session_id}.pdf"'
            },
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"PDF generation failed: {e}",
        )


def _wrap_text(text: str, width: int) -> list[str]:
    """Simple word-wrap for PDF text rendering."""
    words = text.split()
    lines: list[str] = []
    current_line = ""
    for word in words:
        if len(current_line) + len(word) + 1 <= width:
            current_line = f"{current_line} {word}" if current_line else word
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)
    return lines or [""]


@router.post("/sessions/{session_id}/complete")
async def complete_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
):
    """Mark a session as completed."""
    stmt = update(Session).where(Session.id == session_id).values(status="completed")
    await db.execute(stmt)
    await db.commit()
    return {"status": "completed"}


@router.post("/sessions/{session_id}/resume")
async def resume_pipeline(
    session_id: uuid.UUID,
    data: ResumeRequest | None = None,
    db: AsyncSession = Depends(get_db_session),
    event_service: EventService = Depends(get_event_service),
):
    """Resume pipeline after code approval/denial."""
    from app.services.step_state_service import StepStateService

    svc = StepStateService(db, event_service)
    try:
        states = await svc.get_states(session_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Session not found")
    if svc.has_running_steps(states):
        raise HTTPException(status_code=409, detail="Steps are already running")

    from app.services.agent_service import AgentService

    agent_svc = AgentService(db, event_service)
    result = await agent_svc.resume(
        session_id,
        proposal_id=data.proposal_id if data else None,
        proposal_type=data.proposal_type if data else None,
    )
    return result


@router.post("/sessions/{session_id}/rerun/{step}")
async def rerun_from_step(
    session_id: uuid.UUID,
    step: str,
    db: AsyncSession = Depends(get_db_session),
    event_service: EventService = Depends(get_event_service),
):
    """Invalidate downstream steps and rerun from a specific step."""
    from app.services.step_state_service import STEP_ORDER, StepStateService

    if step not in STEP_ORDER:
        raise HTTPException(status_code=400, detail=f"Invalid step: {step}")

    svc = StepStateService(db, event_service)
    try:
        states = await svc.get_states(session_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Session not found")
    if svc.has_running_steps(states):
        raise HTTPException(status_code=409, detail="Steps are already running")

    # Invalidate downstream
    await svc.invalidate_downstream(session_id, step)

    # Run from that step
    from app.services.agent_service import AgentService

    agent_svc = AgentService(db, event_service)
    result = await agent_svc.run_step(session_id, step)
    return result


@router.get("/sessions/{session_id}/feature-selection")
async def get_feature_selection(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
):
    """Get feature selection state for a session."""
    session = await db.get(Session, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    target_column = getattr(session, "target_column", None) or ""
    selected_features = getattr(session, "selected_features", None) or []

    # Get column profiles for feature list
    from sqlalchemy import select as sa_select
    from app.models.column_profile import ColumnProfile
    from app.models.uploaded_file import UploadedFile

    files_stmt = sa_select(UploadedFile).where(UploadedFile.session_id == session_id)
    files_result = await db.execute(files_stmt)
    files = list(files_result.scalars().all())

    # Try to get agent-provided feature importance
    feature_importance_map: dict[str, dict[str, Any]] = {}
    try:
        from app.models.proposal import Proposal
        stmt = sa_select(Proposal).where(
            Proposal.session_id == session_id,
            Proposal.step == "feature_selection",
            Proposal.status == "approved",
        ).order_by(Proposal.created_at.desc()).limit(1)
        result = await db.execute(stmt)
        proposal = result.scalar_one_or_none()
        if proposal and proposal.plan:
            for feat in proposal.plan.get("features", []):
                name = feat.get("name", "")
                if name:
                    feature_importance_map[name] = feat
    except Exception:
        pass

    features: list[dict[str, Any]] = []
    for f in files:
        cols_stmt = sa_select(ColumnProfile).where(ColumnProfile.file_id == f.id)
        cols_result = await db.execute(cols_stmt)
        for col in cols_result.scalars().all():
            col_name = col.column_name
            if col_name == target_column:
                continue
            agent_feat = feature_importance_map.get(col_name, {})
            features.append({
                "name": col_name,
                "dtype": col.dtype,
                "null_pct": col.null_pct or 0,
                "unique_count": col.unique_count,
                "importance": agent_feat.get("importance", 0.5),
                "selected": col_name in selected_features if selected_features else True,
                "reasoning": agent_feat.get("reasoning"),
                "leakage_risk": agent_feat.get("leakage_risk", False),
                "source": "agent" if agent_feat else "placeholder",
            })

    return {
        "target_column": target_column,
        "features": features,
        "selected_features": selected_features,
    }


@router.patch("/sessions/{session_id}/feature-selection")
async def update_feature_selection(
    session_id: uuid.UUID,
    data: FeatureSelectionUpdate,
    db: AsyncSession = Depends(get_db_session),
):
    """Update feature selection for a session."""
    session = await db.get(Session, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if not data.selected_features:
        raise HTTPException(status_code=400, detail="At least one feature must be selected")

    if data.target_column in data.selected_features:
        raise HTTPException(
            status_code=400,
            detail="Target column must not be in the selected features list",
        )

    session.target_column = data.target_column
    session.selected_features = data.selected_features
    await db.commit()
    await db.refresh(session)

    return {
        "target_column": session.target_column,
        "selected_features": session.selected_features,
    }


@router.get("/sessions/{session_id}/step-states")
async def get_step_states(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    event_service: EventService = Depends(get_event_service),
):
    """Get current step states for a session."""
    from app.services.step_state_service import StepStateService

    svc = StepStateService(db, event_service)
    states = await svc.get_states(session_id)
    return {"step_states": states}


@router.post("/sessions/{session_id}/select-model", response_model=SelectModelResponse)
async def select_model(
    session_id: uuid.UUID,
    data: SelectModelRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """Select which trained model to use for SHAP explainability."""
    session = await db.get(Session, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    # Verify the model exists in model_results.json
    artifacts_dir = Path(settings.upload_dir) / str(session_id) / "artifacts"
    results_path = artifacts_dir / "model_results.json"
    if results_path.exists():
        with open(results_path) as f:
            model_results = json.load(f)
        model_names = [m["model_name"] for m in model_results]
        if data.model_name not in model_names:
            raise HTTPException(
                status_code=400,
                detail=f"Model '{data.model_name}' not found. Available: {model_names}",
            )
        # Update is_best flags
        for m in model_results:
            m["is_best"] = m["model_name"] == data.model_name
        with open(results_path, "w") as f:
            json.dump(model_results, f, indent=2)
    else:
        raise HTTPException(
            status_code=404,
            detail="No model results found. Run the pipeline first.",
        )

    # Store selected model on the session context
    if not session.step_states:
        session.step_states = {}
    session.step_states = {**session.step_states, "selected_model": data.model_name}
    await db.commit()

    return SelectModelResponse(
        session_id=str(session_id),
        selected_model=data.model_name,
    )


@router.post(
    "/sessions/{session_id}/train-additional-model",
    deprecated=True,
)
async def train_additional_model(
    session_id: uuid.UUID,
    data: TrainAdditionalModelRequest,
    db: AsyncSession = Depends(get_db_session),
    event_service: EventService = Depends(get_event_service),
):
    """Train a new model type — routes through the agent proposal flow.

    DEPRECATED: Use POST /sessions/{id}/feedback with step='modeling' instead.
    This endpoint now submits feedback to the agent rather than executing directly.
    """
    from app.services.agent_service import AgentService

    session = await db.get(Session, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    agent_svc = AgentService(db, event_service)
    result = await agent_svc.submit_feedback(
        session_id,
        message=f"Train additional {data.model_type} model.",
        step="modeling",
    )
    return {**result, "status": "feedback_submitted", "message": "Request routed through AI agent proposal flow"}


@router.post(
    "/sessions/{session_id}/eda/custom-plot",
    deprecated=True,
)
async def create_custom_plot(
    session_id: uuid.UUID,
    data: CustomPlotRequest,
    db: AsyncSession = Depends(get_db_session),
    event_service: EventService = Depends(get_event_service),
):
    """Generate a custom EDA plot — routes through the agent proposal flow.

    DEPRECATED: Use POST /sessions/{id}/feedback with step='eda' instead.
    This endpoint now submits feedback to the agent rather than executing directly.
    """
    from app.services.agent_service import AgentService

    session = await db.get(Session, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    agent_svc = AgentService(db, event_service)
    result = await agent_svc.submit_feedback(
        session_id,
        message=f"Generate custom EDA plot: {data.request}",
        step="eda",
    )
    return {**result, "status": "feedback_submitted", "message": "Request routed through AI agent proposal flow"}


@router.post(
    "/sessions/{session_id}/hypotheses/custom",
    deprecated=True,
)
async def create_custom_hypothesis(
    session_id: uuid.UUID,
    data: CustomHypothesisRequest,
    db: AsyncSession = Depends(get_db_session),
    event_service: EventService = Depends(get_event_service),
):
    """Create a custom hypothesis — routes through the agent proposal flow.

    DEPRECATED: Use POST /sessions/{id}/feedback with step='hypothesis' instead.
    This endpoint now submits feedback to the agent rather than executing directly.
    """
    from app.services.agent_service import AgentService

    session = await db.get(Session, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    agent_svc = AgentService(db, event_service)
    result = await agent_svc.submit_feedback(
        session_id,
        message=(
            f"Add custom hypothesis: \"{data.statement}\" "
            f"using {data.test_type} test with variables: {', '.join(data.variables)}."
        ),
        step="hypothesis",
    )
    return {**result, "status": "feedback_submitted", "message": "Request routed through AI agent proposal flow"}


@router.post(
    "/sessions/{session_id}/retrain-threshold",
    deprecated=True,
)
async def retrain_threshold(
    session_id: uuid.UUID,
    data: RetrainThresholdRequest,
    db: AsyncSession = Depends(get_db_session),
    event_service: EventService = Depends(get_event_service),
):
    """Re-evaluate at a different threshold — routes through the agent proposal flow.

    DEPRECATED: Use POST /sessions/{id}/feedback with step='threshold_calibration' instead.
    This endpoint now submits feedback to the agent rather than executing directly.
    """
    from app.services.agent_service import AgentService

    session = await db.get(Session, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    agent_svc = AgentService(db, event_service)
    result = await agent_svc.submit_feedback(
        session_id,
        message=f"Re-evaluate model \"{data.model_name}\" at threshold {data.threshold}.",
        step="threshold_calibration",
    )
    return {**result, "status": "feedback_submitted", "message": "Request routed through AI agent proposal flow"}


@router.get("/sessions/{session_id}/datasets")
async def list_datasets(
    session_id: uuid.UUID,
    source_type: str | None = None,
    db: AsyncSession = Depends(get_db_session),
):
    """List all datasets registered for a session."""
    from app.services.dataset_registry import DatasetRegistry

    registry = DatasetRegistry(db)
    datasets = await registry.list_datasets(session_id)

    if source_type:
        datasets = [d for d in datasets if d.source_type == source_type]

    return [
        {
            "id": str(d.id),
            "session_id": str(d.session_id),
            "source_type": d.source_type,
            "name": d.name,
            "file_path": d.file_path,
            "row_count": d.row_count,
            "column_count": d.column_count,
            "parent_dataset_id": str(d.parent_dataset_id) if d.parent_dataset_id else None,
            "metadata": d.metadata_,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in datasets
    ]
