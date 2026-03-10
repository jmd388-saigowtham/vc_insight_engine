"""Feature selection node — LLM suggests features with proposal/approval loop.

Proposes a feature set as a business-logic Proposal with per-feature
reasoning. User can add/remove features. From this point downstream,
only approved features + later approved engineered features may be used.
"""

from __future__ import annotations

import json

import structlog

from app.agent.llm import invoke_llm
from app.agent.nodes.approval_helpers import (
    check_proposal_phase,
    clear_business_proposal,
    get_proposal_feedback,
    increment_revision_count,
    mark_step_done,
    set_business_proposal,
    should_revise,
)
from app.agent.nodes.node_helpers import emit_trace, read_step_context
from app.agent.prompts import FEATURE_SELECTION_PROMPT
from app.agent.state import AgentState

logger = structlog.get_logger()


def _format_column_profiles(profiles: list[dict]) -> str:
    """Format column profiles for the LLM prompt."""
    lines = []
    for p in profiles:
        name = p.get("column_name", p.get("name", "unknown"))
        dtype = p.get("data_type", p.get("dtype", "unknown"))
        null_pct = p.get("null_pct", 0)
        unique = p.get("unique_count", "?")
        lines.append(f"- {name} ({dtype}): {null_pct:.1f}% nulls, {unique} unique values")
    return "\n".join(lines) or "No column profiles available"


async def feature_selection_node(state: AgentState) -> AgentState:
    """Use LLM to suggest features with proposal loop for user review."""
    step = "feature_selection"
    logger.info("feature_selection_node: executing", session_id=str(state.get("session_id")))
    state["current_step"] = step

    read_step_context(state, step)

    target_col = state.get("target_column", "")
    if not target_col:
        state["error"] = "No target column identified for feature selection"
        return state

    profiles = state.get("column_profiles", [])
    if not profiles:
        state["error"] = "No column profiles available for feature selection"
        return state

    phase = check_proposal_phase(state, step)

    if phase == "propose":
        return await _propose_features(state, step, target_col, profiles)
    elif phase == "execute":
        return await _execute_features(state, step, target_col)
    elif phase == "revision_requested":
        if should_revise(state, step):
            increment_revision_count(state, step)
            return await _propose_features(
                state, step, target_col, profiles, revision=True
            )
        # Max revisions — use current proposal as-is
        return await _execute_features(state, step, target_col)
    elif phase == "rejected":
        emit_trace(state, "INFO", step, {
            "message": "Feature selection rejected; using all numeric columns"
        })
        feature_names = _fallback_features(profiles, target_col)
        state["selected_features"] = feature_names
        clear_business_proposal(state)
        mark_step_done(state, step)
        state["next_action"] = "orchestrator"
        return state
    else:
        state["next_action"] = "wait"
        return state


async def _propose_features(
    state: AgentState,
    step: str,
    target_col: str,
    profiles: list[dict],
    revision: bool = False,
) -> AgentState:
    """Generate feature selection proposal via LLM."""
    feedback = ""
    if revision:
        feedback = get_proposal_feedback(state, step)

    try:
        prompt = FEATURE_SELECTION_PROMPT.format(
            company_name=state.get("company_name", "Unknown"),
            industry=state.get("industry", "Unknown"),
            business_context=state.get("business_context", "Not provided"),
            target_column=target_col,
            column_profiles=_format_column_profiles(profiles),
        )

        if feedback:
            prompt += f"\n\n## User Feedback for Revision\n{feedback}"

        response = await invoke_llm([
            {"role": "system", "content": prompt},
            {"role": "user", "content": "Select features for the model. Respond with JSON only."},
        ])

        cleaned = response.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]
            cleaned = cleaned.rsplit("```", 1)[0]

        parsed = json.loads(cleaned)
        features = parsed.get("features", [])
        excluded = parsed.get("excluded", [])

        feature_list = [
            {
                "name": f.get("name", ""),
                "importance": f.get("importance", 0.5),
                "reasoning": f.get("reasoning", f.get("reason", "")),
            }
            for f in features
            if isinstance(f, dict) and "name" in f
        ]

        feature_names = [f["name"] for f in feature_list if f["name"] != target_col]

        plan = {
            "features": feature_list,
            "excluded": excluded,
            "target_column": target_col,
            "total_columns": len(profiles),
            "selected_count": len(feature_names),
        }

        summary = (
            f"Selected {len(feature_names)} features out of {len(profiles)} columns "
            f"for target '{target_col}'"
        )
        if feedback:
            summary += " (revised based on feedback)"

        reasoning = parsed.get("reasoning", "LLM-based feature selection")
        if isinstance(reasoning, list):
            reasoning = "; ".join(str(r) for r in reasoning)

        emit_trace(state, "AI_REASONING", step, {
            "message": summary,
            "feature_count": len(feature_names),
        })

        return set_business_proposal(
            state, step, "feature_selection", plan, summary, str(reasoning)
        )

    except Exception as e:
        logger.error("feature_selection_node: LLM failed", error=str(e))
        # Fallback: propose all numeric columns
        feature_names = _fallback_features(profiles, target_col)
        plan = {
            "features": [{"name": f, "importance": 0.5, "reasoning": "Fallback"} for f in feature_names],
            "excluded": [],
            "target_column": target_col,
            "total_columns": len(profiles),
            "selected_count": len(feature_names),
        }
        return set_business_proposal(
            state,
            step,
            "feature_selection",
            plan,
            f"Fallback: {len(feature_names)} numeric features (LLM unavailable)",
            "LLM failed; using all numeric columns as default.",
        )


async def _execute_features(
    state: AgentState, step: str, target_col: str
) -> AgentState:
    """Apply the approved feature selection."""
    plan = state.get("pending_proposal_plan", {})
    features = plan.get("features", [])

    feature_names = [
        f["name"] for f in features
        if isinstance(f, dict) and f.get("name") and f["name"] != target_col
    ]

    if not feature_names:
        # Last resort fallback
        profiles = state.get("column_profiles", [])
        feature_names = _fallback_features(profiles, target_col)

    state["selected_features"] = feature_names

    # Store in session_doc
    try:
        from session_doc.server import upsert_structured
        sid = str(state.get("session_id", ""))
        narrative = f"Target: {target_col}\n"
        narrative += f"Selected features ({len(feature_names)}): {', '.join(feature_names[:20])}\n"
        excluded = plan.get("excluded", [])
        excluded_names = []
        if excluded:
            excluded_names = [e.get("name", "") for e in excluded[:10] if isinstance(e, dict)]
            narrative += f"Excluded: {', '.join(excluded_names)}\n"
        upsert_structured(sid, "Feature Selection", narrative, metadata={
            "target_column": target_col,
            "selected_features": feature_names,
            "excluded_features": excluded_names,
        })
    except Exception as e:
        logger.warning("feature_selection_node: session_doc upsert failed", error=str(e))

    emit_trace(state, "TOOL_RESULT", step, {
        "message": f"Feature selection approved: {len(feature_names)} features",
        "features": feature_names[:20],
    })

    clear_business_proposal(state)
    mark_step_done(state, step)
    state["next_action"] = "orchestrator"
    return state


def _fallback_features(profiles: list[dict], target_col: str) -> list[str]:
    """Fallback: select all numeric columns except target."""
    return [
        p.get("column_name", p.get("name", ""))
        for p in profiles
        if p.get("data_type", p.get("dtype", "")) in (
            "int64", "float64", "int32", "float32", "number"
        )
        and p.get("column_name", p.get("name", "")) != target_col
    ]
