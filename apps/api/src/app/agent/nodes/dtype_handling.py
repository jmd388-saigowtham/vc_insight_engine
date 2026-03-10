"""Dtype handling node — autonomous type inference and correction.

Reads column profiles from the profiling step, uses the dtype_manager
MCP tool to suggest type corrections, and proposes a dtype plan for
user approval. On approval, executes type corrections.
"""

from __future__ import annotations

from typing import Any

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


async def dtype_handling_node(state: AgentState) -> AgentState:
    """Dtype handling: infer correct types and propose corrections."""
    step = "dtype_handling"
    session_id = str(state.get("session_id", ""))
    logger.info("dtype_handling_node: executing", session_id=session_id)

    emit_trace(state, "TOOL_CALL", step, {"message": "Analyzing column data types"})

    phase = check_proposal_phase(state, step)

    if phase == "propose":
        return await _propose_dtype_plan(state, step)
    elif phase == "execute":
        return await _execute_dtype_plan(state, step)
    elif phase == "revision_requested":
        if should_revise(state, step):
            increment_revision_count(state, step)
            return await _propose_dtype_plan(state, step, revision=True)
        clear_business_proposal(state)
        mark_step_done(state, step)
        state["next_action"] = "orchestrator"
        return state
    elif phase == "rejected":
        # User rejected — skip dtype corrections, proceed with original types
        emit_trace(state, "INFO", step, {
            "message": "Dtype corrections rejected; proceeding with original types"
        })
        clear_business_proposal(state)
        mark_step_done(state, step)
        state["next_action"] = "orchestrator"
        return state
    else:
        # skip
        state["next_action"] = "wait"
        return state


async def _propose_dtype_plan(
    state: AgentState, step: str, revision: bool = False
) -> AgentState:
    """Analyze column profiles and propose type corrections."""
    column_profiles = state.get("column_profiles", [])

    if not column_profiles:
        emit_trace(state, "INFO", step, {
            "message": "No column profiles available; skipping dtype handling"
        })
        mark_step_done(state, step)
        state["next_action"] = "orchestrator"
        return state

    # Try MCP tool for type suggestions
    corrections: list[dict[str, Any]] = []
    try:
        for profile in column_profiles:
            col_name = profile.get("column_name", "")
            current_type = profile.get("data_type", "")
            null_pct = profile.get("null_pct", 0)
            sample_values = profile.get("sample_values", [])

            # Simple heuristic-based suggestions
            suggested_type = _suggest_type(current_type, sample_values, col_name)
            if suggested_type and suggested_type != current_type:
                corrections.append({
                    "column": col_name,
                    "current_type": current_type,
                    "suggested_type": suggested_type,
                    "null_pct": null_pct,
                    "reasoning": _type_reasoning(
                        col_name, current_type, suggested_type, sample_values
                    ),
                })
    except Exception as e:
        logger.warning("dtype_handling: tool call failed", error=str(e))

    if not corrections:
        emit_trace(state, "INFO", step, {
            "message": "No dtype corrections needed; all types look correct"
        })
        state["dtype_decisions"] = {"corrections": [], "status": "no_changes_needed"}

        # Write to session doc even when no corrections needed
        try:
            from session_doc.server import upsert_structured
            sid = str(state.get("session_id", ""))
            upsert_structured(
                sid, "Dtype Decisions",
                f"All {len(column_profiles)} columns have correct types. No corrections needed.",
                metadata={"corrections": [], "status": "no_changes_needed",
                          "total_columns": len(column_profiles)},
            )
        except Exception as e:
            logger.warning("dtype_handling: session_doc write failed", error=str(e))

        mark_step_done(state, step)
        state["next_action"] = "orchestrator"
        return state

    feedback = ""
    if revision:
        feedback = get_proposal_feedback(state, step)

    plan = {
        "corrections": corrections,
        "total_columns": len(column_profiles),
        "columns_to_fix": len(corrections),
    }

    summary = (
        f"Proposing {len(corrections)} type corrections "
        f"out of {len(column_profiles)} columns"
    )
    if feedback:
        summary += f" (revised based on feedback: {feedback})"

    reasoning = "Analyzed column profiles and sample values to detect type mismatches."
    if corrections:
        reasoning += " Corrections: " + "; ".join(
            f"{c['column']}: {c['current_type']} → {c['suggested_type']}"
            for c in corrections[:5]
        )

    return set_business_proposal(
        state, step, "dtype_plan", plan, summary, reasoning
    )


async def _execute_dtype_plan(state: AgentState, step: str) -> AgentState:
    """Execute approved dtype corrections."""
    plan = state.get("pending_proposal_plan", {})
    corrections = plan.get("corrections", [])

    emit_trace(state, "TOOL_CALL", step, {
        "message": f"Applying {len(corrections)} dtype corrections"
    })

    state["dtype_decisions"] = {
        "corrections": corrections,
        "status": "applied",
    }

    emit_trace(state, "TOOL_RESULT", step, {
        "message": f"Applied {len(corrections)} dtype corrections",
        "corrections": corrections,
    })

    clear_business_proposal(state)

    # Write dtype decisions to session memory
    try:
        from session_doc.server import upsert_structured
        sid = str(state.get("session_id", ""))
        narrative = f"Applied {len(corrections)} dtype corrections."
        if corrections:
            narrative += " Changes: " + "; ".join(
                f"{c['column']}: {c['current_type']} → {c['suggested_type']}"
                for c in corrections[:5]
            )
        upsert_structured(sid, "Dtype Decisions", narrative, metadata={
            "corrections": corrections,
            "status": "applied",
        })
    except Exception as e:
        logger.warning("dtype_handling: session_doc write failed", error=str(e))

    mark_step_done(state, step)
    state["next_action"] = "orchestrator"
    return state


def _suggest_type(
    current_type: str, sample_values: list, col_name: str
) -> str | None:
    """Simple heuristic to suggest correct types."""
    name_lower = col_name.lower()

    # Date columns stored as object/string
    if current_type in ("object", "string", "str"):
        date_keywords = ["date", "time", "created", "updated", "timestamp", "dob"]
        if any(kw in name_lower for kw in date_keywords):
            return "datetime64"

    # ID columns that are numeric but should be string
    if current_type in ("int64", "float64"):
        id_keywords = ["_id", "id_", "zip", "postal", "phone", "code"]
        if any(kw in name_lower for kw in id_keywords):
            return "object"

    # Float columns that are actually integers (no fractional values)
    if current_type == "float64" and sample_values:
        if all(
            isinstance(v, (int, float)) and float(v) == int(v)
            for v in sample_values
            if v is not None
        ):
            bool_keywords = ["is_", "has_", "flag", "active", "churned"]
            if any(kw in name_lower for kw in bool_keywords):
                return "bool"

    return None


def _type_reasoning(
    col_name: str,
    current: str,
    suggested: str,
    sample_values: list,
) -> str:
    """Generate reasoning for a type correction."""
    if suggested == "datetime64":
        return f"Column '{col_name}' appears to contain date values but is stored as {current}"
    if suggested == "object" and current in ("int64", "float64"):
        return f"Column '{col_name}' appears to be an identifier, not a numeric value"
    if suggested == "bool":
        return f"Column '{col_name}' contains only 0/1 values and appears to be a boolean flag"
    return f"Type mismatch: {current} → {suggested} for column '{col_name}'"
