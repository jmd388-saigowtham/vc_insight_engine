from __future__ import annotations

import json

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

logger = structlog.get_logger()


async def recommendation_node(state: AgentState) -> AgentState:
    """Analyze model + explainability results to generate VC-focused recommendations."""
    step = "recommendation"
    logger.info("recommendation_node: executing", session_id=str(state.get("session_id")))
    state["current_step"] = step

    step_context = read_step_context(state, step)

    session_id = state.get("session_id")
    model_results = state.get("model_results", {})
    explainability = state.get("explainability_results", {})
    hypotheses = state.get("hypotheses", [])
    business_context = state.get("business_context", "")
    target_col = state.get("target_column", "")
    company_name = state.get("company_name", "the company")
    industry = state.get("industry", "")

    phase = check_proposal_phase(state, step)

    if phase == "propose":
        return await _propose_recommendations(
            state, step, company_name, industry, business_context,
            target_col, model_results, explainability, hypotheses, step_context,
        )
    elif phase == "execute":
        return _execute_recommendations(state, step, session_id)
    elif phase == "revision_requested":
        if should_revise(state, step):
            increment_revision_count(state, step)
            return await _propose_recommendations(
                state, step, company_name, industry, business_context,
                target_col, model_results, explainability, hypotheses,
                step_context, revision=True,
            )
        return _execute_recommendations(state, step, session_id)
    elif phase == "rejected":
        emit_trace(state, "INFO", step, {
            "message": "Recommendations rejected — step reverted to READY"
        })
        state["recommendations"] = []
        clear_business_proposal(state)
        revert_step_to_ready(state, step)
        state["next_action"] = "orchestrator"
        return state
    else:
        state["next_action"] = "wait"
        return state


async def _propose_recommendations(
    state: AgentState,
    step: str,
    company_name: str,
    industry: str,
    business_context: str,
    target_col: str,
    model_results: dict,
    explainability: dict,
    hypotheses: list,
    step_context: dict,
    revision: bool = False,
) -> AgentState:
    """Generate recommendations and propose for user review."""
    feedback = ""
    if revision:
        feedback = get_proposal_feedback(state, step)

    try:
        models = model_results.get("models", [])
        best_model = next((m for m in models if m.get("best")), models[0] if models else {})
        feature_importance = explainability.get("feature_importance", [])
        top_features = [f["feature"] for f in feature_importance[:10]]
        supported = [
            h for h in hypotheses
            if h.get("result", {}).get("conclusion") == "supported"
        ]

        recommendations = await _llm_recommendations(
            company_name=company_name,
            industry=industry,
            business_context=business_context,
            target_col=target_col,
            model_results=model_results,
            feature_importance=feature_importance,
            hypotheses=hypotheses,
        )

        generation_method = "llm"
        if recommendations is None:
            generation_method = "heuristic"
            recommendations = _heuristic_recommendations(
                business_context=business_context,
                target_col=target_col,
                best_model=best_model,
                top_features=top_features,
                supported=supported,
                company_name=company_name,
            )

        plan = {
            "recommendations": recommendations,
            "method": generation_method,
            "count": len(recommendations),
        }
        rec_titles = [r.get("title", "") for r in recommendations]
        summary = (
            f"Generated {len(recommendations)} VC-focused recommendation(s): "
            f"{'; '.join(rec_titles[:5])}"
        )
        if feedback:
            summary += " (revised based on feedback)"

        emit_trace(state, "AI_REASONING", step, {
            "summary": summary,
            "recommendation_titles": rec_titles,
            "method": generation_method,
            "context_used": bool(step_context.get("session_doc_section")),
        })

        return set_business_proposal(
            state, step, "recommendation", plan, summary,
            f"Generated via {generation_method} analysis of model results and explainability.",
        )

    except Exception as e:
        logger.error("recommendation_node: proposal failed", error=str(e))
        state["error"] = str(e)
        mark_step_failed(state, step)
        return state


