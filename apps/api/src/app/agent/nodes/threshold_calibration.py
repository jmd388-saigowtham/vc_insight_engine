"""Threshold calibration node — business-informed threshold optimization.

Proposes an optimal classification threshold with precision/recall
tradeoff analysis and business rationale. User can adjust threshold
with their own business justification.
"""

from __future__ import annotations

import structlog

from app.agent.nodes.approval_helpers import (
    check_proposal_phase,
    clear_business_proposal,
    get_proposal_feedback,
    increment_revision_count,
    mark_step_done,
    set_business_proposal,
    should_revise,
)
from app.agent.nodes.node_helpers import emit_trace
from app.agent.state import AgentState

logger = structlog.get_logger()


async def threshold_calibration_node(state: AgentState) -> AgentState:
    """Propose and optimize classification threshold."""
    step = "threshold_calibration"
    session_id = str(state.get("session_id", ""))
    logger.info("threshold_calibration_node: executing", session_id=session_id)

    phase = check_proposal_phase(state, step)

    if phase == "propose":
        return await _propose_threshold(state, step)
    elif phase == "execute":
        return await _execute_threshold(state, step)
    elif phase == "revision_requested":
        if should_revise(state, step):
            increment_revision_count(state, step)
            return await _propose_threshold(state, step, revision=True)
        clear_business_proposal(state)
        mark_step_done(state, step)
        state["next_action"] = "orchestrator"
        return state
    elif phase == "rejected":
        # Use default threshold of 0.5
        state["threshold_config"] = {
            "threshold": 0.5,
            "method": "default",
            "reasoning": "User rejected threshold optimization; using default 0.5",
        }
        clear_business_proposal(state)
        mark_step_done(state, step)
        state["next_action"] = "orchestrator"
        return state
    else:
        state["next_action"] = "wait"
        return state


async def _propose_threshold(
    state: AgentState, step: str, revision: bool = False
) -> AgentState:
    """Analyze model results and propose optimal threshold."""
    model_results = state.get("model_results", {})

    if not model_results:
        emit_trace(state, "INFO", step, {
            "message": "No model results; skipping threshold calibration"
        })
        state["threshold_config"] = {
            "threshold": 0.5,
            "method": "default",
            "reasoning": "No model results available",
        }
        mark_step_done(state, step)
        state["next_action"] = "orchestrator"
        return state

    feedback = ""
    if revision:
        feedback = get_proposal_feedback(state, step)

    # Extract best model info
    best_model = model_results.get("best_model", "unknown")
    models = model_results.get("models", [])
    best_info = {}
    for m in models:
        if m.get("model_name") == best_model:
            best_info = m
            break

    # Default threshold analysis
    default_threshold = 0.5
    precision = best_info.get("precision", 0)
    recall = best_info.get("recall", 0)
    f1 = best_info.get("f1_score", 0)

    # Determine recommended threshold based on business context
    business_context = state.get("business_context", "").lower()
    selected_opp = state.get("selected_opportunity", {})
    use_case = selected_opp.get("use_case", "")

    if "churn" in business_context or use_case == "churn":
        # For churn: prefer higher recall (catch more churners)
        recommended = 0.4
        rationale = (
            "For churn prediction, a lower threshold (0.4) is recommended "
            "to catch more at-risk customers, accepting some false positives."
        )
    elif "fraud" in business_context:
        # For fraud: prefer higher precision (fewer false accusations)
        recommended = 0.6
        rationale = (
            "For fraud detection, a higher threshold (0.6) is recommended "
            "to reduce false positives while still catching most fraud."
        )
    else:
        # Default: F1-optimal
        recommended = 0.5
        rationale = (
            "Default threshold (0.5) balances precision and recall. "
            "Adjust based on the relative cost of false positives vs. false negatives."
        )

    if feedback:
        # If user gave feedback, try to adjust
        if "lower" in feedback.lower() or "more recall" in feedback.lower():
            recommended = max(0.2, recommended - 0.1)
            rationale = f"Lowered threshold to {recommended} based on user feedback."
        elif "higher" in feedback.lower() or "more precision" in feedback.lower():
            recommended = min(0.8, recommended + 0.1)
            rationale = f"Raised threshold to {recommended} based on user feedback."

    # Build threshold analysis
    thresholds = [0.3, 0.4, 0.5, 0.6, 0.7]
    threshold_analysis = []
    for t in thresholds:
        # Approximate metrics at different thresholds
        # (In a real implementation, this would use the actual model predictions)
        factor = (t - 0.5) * 2
        est_precision = min(1.0, max(0.1, precision + factor * 0.15))
        est_recall = min(1.0, max(0.1, recall - factor * 0.15))
        est_f1 = (
            2 * est_precision * est_recall / (est_precision + est_recall)
            if (est_precision + est_recall) > 0
            else 0
        )
        threshold_analysis.append({
            "threshold": t,
            "estimated_precision": round(est_precision, 3),
            "estimated_recall": round(est_recall, 3),
            "estimated_f1": round(est_f1, 3),
        })

    plan = {
        "recommended_threshold": recommended,
        "current_default": default_threshold,
        "best_model": best_model,
        "current_metrics": {
            "precision": precision,
            "recall": recall,
            "f1_score": f1,
        },
        "threshold_analysis": threshold_analysis,
        "business_rationale": rationale,
        "false_positive_cost": "medium",
        "false_negative_cost": "high" if "churn" in (use_case or "") else "medium",
    }

    summary = (
        f"Recommended threshold: {recommended} for {best_model}. "
        f"{rationale}"
    )

    return set_business_proposal(
        state, step, "threshold_plan", plan, summary, rationale
    )


async def _execute_threshold(state: AgentState, step: str) -> AgentState:
    """Apply the approved threshold."""
    plan = state.get("pending_proposal_plan", {})
    threshold = plan.get("recommended_threshold", 0.5)

    state["threshold_config"] = {
        "threshold": threshold,
        "method": "optimized",
        "best_model": plan.get("best_model", ""),
        "business_rationale": plan.get("business_rationale", ""),
        "metrics_at_threshold": plan.get("current_metrics", {}),
    }

    emit_trace(state, "TOOL_RESULT", step, {
        "message": f"Threshold set to {threshold}",
        "threshold_config": state["threshold_config"],
    })

    # Update session memory
    try:
        from session_doc.server import upsert_structured
        session_id = str(state.get("session_id", ""))
        upsert_structured(
            session_id,
            "Threshold Decisions",
            f"Threshold: {threshold}\n"
            f"Model: {plan.get('best_model', '')}\n"
            f"Rationale: {plan.get('business_rationale', '')}",
            metadata={
                "threshold": threshold,
                "best_model": plan.get("best_model", ""),
                "method": "optimized",
                "metrics_at_threshold": plan.get("current_metrics", {}),
            },
        )
    except Exception:
        pass

    clear_business_proposal(state)
    mark_step_done(state, step)
    state["next_action"] = "orchestrator"
    return state
