from __future__ import annotations

import json
from pathlib import Path

import structlog

from app.agent.nodes.approval_helpers import (
    check_proposal_phase,
    clear_business_proposal,
    get_proposal_feedback,
    increment_revision_count,
    mark_step_done,
    mark_step_failed,
    revert_step_to_ready,
    set_business_proposal,
    should_revise,
)
from app.agent.nodes.node_helpers import emit_trace, read_step_context
from app.agent.state import AgentState
from app.config import settings

logger = structlog.get_logger()


async def report_node(state: AgentState) -> AgentState:
    """Compile all results into a final Report object with proposal/approval loop."""
    step = "report"
    logger.info("report_node: executing", session_id=str(state.get("session_id")))
    state["current_step"] = step

    step_context = read_step_context(state, step)

    session_id = state.get("session_id")
    company_name = state.get("company_name", "the company")
    industry = state.get("industry", "")
    business_context = state.get("business_context", "")
    target_col = state.get("target_column", "")
    model_results = state.get("model_results", {})
    explainability = state.get("explainability_results", {})
    hypotheses = state.get("hypotheses", [])
    recommendations = state.get("recommendations", [])
    eda_results = state.get("eda_results", {})

    phase = check_proposal_phase(state, step)

    if phase == "propose":
        return await _propose_report(
            state, step, session_id, company_name, industry, business_context,
            target_col, model_results, explainability, hypotheses,
            recommendations, eda_results, step_context,
        )
    elif phase == "execute":
        return _execute_report(state, step, session_id)
    elif phase == "revision_requested":
        if should_revise(state, step):
            increment_revision_count(state, step)
            return await _propose_report(
                state, step, session_id, company_name, industry, business_context,
                target_col, model_results, explainability, hypotheses,
                recommendations, eda_results, step_context, revision=True,
            )
        return _execute_report(state, step, session_id)
    elif phase == "rejected":
        emit_trace(state, "INFO", step, {
            "message": "Report rejected — step reverted to READY",
        })
        state["report_path"] = ""
        clear_business_proposal(state)
        revert_step_to_ready(state, step)
        state["next_action"] = "orchestrator"
        return state
    else:
        state["next_action"] = "wait"
        return state


async def _propose_report(
    state: AgentState,
    step: str,
    session_id,
    company_name: str,
    industry: str,
    business_context: str,
    target_col: str,
    model_results: dict,
    explainability: dict,
    hypotheses: list,
    recommendations: list,
    eda_results: dict,
    step_context: dict,
    revision: bool = False,
) -> AgentState:
    """Generate report content and propose for user review."""
    feedback = ""
    if revision:
        feedback = get_proposal_feedback(state, step)

    try:
        models = model_results.get("models", [])
        best_model = next((m for m in models if m.get("best")), models[0] if models else {})
        best_metrics = best_model.get("metrics", {})
        feature_importance = explainability.get("feature_importance", [])
        top_features = [f["feature"] for f in feature_importance[:5]]
        supported = [
            h for h in hypotheses
            if h.get("result", {}).get("conclusion") == "supported"
        ]

        # Try LLM-powered narrative generation
        llm_narrative = await _llm_narrative(
            company_name=company_name,
            industry=industry,
            business_context=business_context,
            target_col=target_col,
            models=models,
            best_model=best_model,
            best_metrics=best_metrics,
            feature_importance=feature_importance,
            hypotheses=hypotheses,
            supported=supported,
            recommendations=recommendations,
        )

        if llm_narrative:
            executive_summary = llm_narrative["executive_summary"]
            key_findings = llm_narrative["key_findings"]
            generation_method = "llm"
        else:
            executive_summary = _template_summary(
                company_name, target_col, best_model, best_metrics, hypotheses, supported,
            )
            key_findings = _template_findings(
                best_model, best_metrics, top_features, eda_results, supported,
            )
            generation_method = "template"

        rec_texts = [
            f"[{r.get('opportunity_type', 'general').upper()}] {r.get('title', '')}: "
            f"{r.get('description', '')}"
            for r in recommendations
        ]

        export_urls = {
            "pdf": f"/sessions/{session_id}/report/pdf",
            "csv": f"/sessions/{session_id}/report/csv",
            "json": f"/sessions/{session_id}/report/json",
        }

        report = {
            "title": f"{company_name} - {target_col} Analysis Report",
            "executive_summary": executive_summary,
            "key_findings": key_findings,
            "recommendations": rec_texts,
            "export_urls": export_urls,
            "model_summary": {
                "best_model": best_model.get("model_name"),
                "metrics": best_metrics,
                "models_trained": len(models),
            },
            "hypothesis_summary": {
                "total": len(hypotheses),
                "supported": len(supported),
                "rejected": sum(
                    1 for h in hypotheses
                    if h.get("result", {}).get("conclusion") == "rejected"
                ),
            },
        }

        plan = {
            "report": report,
            "method": generation_method,
        }
        summary = (
            f"Report: '{report['title']}' with {len(key_findings)} findings, "
            f"{len(rec_texts)} recommendations"
        )
        if feedback:
            summary += " (revised based on feedback)"

        emit_trace(state, "AI_REASONING", step, {
            "summary": summary,
            "method": generation_method,
            "findings_count": len(key_findings),
            "recommendations_count": len(rec_texts),
            "context_used": bool(step_context.get("session_doc_section")),
        })

        return set_business_proposal(
            state, step, "report_plan", plan, summary,
            f"Generated via {generation_method} narrative with model results and findings.",
        )

    except Exception as e:
        logger.error("report_node: proposal failed", error=str(e))
        state["error"] = str(e)
        mark_step_failed(state, step)
        return state