def _execute_recommendations(
    state: AgentState, step: str, session_id,
) -> AgentState:
    """Apply the approved recommendations."""
    plan = state.get("pending_proposal_plan", {})
    recommendations = plan.get("recommendations", [])

    state["recommendations"] = recommendations

    emit_trace(state, "TOOL_RESULT", step, {
        "message": f"Recommendations approved: {len(recommendations)} items",
    })

    # Update session doc
    try:
        from session_doc.server import upsert_structured
        sid = str(state.get("session_id", ""))
        rec_titles = [r.get("title", "") for r in recommendations]
        narrative = (
            f"Generated {len(recommendations)} recommendation(s): "
            f"{'; '.join(rec_titles)}."
        )
        upsert_structured(sid, "Recommendations", narrative, metadata={
            "count": len(recommendations),
            "recommendations": [
                {
                    "title": r.get("title", ""),
                    "opportunity_type": r.get("opportunity_type", ""),
                    "confidence": r.get("confidence", 0),
                }
                for r in recommendations
            ],
        })
    except Exception as e:
        logger.warning("recommendation_node: session_doc upsert failed", error=str(e))

    clear_business_proposal(state)
    mark_step_done(state, step)
    state["next_action"] = "orchestrator"
    return state


async def _llm_recommendations(
    *,
    company_name: str,
    industry: str,
    business_context: str,
    target_col: str,
    model_results: dict,
    feature_importance: list,
    hypotheses: list,
) -> list[dict] | None:
    """Call LLM to generate recommendations. Returns None on failure."""
    try:
        from app.agent.llm import invoke_llm
        from app.agent.prompts import RECOMMENDATION_PROMPT

        # Format model results for the prompt
        models = model_results.get("models", [])
        model_summary_lines = []
        for m in models:
            metrics = m.get("metrics", {})
            line = (
                f"- {m.get('model_name', 'Unknown')}: "
                f"F1={metrics.get('f1', 'N/A')}, "
                f"Accuracy={metrics.get('accuracy', 'N/A')}, "
                f"AUC-ROC={metrics.get('roc_auc', 'N/A')}"
            )
            if m.get("best"):
                line += " (BEST)"
            model_summary_lines.append(line)
        model_results_str = "\n".join(model_summary_lines) if model_summary_lines else "No models trained"

        # Format feature importance
        fi_lines = []
        for f in feature_importance[:15]:
            fi_lines.append(f"- {f.get('feature', '?')}: importance={f.get('importance', 'N/A')}")
        fi_str = "\n".join(fi_lines) if fi_lines else "No feature importance available"

        # Format hypothesis results
        hyp_lines = []
        for h in hypotheses:
            result = h.get("result", {})
            hyp_lines.append(
                f"- {h.get('statement', '?')} -> {result.get('conclusion', 'unknown')} "
                f"(p={result.get('p_value', 'N/A')})"
            )
        hyp_str = "\n".join(hyp_lines) if hyp_lines else "No hypothesis tests run"

        prompt = RECOMMENDATION_PROMPT.format(
            company_name=company_name,
            industry=industry,
            business_context=business_context,
            target_column=target_col,
            model_results=model_results_str,
            feature_importance=fi_str,
            hypothesis_results=hyp_str,
        )

        response = await invoke_llm([
            {"role": "system", "content": prompt},
        ])

        parsed = json.loads(response)
        recs = parsed.get("recommendations", [])

        if not isinstance(recs, list) or len(recs) == 0:
            logger.warning("recommendation_node: LLM returned empty or invalid recommendations")
            return None

        # Validate each recommendation has required fields
        validated = []
        for r in recs:
            validated.append({
                "opportunity_type": r.get("opportunity_type", "expansion"),
                "title": r.get("title", "Untitled"),
                "description": r.get("description", ""),
                "confidence": float(r.get("confidence", 0.5)),
                "feasibility": r.get("feasibility", "medium"),
                "supporting_evidence": r.get("supporting_evidence", []),
                "key_features": r.get("key_features", []),
            })

        logger.info("recommendation_node: LLM generated recommendations", count=len(validated))
        return validated

    except Exception as e:
        logger.warning("recommendation_node: LLM call failed, will use fallback", error=str(e))
        return None


