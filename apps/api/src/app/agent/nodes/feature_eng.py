"""Feature engineering node — proposes feature engineering with proposal/approval loop.

Proposes scaling, polynomial features, and interaction features as a
business-logic Proposal. User can approve, request changes, or reject.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Any

import pandas as pd
import structlog

from app.agent.llm import invoke_llm_json
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
from app.agent.prompts import FEATURE_ENG_PLANNING_PROMPT
from app.agent.state import AgentState
from app.config import settings

logger = structlog.get_logger()

_mcp_root = str(Path(__file__).resolve().parents[6] / "packages" / "mcp-servers" / "src")
if _mcp_root not in sys.path:
    sys.path.insert(0, _mcp_root)

STEP = "feature_eng"

_DEFAULT_PLAN: dict[str, Any] = {
    "scaling": {"method": "standard", "columns": []},
    "polynomial": {"enabled": False, "columns": [], "degree": 2},
    "interactions": {"enabled": False, "column_pairs": []},
    "reasoning": "Fallback: standard scaling on all numeric features.",
}


def _summarize_eda(state: AgentState) -> str:
    """Extract a short summary of EDA insights."""
    eda = state.get("eda_results", {})
    if not eda:
        return "No EDA results available."
    parts = []
    if eda.get("plots"):
        parts.append(f"{len(eda['plots'])} plots generated")
    return "; ".join(parts) if parts else "EDA completed."


def _summarize_hypotheses(state: AgentState) -> str:
    """Extract a short summary of hypothesis test results."""
    hypotheses = state.get("hypotheses", [])
    if not hypotheses:
        return "No hypothesis results available."
    parts = []
    for h in hypotheses[:5]:
        name = h.get("name", h.get("hypothesis", h.get("statement", "?")))
        result = h.get("result", h.get("conclusion", "?"))
        if isinstance(result, dict):
            result = result.get("conclusion", "?")
        parts.append(f"- {name}: {result}")
    return "\n".join(parts)


async def _plan_feature_eng(
    state: AgentState,
    step_context: dict[str, Any],
) -> dict[str, Any]:
    """Ask the LLM to plan feature engineering."""
    df_path = state.get("cleaned_df_path") or state.get("merged_df_path", "")
    current_features: list[str] = []
    target_col = state.get("target_column", "")

    if df_path:
        try:
            p = Path(df_path)
            if not p.is_absolute():
                p = Path(settings.upload_dir) / df_path
            if str(p).endswith(".csv"):
                df = pd.read_csv(str(p), nrows=5)
            else:
                df = pd.read_excel(str(p), nrows=5, engine="openpyxl")
            current_features = list(df.columns)
        except Exception:
            pass

    if not current_features:
        profiles = state.get("column_profiles", [])
        current_features = [
            p.get("column_name", "") for p in profiles if p.get("column_name")
        ]

    prompt_vars = {
        "current_features": ", ".join(current_features) if current_features else "Unknown",
        "target_column": target_col,
        "eda_insights": _summarize_eda(state),
        "hypothesis_results": _summarize_hypotheses(state),
        "session_doc_section": step_context.get("session_doc_section", ""),
        "strategy_hint": step_context.get("strategy_hint", ""),
        "denial_feedback": "\n".join(step_context.get("denial_feedback", [])) or "None",
    }

    try:
        result = await invoke_llm_json(
            [
                {"role": "system", "content": FEATURE_ENG_PLANNING_PROMPT.format(**prompt_vars)},
                {"role": "user", "content": "Plan the feature engineering."},
            ],
            schema_hint='{"scaling": {...}, "polynomial": {...}, "interactions": {...}, '
                        '"reasoning": "..."}',
        )

        valid_methods = {"standard", "minmax", "robust"}
        scaling = result.get("scaling", {})
        if scaling.get("method") not in valid_methods:
            scaling["method"] = "standard"
        if not scaling.get("columns"):
            scaling["columns"] = []

        return {
            "scaling": scaling,
            "polynomial": result.get(
                "polynomial", {"enabled": False, "columns": [], "degree": 2}
            ),
            "interactions": result.get(
                "interactions", {"enabled": False, "column_pairs": []}
            ),
            "reasoning": result.get("reasoning", ""),
        }
    except Exception as e:
        logger.warning("feature_eng: LLM planning failed", error=str(e))
        return dict(_DEFAULT_PLAN)


async def feature_eng_node(state: AgentState) -> AgentState:
    """Engineer features with business proposal loop."""
    logger.info("feature_eng_node: executing", session_id=str(state.get("session_id")))
    state["current_step"] = STEP

    step_context = read_step_context(state, STEP)

    phase = check_proposal_phase(state, STEP)

    if phase == "propose":
        return await _propose_feature_eng(state, step_context)
    elif phase == "execute":
        return await _execute_feature_eng(state)
    elif phase == "revision_requested":
        if should_revise(state, STEP):
            increment_revision_count(state, STEP)
            return await _propose_feature_eng(state, step_context, revision=True)
        return await _execute_feature_eng(state)
    elif phase == "rejected":
        emit_trace(state, "INFO", STEP, {
            "message": "Feature engineering rejected; using raw features"
        })
        df_path = state.get("cleaned_df_path") or state.get("merged_df_path", "")
        state["features_df_path"] = df_path
        state["feature_plan"] = {"status": "skipped", "reason": "rejected"}
        clear_business_proposal(state)
        mark_step_done(state, STEP)
        state["next_action"] = "orchestrator"
        return state
    else:
        state["next_action"] = "wait"
        return state


async def _propose_feature_eng(
    state: AgentState,
    step_context: dict,
    revision: bool = False,
) -> AgentState:
    """Generate feature engineering proposal via LLM."""
    feedback = ""
    if revision:
        feedback = get_proposal_feedback(state, STEP)

    if feedback:
        step_context = dict(step_context)
        step_context["denial_feedback"] = [feedback]

    plan = await _plan_feature_eng(state, step_context)

    # Store for execution
    node_plans = dict(state.get("node_plans", {}))
    node_plans[STEP] = plan
    state["node_plans"] = node_plans

    scaling = plan.get("scaling", {})
    method_label = {
        "standard": "StandardScaler",
        "minmax": "MinMaxScaler",
        "robust": "RobustScaler",
    }.get(scaling.get("method", "standard"), scaling.get("method", "standard"))

    parts = [f"Scale numeric features using {method_label}"]
    if plan.get("polynomial", {}).get("enabled"):
        degree = plan["polynomial"].get("degree", 2)
        parts.append(f"polynomial features (degree {degree})")
    if plan.get("interactions", {}).get("enabled"):
        parts.append("interaction features")

    summary = "Feature engineering: " + ", ".join(parts)
    if feedback:
        summary += " (revised based on feedback)"

    reasoning = plan.get("reasoning", "LLM-planned feature engineering")

    emit_trace(state, "AI_REASONING", STEP, {
        "message": summary,
        "plan": plan,
    })

    return set_business_proposal(
        state, STEP, "feature_eng", plan, summary, reasoning,
    )


async def _execute_feature_eng(state: AgentState) -> AgentState:
    """Execute the approved feature engineering plan."""
    plan = state.get("pending_proposal_plan", {})
    if not plan.get("scaling"):
        plan = state.get("node_plans", {}).get(STEP, dict(_DEFAULT_PLAN))

    df_path = state.get("cleaned_df_path") or state.get("merged_df_path", "")
    if not df_path:
        state["error"] = "No dataframe path for feature engineering"
        clear_business_proposal(state)
        mark_step_done(state, STEP)
        state["next_action"] = "orchestrator"
        return state

    try:
        from preprocessing.server import create_polynomial_features, scale_numeric

        p = Path(df_path)
        if not p.is_absolute():
            p = Path(settings.upload_dir) / df_path
        input_path = str(p)

        if input_path.endswith(".csv"):
            df = pd.read_csv(input_path, nrows=1000)
        else:
            df = pd.read_excel(input_path, nrows=1000, engine="openpyxl")

        target_col = state.get("target_column", "")
        numeric_cols = list(df.select_dtypes(include=["number"]).columns)
        exclude = {
            target_col.lower(), "id", "customerid", "customer_id", "index", "row_number"
        }
        numeric_cols = [c for c in numeric_cols if c.lower() not in exclude]

        # Filter to selected features if specified
        selected = state.get("selected_features")
        if selected:
            selected_lower = {s.lower() for s in selected}
            numeric_cols = [c for c in numeric_cols if c.lower() in selected_lower]

        if not numeric_cols:
            state["features_df_path"] = input_path
            state["feature_plan"] = {"status": "skipped", "reason": "no_numeric_columns"}
            clear_business_proposal(state)
            mark_step_done(state, STEP)
            state["next_action"] = "orchestrator"
            return state

        output_dir = Path(settings.upload_dir) / "features"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(output_dir / f"features_{uuid.uuid4().hex[:8]}.csv")

        scaling = plan.get("scaling", {"method": "standard", "columns": []})
        polynomial = plan.get("polynomial", {"enabled": False, "columns": [], "degree": 2})
        interactions = plan.get("interactions", {"enabled": False, "column_pairs": []})

        all_changes: list[str] = []

        # Step 1: Polynomial features
        if polynomial.get("enabled"):
            poly_cols = polynomial.get("columns", [])
            if poly_cols:
                poly_cols = [c for c in poly_cols if c in numeric_cols]
            if not poly_cols:
                poly_cols = numeric_cols[:5]
            degree = polynomial.get("degree", 2)

            poly_result = create_polynomial_features(
                file_path=input_path,
                columns=poly_cols,
                degree=degree,
                output_path=output_path,
            )
            if poly_result.success:
                input_path = poly_result.output_path
                all_changes.append(poly_result.changes_summary)

        # Step 2: Interaction features
        if interactions.get("enabled"):
            try:
                from preprocessing.server import (
                    create_interaction_features as create_interactions,
                )
                pairs = interactions.get("column_pairs", [])
                if pairs:
                    all_cols_set = set(df.columns)
                    valid_pairs = [
                        pair for pair in pairs
                        if isinstance(pair, (list, tuple))
                        and len(pair) == 2
                        and pair[0] in all_cols_set
                        and pair[1] in all_cols_set
                    ]
                    if valid_pairs:
                        int_result = create_interactions(
                            file_path=input_path,
                            column_pairs=valid_pairs,
                            output_path=output_path,
                        )
                        if int_result.success:
                            input_path = int_result.output_path
                            all_changes.append(int_result.changes_summary)
            except Exception as e:
                logger.warning("feature_eng: interaction features failed", error=str(e))

        # Step 3: Scale numeric features
        method = scaling.get("method", "standard")
        result = scale_numeric(
            file_path=input_path,
            columns=numeric_cols,
            method=method,
            output_path=output_path,
        )
        all_changes.append(result.changes_summary)

        method_label = {
            "standard": "StandardScaler",
            "minmax": "MinMaxScaler",
            "robust": "RobustScaler",
        }.get(method, method)

        state["features_df_path"] = result.output_path
        state["feature_plan"] = {
            "status": "completed",
            "scaled_columns": numeric_cols,
            "strategy": method_label,
            "polynomial_enabled": polynomial.get("enabled", False),
            "interactions_enabled": interactions.get("enabled", False),
            "changes": "; ".join(all_changes),
        }

        emit_trace(state, "TOOL_RESULT", STEP, {
            "message": f"Feature engineering completed: {method_label}",
            "scaled_columns": len(numeric_cols),
            "changes": all_changes,
        })

        # Update session doc
        try:
            from session_doc.server import upsert_structured
            sid = str(state.get("session_id", ""))
            extra = []
            if polynomial.get("enabled"):
                extra.append(f"polynomial (degree {polynomial.get('degree', 2)})")
            if interactions.get("enabled"):
                extra.append("interactions")
            extra_str = f" Also: {', '.join(extra)}." if extra else ""
            narrative = (
                f"Scaled {len(numeric_cols)} column(s) using {method_label}."
                f"{extra_str}"
            )
            upsert_structured(sid, "Feature Engineering", narrative, metadata={
                "scaling_method": method,
                "scaled_columns": numeric_cols,
                "polynomial_enabled": polynomial.get("enabled", False),
                "polynomial_degree": polynomial.get("degree", 2),
                "interactions_enabled": interactions.get("enabled", False),
                "output_path": result.output_path,
            })
        except Exception as e:
            logger.warning("feature_eng: session_doc upsert failed", error=str(e))

    except Exception as e:
        logger.error("feature_eng: failed", error=str(e))
        state["error"] = str(e)

    clear_business_proposal(state)
    mark_step_done(state, STEP)
    state["next_action"] = "orchestrator"
    return state
