"""Preprocessing node — proposes preprocessing strategy with proposal/approval loop.

Proposes a preprocessing strategy (missing values, encoding) as a business-logic
Proposal. User can approve, override strategies per column, or reject.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pandas as pd
import structlog

from app.agent.llm import invoke_llm_json
from app.agent.nodes.approval_helpers import (
    check_proposal_phase,
    clear_business_proposal,
    get_proposal_feedback,
    increment_revision_count,
    mark_step_done,
    mark_step_failed,
    set_business_proposal,
    should_revise,
)
from app.agent.nodes.node_helpers import emit_trace, read_step_context, update_session_memory_md
from app.agent.prompts import PREPROCESSING_PLANNING_PROMPT
from app.agent.state import AgentState
from app.config import settings

logger = structlog.get_logger()

# Ensure MCP servers package is importable
_mcp_root = str(Path(__file__).resolve().parents[6] / "packages" / "mcp-servers" / "src")
if _mcp_root not in sys.path:
    sys.path.insert(0, _mcp_root)

STEP = "preprocessing"

# Default preprocessing plan when LLM planning fails
_DEFAULT_PREPROCESSING_PLAN: dict = {
    "missing_strategy": {
        "numeric_default": "median",
        "categorical_default": "mode",
        "drop_high_null_threshold": 0.5,
        "column_overrides": {},
    },
    "encoding": {
        "method": "label",
        "column_overrides": {},
    },
    "reasoning": "Fallback: median for numeric, mode for categorical, label encoding.",
}


async def _plan_preprocessing(state: AgentState, step_context: dict) -> dict:
    """Ask the LLM to decide the preprocessing strategy."""
    column_profiles = state.get("column_profiles", [])
    target_col = state.get("target_column", "")

    profile_lines: list[str] = []
    missing_lines: list[str] = []
    categorical_cols: list[str] = []

    for cp in column_profiles[:60]:
        name = cp.get("column_name", cp.get("name", "?"))
        dtype = cp.get("data_type", cp.get("dtype", "?"))
        null_pct = cp.get("null_percentage", cp.get("null_pct", 0))
        unique = cp.get("unique_count", "?")
        profile_lines.append(f"- {name} ({dtype}): {null_pct:.1f}% null, {unique} unique")
        if null_pct > 0:
            missing_lines.append(f"- {name}: {null_pct:.1f}% null ({dtype})")
        if dtype in ("object", "category", "string", "categorical"):
            categorical_cols.append(f"{name} ({unique} unique)")

    prompt_text = PREPROCESSING_PLANNING_PROMPT.format(
        column_profiles="\n".join(profile_lines) or "No profiles available.",
        target_column=target_col or "Not set",
        missing_summary="\n".join(missing_lines) or "No missing values.",
        categorical_columns=", ".join(categorical_cols) or "None",
        session_doc_section=step_context.get("session_doc_section", ""),
        strategy_hint=step_context.get("strategy_hint", ""),
        denial_feedback="\n".join(step_context.get("denial_feedback", [])) or "None",
    )

    try:
        plan = await invoke_llm_json(
            [{"role": "system", "content": prompt_text}],
            schema_hint=(
                '{"missing_strategy": {"numeric_default": "...", '
                '"categorical_default": "...", "drop_high_null_threshold": 0.5, '
                '"column_overrides": {}}, "encoding": {"method": "...", '
                '"column_overrides": {}}, "reasoning": "..."}'
            ),
        )
        if "missing_strategy" not in plan or "encoding" not in plan:
            return _DEFAULT_PREPROCESSING_PLAN
        return plan
    except Exception as e:
        logger.warning("_plan_preprocessing: LLM failed", error=str(e))
        return _DEFAULT_PREPROCESSING_PLAN


async def preprocessing_node(state: AgentState) -> AgentState:
    """Handle missing values and encode categoricals with proposal loop."""
    logger.info("preprocessing_node: executing", session_id=str(state.get("session_id")))
    state["current_step"] = STEP

    step_context = read_step_context(state, STEP)

    phase = check_proposal_phase(state, STEP)

    if phase == "propose":
        return await _propose_preprocessing(state, step_context)
    elif phase == "execute":
        return await _execute_preprocessing(state)
    elif phase == "revision_requested":
        if should_revise(state, STEP):
            increment_revision_count(state, STEP)
            return await _propose_preprocessing(state, step_context, revision=True)
        return await _execute_preprocessing(state)
    elif phase == "rejected":
        emit_trace(state, "INFO", STEP, {
            "message": "Preprocessing plan rejected; using raw data"
        })
        # Use existing data path without preprocessing
        df_path = state.get("merged_df_path", "")
        state["cleaned_df_path"] = df_path
        state["preprocessing_plan"] = {"status": "skipped", "reason": "rejected"}
        clear_business_proposal(state)
        mark_step_done(state, STEP)
        state["next_action"] = "orchestrator"
        return state
    else:
        state["next_action"] = "wait"
        return state


async def _propose_preprocessing(
    state: AgentState,
    step_context: dict,
    revision: bool = False,
) -> AgentState:
    """Generate preprocessing proposal via LLM."""
    feedback = ""
    if revision:
        feedback = get_proposal_feedback(state, STEP)

    if feedback:
        step_context = dict(step_context)
        step_context["denial_feedback"] = [feedback]

    plan = await _plan_preprocessing(state, step_context)

    # Store for execution
    node_plans = dict(state.get("node_plans", {}))
    node_plans[STEP] = plan
    state["node_plans"] = node_plans

    missing = plan.get("missing_strategy", {})
    encoding = plan.get("encoding", {})

    summary_parts = []
    summary_parts.append(
        f"Missing values: {missing.get('numeric_default', 'median')} (numeric), "
        f"{missing.get('categorical_default', 'mode')} (categorical)"
    )
    threshold = missing.get("drop_high_null_threshold")
    if threshold and threshold < 1.0:
        summary_parts.append(f"drop cols >{threshold * 100:.0f}% null")
    summary_parts.append(f"Encoding: {encoding.get('method', 'label')}")

    summary = "Preprocessing: " + "; ".join(summary_parts)
    if feedback:
        summary += " (revised based on feedback)"

    reasoning = plan.get("reasoning", "LLM-planned preprocessing")

    emit_trace(state, "AI_REASONING", STEP, {
        "message": summary,
        "missing_strategy": missing,
        "encoding": encoding,
    })

    proposal_plan = {
        "missing_strategy": missing,
        "encoding": encoding,
        "reasoning": reasoning,
    }

    return set_business_proposal(
        state, STEP, "preprocessing", proposal_plan, summary, reasoning,
    )


async def _execute_preprocessing(state: AgentState) -> AgentState:
    """Execute the approved preprocessing plan."""
    emit_trace(state, "PLAN", STEP, {
        "message": "Executing approved preprocessing plan..."
    })

    plan = state.get("pending_proposal_plan", {})
    if not plan.get("missing_strategy"):
        plan = state.get("node_plans", {}).get(STEP, _DEFAULT_PREPROCESSING_PLAN)

    df_path = state.get("merged_df_path", "")
    if not df_path:
        state["error"] = "No dataframe path for preprocessing"
        clear_business_proposal(state)
        mark_step_done(state, STEP)
        state["next_action"] = "orchestrator"
        return state

    try:
        from preprocessing.server import encode_categorical, handle_missing

        p = Path(df_path)
        if not p.is_absolute():
            p = Path(settings.upload_dir) / df_path
        input_path = str(p)

        if input_path.endswith(".csv"):
            df = pd.read_csv(input_path, nrows=1000)
        else:
            df = pd.read_excel(input_path, nrows=1000, engine="openpyxl")

        output_dir = Path(settings.upload_dir) / "preprocessed"
        output_dir.mkdir(parents=True, exist_ok=True)

        changes: list[str] = []

        # Dtype suggestions
        try:
            from dtype_manager.server import suggest_types
            suggestions = suggest_types(file_path=input_path)
            if suggestions and hasattr(suggestions, "suggestions"):
                type_changes = [
                    f"{s.column}: {s.current_type} -> {s.suggested_type}"
                    for s in suggestions.suggestions
                    if s.current_type != s.suggested_type
                ]
                if type_changes:
                    changes.append(f"Type suggestions: {'; '.join(type_changes[:10])}")
        except Exception as e:
            logger.warning("preprocessing_node: dtype_manager failed", error=str(e))

        missing_strategy = plan.get("missing_strategy", {})
        encoding_plan = plan.get("encoding", {})

        numeric_default = missing_strategy.get("numeric_default", "median")
        categorical_default = missing_strategy.get("categorical_default", "mode")
        drop_threshold = missing_strategy.get("drop_high_null_threshold", 0.5)
        column_overrides = missing_strategy.get("column_overrides", {})
        encoding_method = encoding_plan.get("method", "label")
        encoding_overrides = encoding_plan.get("column_overrides", {})

        target_col = state.get("target_column", "")

        # Drop high-null columns
        if drop_threshold and drop_threshold < 1.0:
            high_null_cols = [
                col for col in df.columns
                if df[col].isna().mean() > drop_threshold and col != target_col
            ]
            if high_null_cols:
                if input_path.endswith(".csv"):
                    full_df = pd.read_csv(input_path)
                else:
                    full_df = pd.read_excel(input_path, engine="openpyxl")
                full_df = full_df.drop(columns=high_null_cols)
                drop_output = str(output_dir / f"dropped_{uuid.uuid4().hex[:8]}.csv")
                full_df.to_csv(drop_output, index=False)
                input_path = drop_output
                df = df.drop(columns=[c for c in high_null_cols if c in df.columns])
                changes.append(
                    f"Dropped {len(high_null_cols)} high-null columns: "
                    f"{', '.join(high_null_cols[:5])}"
                )

        # Handle missing values
        null_cols = {
            col: int(df[col].isna().sum()) for col in df.columns if df[col].isna().any()
        }
        if null_cols:
            strategy: dict[str, str] = {}
            for col in null_cols:
                if col in column_overrides:
                    strategy[col] = column_overrides[col]
                elif pd.api.types.is_numeric_dtype(df[col]):
                    strategy[col] = numeric_default
                else:
                    strategy[col] = categorical_default

            missing_output = str(output_dir / f"missing_{uuid.uuid4().hex[:8]}.csv")
            emit_trace(state, "TOOL_CALL", STEP, {
                "server": "preprocessing", "tool": "handle_missing",
                "message": f"Handling missing values for {len(null_cols)} columns...",
            })
            result = handle_missing(
                file_path=input_path,
                strategy=strategy,
                output_path=missing_output,
            )
            input_path = result.output_path
            changes.append(f"Missing values: {result.changes_summary}")

        # Encode categorical columns
        if input_path.endswith(".csv"):
            df = pd.read_csv(input_path, nrows=1000)
        else:
            df = pd.read_excel(input_path, nrows=1000, engine="openpyxl")

        cat_cols = list(df.select_dtypes(include=["object", "category"]).columns)
        cat_cols = [c for c in cat_cols if c != target_col]

        if cat_cols:
            default_cols = [c for c in cat_cols if c not in encoding_overrides]
            override_groups: dict[str, list[str]] = {}
            for col in cat_cols:
                if col in encoding_overrides:
                    method = encoding_overrides[col]
                    override_groups.setdefault(method, []).append(col)

            if default_cols:
                encode_output = str(output_dir / f"encoded_{uuid.uuid4().hex[:8]}.csv")
                emit_trace(state, "TOOL_CALL", STEP, {
                    "server": "preprocessing", "tool": "encode_categorical",
                    "message": f"Encoding {len(default_cols)} categorical columns ({encoding_method})...",
                })
                result = encode_categorical(
                    file_path=input_path,
                    columns=default_cols,
                    method=encoding_method,
                    output_path=encode_output,
                )
                input_path = result.output_path
                changes.append(f"Encoding ({encoding_method}): {result.changes_summary}")

            for method, cols in override_groups.items():
                encode_output = str(output_dir / f"encoded_{uuid.uuid4().hex[:8]}.csv")
                result = encode_categorical(
                    file_path=input_path,
                    columns=cols,
                    method=method,
                    output_path=encode_output,
                )
                input_path = result.output_path
                changes.append(f"Encoding ({method}): {result.changes_summary}")

        state["cleaned_df_path"] = input_path
        state["preprocessing_plan"] = {
            "status": "completed",
            "null_columns_handled": list(null_cols.keys()) if null_cols else [],
            "categorical_columns_encoded": cat_cols,
            "changes": changes,
        }

        emit_trace(state, "TOOL_RESULT", STEP, {
            "message": f"Preprocessing completed: {len(changes)} changes",
            "changes": changes,
        })

        # Update session doc
        try:
            from session_doc.server import upsert_structured
            sid = str(state.get("session_id", ""))
            summary_parts = []
            if null_cols:
                summary_parts.append(f"Handled missing in {len(null_cols)} column(s)")
            if cat_cols:
                summary_parts.append(f"Encoded {len(cat_cols)} categorical(s)")
            narrative = (
                ". ".join(summary_parts) + "." if summary_parts
                else "No preprocessing needed."
            )
            upsert_structured(sid, "Preprocessing Decisions", narrative, metadata={
                "null_columns_handled": list(null_cols.keys()) if null_cols else [],
                "categorical_columns_encoded": cat_cols,
                "numeric_strategy": numeric_default,
                "categorical_strategy": categorical_default,
                "encoding_method": encoding_method,
                "output_path": input_path,
            })
            emit_trace(state, "DOC_UPDATED", STEP, {
                "section": "Preprocessing Decisions",
                "message": "Updated session doc with preprocessing decisions",
            })
        except Exception as e:
            logger.warning("preprocessing_node: session_doc upsert failed", error=str(e))

    except Exception as e:
        logger.error("preprocessing_node: failed", error=str(e))
        state["error"] = str(e)

    clear_business_proposal(state)

    # Only mark DONE on success; FAILED on error
    if state.get("error"):
        mark_step_failed(state, STEP)
    else:
        mark_step_done(state, STEP)
        # Update session memory
        try:
            changes = state.get("preprocessing_plan", {}).get("changes", [])
            update_session_memory_md(state, STEP, (
                f"Changes applied: {len(changes)}\n"
                + "\n".join(f"- {c}" for c in changes[:5])
            ))
        except Exception:
            pass

    state["next_action"] = "orchestrator"
    return state