def _heuristic_recommendations(
    *,
    business_context: str,
    target_col: str,
    best_model: dict,
    top_features: list[str],
    supported: list[dict],
    company_name: str,
) -> list[dict]:
    """Fallback heuristic recommendations when LLM is unavailable."""
    recommendations: list[dict] = []

    context_lower = business_context.lower()
    target_lower = target_col.lower()
    is_churn = "churn" in context_lower or "churn" in target_lower

    if is_churn:
        churn_features = [
            f for f in top_features
            if any(kw in f.lower() for kw in (
                "usage", "activity", "engagement", "login", "session",
                "call", "support", "complaint", "tenure",
            ))
        ]
        if churn_features:
            recommendations.append({
                "opportunity_type": "churn",
                "title": "Proactive Churn Prevention Program",
                "description": (
                    f"The model identifies {', '.join(churn_features[:3])} as key churn drivers. "
                    f"Implement early warning triggers when these metrics decline, "
                    f"enabling proactive customer outreach before churn occurs."
                ),
                "confidence": best_model.get("metrics", {}).get("f1", 0.0),
                "feasibility": "high",
                "supporting_evidence": [
                    f"Top predictive features: {', '.join(churn_features[:5])}",
                    f"Model F1-score: {best_model.get('metrics', {}).get('f1', 0):.1%}",
                ],
            })

        recommendations.append({
            "opportunity_type": "churn",
            "title": "Customer Retention Scoring",
            "description": (
                f"Deploy the {best_model.get('model_name', 'best')} model to score "
                f"all customers by churn risk. Prioritize retention efforts on "
                f"high-value customers with elevated risk scores."
            ),
            "confidence": best_model.get("metrics", {}).get("roc_auc", 0.0)
            or best_model.get("metrics", {}).get("f1", 0.0),
            "feasibility": "medium",
            "supporting_evidence": [
                f"Best model: {best_model.get('model_name', 'N/A')}",
                f"AUC-ROC: {best_model.get('metrics', {}).get('roc_auc', 'N/A')}",
            ],
        })

    revenue_features = [
        f for f in top_features
        if any(kw in f.lower() for kw in (
            "revenue", "spend", "amount", "value", "purchase",
            "order", "transaction", "product", "plan", "tier",
        ))
    ]
    if revenue_features:
        recommendations.append({
            "opportunity_type": "expansion",
            "title": "Revenue Expansion Targeting",
            "description": (
                f"Features like {', '.join(revenue_features[:3])} show strong predictive power. "
                f"Use these signals to identify customers likely to expand "
                f"their spending with targeted upsell campaigns."
            ),
            "confidence": 0.7,
            "feasibility": "medium",
            "supporting_evidence": [
                f"Revenue-related predictive features: {', '.join(revenue_features[:5])}"
            ],
        })

    if supported:
        significant_vars = []
        for h in supported[:5]:
            significant_vars.extend(h.get("variables", []))
        unique_vars = list(dict.fromkeys(v for v in significant_vars if v != target_col))

        if unique_vars:
            recommendations.append({
                "opportunity_type": "cross_sell",
                "title": "Data-Driven Cross-Sell Strategy",
                "description": (
                    f"Statistical analysis reveals significant relationships between "
                    f"{', '.join(unique_vars[:3])} and {target_col}. "
                    f"Segment customers by these attributes to identify cross-sell opportunities."
                ),
                "confidence": 0.65,
                "feasibility": "medium",
                "supporting_evidence": [
                    f"{len(supported)} statistically significant hypotheses",
                    f"Key variables: {', '.join(unique_vars[:5])}",
                ],
            })

    if best_model:
        metrics = best_model.get("metrics", {})
        recommendations.append({
            "opportunity_type": "upsell",
            "title": "Predictive Model Deployment",
            "description": (
                f"Deploy the {best_model.get('model_name', 'best')} model "
                f"(F1: {metrics.get('f1', 0):.1%}, Accuracy: {metrics.get('accuracy', 0):.1%}) "
                f"into {company_name}'s operational systems for real-time scoring. "
                f"This enables automated identification of upsell and retention opportunities."
            ),
            "confidence": metrics.get("f1", 0.0),
            "feasibility": "low",
            "supporting_evidence": [
                f"Model metrics: {metrics}",
                f"Top features: {', '.join(top_features[:5])}",
            ],
        })

    recommendations.append({
        "opportunity_type": "expansion",
        "title": "Data Infrastructure Enhancement",
        "description": (
            "Invest in improving data collection and quality for the identified "
            "key features. Better data leads to more accurate predictions and "
            "higher-confidence targeting for value creation initiatives."
        ),
        "confidence": 0.8,
        "feasibility": "high",
        "supporting_evidence": [
            "Foundation for all ML-driven value creation",
            f"Currently using {len(top_features)} predictive features",
        ],
    })

    return recommendations