def _execute_report(
    state: AgentState, step: str, session_id,
) -> AgentState:
    """Save the approved report to disk."""
    plan = state.get("pending_proposal_plan", {})
    report = plan.get("report", {})

    # Save report to disk
    artifacts_dir = Path(settings.upload_dir) / str(session_id) / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    report_path = str(artifacts_dir / "report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    state["report_path"] = report_path

    key_findings = report.get("key_findings", [])
    rec_texts = report.get("recommendations", [])
    executive_summary = report.get("executive_summary", "")

    emit_trace(state, "FINAL_SUMMARY", step, {
        "narrative_summary": executive_summary,
        "key_decisions": {
            "best_model": report.get("model_summary", {}).get("best_model", "N/A"),
            "target_column": state.get("target_column", ""),
            "hypotheses_tested": report.get("hypothesis_summary", {}).get("total", 0),
            "hypotheses_supported": report.get("hypothesis_summary", {}).get("supported", 0),
            "recommendations_count": len(rec_texts),
        },
        "artifacts_count": len(key_findings) + len(rec_texts) + 1,
    })

    logger.info("report_node: completed", session_id=str(session_id), report_path=report_path)

    # Update session doc
    try:
        from session_doc.server import upsert_structured
        sid = str(state.get("session_id", ""))
        narrative = (
            f"Report generated: {report.get('title', '')}. "
            f"Key findings: {len(key_findings)}. "
            f"Recommendations: {len(rec_texts)}."
        )
        upsert_structured(sid, "Report", narrative, metadata={
            "report_path": report_path,
            "key_findings_count": len(key_findings),
            "recommendations_count": len(rec_texts),
            "export_urls": report.get("export_urls", {}),
        })
    except Exception as e:
        logger.warning("report_node: session_doc upsert failed", error=str(e))

    clear_business_proposal(state)
    mark_step_done(state, step)
    state["next_action"] = "orchestrator"
    return state


async def _llm_narrative(
    *,
    company_name: str,
    industry: str,
    business_context: str,
    target_col: str,
    models: list,
    best_model: dict,
    best_metrics: dict,
    feature_importance: list,
    hypotheses: list,
    supported: list,
    recommendations: list,
) -> dict | None:
    """Call LLM to generate executive summary and key findings. Returns None on failure."""
    try:
        from app.agent.llm import invoke_llm
        from app.agent.prompts import REPORT_NARRATIVE_PROMPT

        # Format feature importance
        fi_lines = []
        for f in feature_importance[:10]:
            fi_lines.append(f"- {f.get('feature', '?')}: importance={f.get('importance', 'N/A')}")
        fi_str = "\n".join(fi_lines) if fi_lines else "No feature importance available"

        # Format hypothesis details
        hyp_details = []
        for h in hypotheses:
            result = h.get("result", {})
            hyp_details.append(
                f"- {h.get('statement', '?')} -> {result.get('conclusion', 'unknown')} "
                f"(p={result.get('p_value', 'N/A')})"
            )
        hyp_str = "\n".join(hyp_details) if hyp_details else "None"

        # Format recommendations summary
        rec_lines = []
        for r in recommendations:
            rec_lines.append(
                f"- [{r.get('opportunity_type', 'general').upper()}] {r.get('title', '')}"
            )
        rec_str = "\n".join(rec_lines) if rec_lines else "None"

        # Dataset summary
        dataset_summary = f"{len(models)} models trained on dataset"

        prompt = REPORT_NARRATIVE_PROMPT.format(
            company_name=company_name,
            industry=industry,
            business_context=business_context,
            target_column=target_col,
            dataset_summary=dataset_summary,
            models_trained=len(models),
            best_model_name=best_model.get("model_name", "N/A"),
            best_f1=f"{best_metrics.get('f1', 0):.1%}" if best_metrics.get("f1") else "N/A",
            best_auc=f"{best_metrics.get('roc_auc', 0):.1%}" if best_metrics.get("roc_auc") else "N/A",
            feature_importance=fi_str,
            hypothesis_total=len(hypotheses),
            hypothesis_supported=len(supported),
            hypothesis_details=hyp_str,
            recommendations_summary=rec_str,
        )

        response = await invoke_llm([
            {"role": "system", "content": prompt},
        ])

        parsed = json.loads(response)

        executive_summary = parsed.get("executive_summary", "")
        key_findings = parsed.get("key_findings", [])

        if not executive_summary or not isinstance(key_findings, list):
            logger.warning("report_node: LLM returned incomplete narrative")
            return None

        logger.info("report_node: LLM generated narrative", findings_count=len(key_findings))
        return {
            "executive_summary": executive_summary,
            "key_findings": key_findings,
        }

    except Exception as e:
        logger.warning("report_node: LLM narrative failed, will use template", error=str(e))
        return None


def _template_summary(
    company_name: str,
    target_col: str,
    best_model: dict,
    best_metrics: dict,
    hypotheses: list,
    supported: list,
) -> str:
    """Fallback template-based executive summary."""
    parts = [
        f"Analysis of {company_name}'s data for {target_col} prediction."
    ]
    if best_model:
        acc = best_metrics.get("accuracy", 0)
        f1 = best_metrics.get("f1", 0)
        auc = best_metrics.get("roc_auc")
        parts.append(
            f"The best performing model is {best_model.get('model_name', 'N/A')} "
            f"with {acc:.1%} accuracy and {f1:.1%} F1-score"
            + (f" (AUC-ROC: {auc:.1%})" if auc else "")
            + "."
        )
    if hypotheses:
        parts.append(
            f"{len(supported)} out of {len(hypotheses)} hypotheses "
            f"were statistically significant."
        )
    parts.append(
        "The analysis reveals actionable patterns that can drive "
        "data-driven decision making."
    )
    return " ".join(parts)


def _template_findings(
    best_model: dict,
    best_metrics: dict,
    top_features: list[str],
    eda_results: dict,
    supported: list,
) -> list[str]:
    """Fallback template-based key findings."""
    findings: list[str] = []
    if best_model:
        findings.append(
            f"The {best_model.get('model_name', 'best')} model achieved the best "
            f"performance with an F1-score of {best_metrics.get('f1', 0):.1%}"
        )
    if top_features:
        findings.append(
            f"Top predictive features: {', '.join(top_features)}"
        )
    if eda_results:
        findings.append(
            f"EDA generated {eda_results.get('successful_plots', 0)} visualizations"
        )
    for hyp in supported[:3]:
        findings.append(hyp.get("statement", ""))
    return findings
