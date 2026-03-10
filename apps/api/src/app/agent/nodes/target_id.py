"""Target identification node — proposes target variable with proposal/approval loop.

Proposes a target column as a business-logic Proposal with alternatives and
reasoning. User can approve, request changes, or reject. If derivation code
is needed, that goes through the code approval gate after the business
proposal is approved.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import structlog

from app.agent.llm import invoke_llm
from app.agent.nodes.approval_helpers import (
    check_approval_phase,
    check_proposal_phase,
    clear_approval,
    clear_business_proposal,
    get_proposal_feedback,
    increment_denial_count,
    increment_revision_count,
    mark_step_done,
    mark_step_failed,
    revert_step_to_ready,
    set_business_proposal,
    set_proposal,
    should_repropose,
    should_revise,
)
from app.agent.nodes.node_helpers import (
    emit_trace,
    read_step_context,
    save_code_artifact,
    update_session_memory_md,
)
from app.agent.prompts import TARGET_SELECTION_PROMPT
from app.agent.state import AgentState
from app.config import settings

# Ensure MCP servers package is importable
_mcp_root = str(Path(__file__).resolve().parents[6] / "packages" / "mcp-servers" / "src")
if _mcp_root not in sys.path:
    sys.path.insert(0, _mcp_root)

logger = structlog.get_logger()

# Common target column names (ordered by priority)
_TARGET_NAMES = [
    "churn",
    "target",
    "label",
    "class",
    "outcome",
    "churned",
    "is_churn",
    "attrition",
    "default",
    "fraud",
    "spam",
]

# Binary-like value sets that suggest a target column
_BINARY_VALUES = {"yes", "no", "true", "false", "0", "1", "y", "n"}

STEP = "target_id"


def _identify_target_column(df: pd.DataFrame) -> str | None:
    """Heuristic to find the best target variable."""
    # 1. Look for common target column names
    for col in df.columns:
        if col.lower().strip() in _TARGET_NAMES:
            return col

    # 2. Look for binary columns with target-like values
    for col in df.columns:
        unique = df[col].nunique()
        if unique == 2 and df[col].dtype in ("object", "bool", "int64", "float64"):
            vals = {str(v).lower() for v in df[col].dropna().unique()}
            if vals & _BINARY_VALUES:
                return col

    return None


async def target_id_node(state: AgentState) -> AgentState:
    """Identify the target column with business proposal + optional code approval."""
    logger.info("target_id_node: executing", session_id=str(state.get("session_id")))
    state["current_step"] = STEP

    read_step_context(state, STEP)

    # --- Phase A: Check if we're in code approval for derivation code ---
    code_phase = check_approval_phase(state, STEP)
    if code_phase == "execute":
        return await _execute_derivation(state)
    elif code_phase == "denied":
        clear_approval(state)
        count = increment_denial_count(state, STEP)
        if should_repropose(state, STEP):
            logger.info("target_id_node: derivation code denied, re-proposing", count=count)
            # Re-propose derivation code with feedback
            state["error"] = None
            # Fall through to re-propose derivation
            plan = state.get("pending_proposal_plan", {})
            if plan.get("derivation_code"):
                code = plan["derivation_code"]
                desc = (
                    f"Derive target column '{plan.get('target_column', '')}' "
                    f"from existing data (revised after denial)."
                )
                set_proposal(state, STEP, code, desc)
                return state
        else:
            logger.info("target_id_node: max denials for derivation code")
            state["error"] = "Target derivation code was denied by user"
            clear_business_proposal(state)
            mark_step_failed(state, STEP)
            return state
    elif code_phase == "skip":
        # Code proposal pending — wait
        state["next_action"] = "wait"
        return state

    # --- Phase B: Business proposal for target selection ---
    phase = check_proposal_phase(state, STEP)

    if phase == "propose":
        return await _propose_target(state)
    elif phase == "execute":
        return await _execute_target(state)
    elif phase == "revision_requested":
        if should_revise(state, STEP):
            increment_revision_count(state, STEP)
            return await _propose_target(state, revision=True)
        # Max revisions — use current proposal as-is
        return await _execute_target(state)
    elif phase == "rejected":
        emit_trace(state, "INFO", STEP, {
            "message": "Target selection rejected by user — step reverted to READY"
        })
        state["error"] = None
        clear_business_proposal(state)
        revert_step_to_ready(state, STEP)
        state["next_action"] = "orchestrator"
        return state
    else:
        # skip — still pending
        state["next_action"] = "wait"
        return state


async def _propose_target(
    state: AgentState,
    revision: bool = False,
) -> AgentState:
    """Generate target selection proposal via heuristic + LLM."""
    feedback = ""
    if revision:
        feedback = get_proposal_feedback(state, STEP)

    # Determine which file to read
    df_path = state.get("merged_df_path", "")
    if not df_path:
        uploaded_files = state.get("uploaded_files", [])
        if uploaded_files:
            df_path = uploaded_files[0].get("storage_path") or uploaded_files[0].get(
                "file_path", ""
            )

    if not df_path:
        logger.error("target_id_node: no dataframe path available")
        state["error"] = "No dataframe path available for target identification"
        emit_trace(state, "ERROR", STEP, {
            "message": "No dataframe path available for target identification"
        })
        mark_step_failed(state, STEP)
        state["next_action"] = "orchestrator"
        return state

    try:
        p = Path(df_path)
        if not p.exists() and not p.is_absolute():
            p = Path(settings.upload_dir) / df_path
        if not p.exists():
            # Path may already include upload_dir prefix — try just the filename
            p = Path(settings.upload_dir) / Path(df_path).name
        df_path = str(p)

        if df_path.endswith(".csv"):
            df = pd.read_csv(df_path, nrows=100_000)
        else:
            df = pd.read_excel(df_path, nrows=100_000, engine="openpyxl")

        # Try heuristic first (unless revising based on feedback)
        target_col = None
        method = "heuristic"
        derivation_code = None
        reasoning = ""
        alternatives = []

        if not revision:
            target_col = _identify_target_column(df)
            if target_col:
                reasoning = (
                    f"Column '{target_col}' matched known target name pattern "
                    f"in priority list."
                )
                method = "existing"

        # LLM-based identification if heuristic failed or revising
        if target_col is None or revision:
            llm_result = await _llm_identify_target(state, df, feedback)
            if llm_result:
                target_col = llm_result["target_column"]
                method = "derived" if llm_result.get("derivation_code") else "existing"
                derivation_code = llm_result.get("derivation_code")
                reasoning = llm_result.get("reasoning", "LLM-based identification")
                alternatives = llm_result.get("alternatives", [])

        if not target_col:
            # Propose with empty target — user must decide
            plan = {
                "target_column": "",
                "method": "unknown",
                "derivation_code": None,
                "columns_available": list(df.columns[:50]),
                "total_columns": len(df.columns),
            }
            return set_business_proposal(
                state, STEP, "target_selection", plan,
                "Could not automatically identify a target variable. Please select one.",
                "Neither heuristic matching nor LLM analysis found a suitable target.",
            )

        # Build proposal plan
        plan = {
            "target_column": target_col,
            "method": method,
            "derivation_code": derivation_code,
            "column_exists": target_col in df.columns,
            "alternatives": alternatives,
        }

        # Add column stats if it exists
        if target_col in df.columns:
            plan["unique_values"] = int(df[target_col].nunique())
            plan["null_pct"] = float(df[target_col].isnull().mean() * 100)
            plan["dtype"] = str(df[target_col].dtype)
            if df[target_col].nunique() <= 10:
                plan["value_counts"] = df[target_col].value_counts().head(10).to_dict()

        summary = f"Target column: '{target_col}' ({method})"
        if derivation_code:
            summary += " — requires derivation code"
        if feedback:
            summary += " (revised based on feedback)"

        emit_trace(state, "AI_REASONING", STEP, {
            "message": summary,
            "target_column": target_col,
            "method": method,
            "requires_derivation": bool(derivation_code),
        })

        alt_proposals = [
            {"column": a.get("column", ""), "reasoning": a.get("reasoning", "")}
            for a in alternatives
            if isinstance(a, dict)
        ]

        return set_business_proposal(
            state, STEP, "target_selection", plan, summary, reasoning,
            alternatives=alt_proposals,
        )

    except Exception as e:
        logger.error("target_id_node: proposal generation failed", error=str(e))
        state["error"] = str(e)
        emit_trace(state, "ERROR", STEP, {
            "message": f"Target proposal generation failed: {e}"
        })
        state["next_action"] = "orchestrator"
        return state


async def _execute_target(state: AgentState) -> AgentState:
    """Apply the approved target selection."""
    plan = state.get("pending_proposal_plan", {})
    target_col = plan.get("target_column", "")

    if not target_col:
        state["error"] = "No target column in approved proposal"
        clear_business_proposal(state)
        mark_step_failed(state, STEP)
        state["next_action"] = "orchestrator"
        return state

    # If derivation code is needed, go through code approval
    derivation_code = plan.get("derivation_code")
    if derivation_code and not plan.get("column_exists", True):
        state["target_column"] = target_col
        desc = (
            f"Derive target column '{target_col}' from existing data.\n"
            f"This code will create the target variable needed for modeling."
        )
        set_proposal(state, STEP, derivation_code, desc)
        logger.info("target_id_node: derivation code needs approval", target=target_col)
        return state

    # Direct target — apply immediately
    state["target_column"] = target_col

    # Update session doc
    try:
        from session_doc.server import upsert_structured
        df_path = state.get("merged_df_path", "")
        filename = Path(df_path).name if df_path else "unknown"
        narrative = f"Target column: '{target_col}' (identified from {filename})."
        upsert_structured(
            str(state.get("session_id", "")), "Target Variable", narrative,
            metadata={"target_column": target_col, "method": "existing", "source_file": filename},
        )
    except Exception as e:
        logger.warning("target_id_node: session_doc upsert failed", error=str(e))

    emit_trace(state, "TOOL_RESULT", STEP, {
        "message": f"Target selection approved: '{target_col}'",
        "target_column": target_col,
    })

    # Update session memory markdown
    try:
        update_session_memory_md(state, STEP, (
            f"Selected: `{target_col}` (existing column)\n"
            f"Method: direct selection\n"
        ))
    except Exception as e:
        logger.warning("target_id_node: session memory update failed", error=str(e))

    clear_business_proposal(state)
    mark_step_done(state, STEP)
    state["next_action"] = "orchestrator"
    return state


async def _execute_derivation(state: AgentState) -> AgentState:
    """Execute approved derivation code in sandbox."""
    approved_code = state.get("approved_code", "")
    target_col = state.get("target_column", "")
    clear_approval(state)

    if not approved_code or not target_col:
        state["error"] = "Missing approved code or target column"
        clear_business_proposal(state)
        mark_step_failed(state, STEP)
        return state

    try:
        from sandbox_executor.server import ExecutionInput, run, validate_code

        validation = validate_code(approved_code)
        if not validation.valid:
            state["error"] = f"Unsafe derivation code: {'; '.join(validation.issues)}"
            clear_business_proposal(state)
            mark_step_failed(state, STEP)
            return state

        df_path = state.get("merged_df_path", "")
        if not df_path:
            uploaded_files = state.get("uploaded_files", [])
            if uploaded_files:
                df_path = uploaded_files[0].get("storage_path", "")

        p = Path(df_path)
        if not p.exists() and not p.is_absolute():
            p = Path(settings.upload_dir) / df_path

        output_path = str(p.parent / f"derived_{p.name}")

        sandbox_code = (
            f"import pandas as pd\n"
            f"df = pd.read_csv(r'{p}')\n"
            if p.suffix == ".csv"
            else f"import pandas as pd\n"
            f"df = pd.read_excel(r'{p}', engine='openpyxl')\n"
        )
        sandbox_code += approved_code + "\n"
        sandbox_code += f"df.to_csv(r'{output_path}', index=False)\n"

        result = run(ExecutionInput(
            code=sandbox_code,
            timeout=120,
            working_dir=str(p.parent),
        ))

        if result.exit_code != 0:
            state["error"] = (
                f"Derivation code failed (exit {result.exit_code}): {result.stderr}"
            )
            clear_business_proposal(state)
            mark_step_failed(state, STEP)
            return state

        state["merged_df_path"] = output_path
        logger.info("target_id_node: derivation code executed")

        # Save derivation code as artifact
        try:
            save_code_artifact(state, STEP, approved_code, f"Derive target '{target_col}'")
        except Exception as e:
            logger.warning("target_id_node: code artifact save failed", error=str(e))

        emit_trace(state, "TOOL_RESULT", STEP, {
            "message": f"Target derivation code executed: '{target_col}'",
            "output_path": output_path,
        })

    except Exception as e:
        logger.error("target_id_node: derivation failed", error=str(e))
        state["error"] = f"Derivation code failed: {e}"

    # Update session doc
    try:
        from session_doc.server import upsert_structured
        narrative = f"Target column: '{target_col}' (derived via approved code)."
        upsert_structured(
            str(state.get("session_id", "")), "Target Variable", narrative,
            metadata={"target_column": target_col, "method": "derived"},
        )
    except Exception as e:
        logger.warning("target_id_node: session_doc upsert failed", error=str(e))

    # Update session memory markdown
    try:
        update_session_memory_md(state, STEP, (
            f"Selected: `{target_col}` (derived via approved code)\n"
            f"Method: derivation code executed in sandbox\n"
        ))
    except Exception as e:
        logger.warning("target_id_node: session memory update failed", error=str(e))

    clear_business_proposal(state)
    mark_step_done(state, STEP)
    state["next_action"] = "orchestrator"
    return state


async def _llm_identify_target(
    state: AgentState, df: pd.DataFrame, feedback: str = ""
) -> dict | None:
    """Use LLM to identify target column."""
    try:
        company_name = state.get("company_name", "the company")
        industry = state.get("industry", "")
        business_context = state.get("business_context", "")

        # Build column profiles
        col_lines = []
        for col in df.columns:
            dtype = str(df[col].dtype)
            null_pct = df[col].isnull().mean() * 100
            nunique = df[col].nunique()
            sample_vals = df[col].dropna().head(3).tolist()
            col_lines.append(
                f"- {col} (dtype={dtype}, nulls={null_pct:.1f}%, "
                f"unique={nunique}, samples={sample_vals})"
            )
        col_profiles_str = "\n".join(col_lines)
        sample_df = df.head(5).to_string(index=False)

        # Get selected opportunity for context
        selected_opp = state.get("selected_opportunity", {})
        opp_str = json.dumps(selected_opp, default=str) if selected_opp else "None selected"

        prompt = TARGET_SELECTION_PROMPT.format(
            company_name=company_name,
            industry=industry,
            business_context=business_context,
            selected_opportunity=opp_str,
            column_profiles=col_profiles_str,
            sample_data=sample_df,
            feedback=feedback or "None",
        )

        response = await invoke_llm([
            {"role": "system", "content": prompt},
        ])

        cleaned = response.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]
            cleaned = cleaned.rsplit("```", 1)[0]

        parsed = json.loads(cleaned)
        target_column = parsed.get("target_column", "")

        if not target_column:
            return None

        derivation_code = parsed.get("derivation_code")
        if not derivation_code and target_column not in df.columns:
            logger.warning(
                "target_id_node: LLM suggested non-existent column without derivation",
                suggested=target_column,
            )
            return None

        return {
            "target_column": target_column,
            "derivation_code": derivation_code,
            "reasoning": parsed.get("reasoning", ""),
            "alternatives": parsed.get("alternatives", []),
        }

    except Exception as e:
        logger.warning("target_id_node: LLM identification failed", error=str(e))
        return None
