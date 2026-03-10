"""Merge planning node — proposes merge strategy with proposal/approval loop.

For multi-file sessions, proposes a merge plan as a business-logic Proposal.
User can approve, request changes to join keys/types/order, or reject.
Single-file sessions skip merge automatically.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import structlog

# Ensure MCP servers and shared schemas are importable
_mcp_root = str(Path(__file__).resolve().parents[6] / "packages" / "mcp-servers" / "src")
if _mcp_root not in sys.path:
    sys.path.insert(0, _mcp_root)
_packages_root = str(Path(__file__).resolve().parents[6] / "packages")
if _packages_root not in sys.path:
    sys.path.insert(0, _packages_root)

from app.agent.nodes.approval_helpers import (
    check_proposal_phase,
    clear_business_proposal,
    get_proposal_feedback,
    increment_revision_count,
    mark_step_done,
    mark_step_failed,
    mark_step_skipped,
    set_business_proposal,
    should_revise,
)
from app.agent.nodes.node_helpers import emit_trace, read_step_context, update_session_memory_md
from app.agent.state import AgentState
from app.config import settings

logger = structlog.get_logger()

STEP = "merge_planning"


async def merge_planning_node(state: AgentState) -> AgentState:
    """Detect join keys between tables and propose/execute merges."""
    logger.info("merge_planning_node: executing", session_id=str(state.get("session_id")))
    state["current_step"] = STEP

    read_step_context(state, STEP)

    uploaded_files = state.get("uploaded_files", [])

    # Single file — nothing to merge
    if len(uploaded_files) <= 1:
        logger.info("merge_planning_node: single file, skipping merge")
        if uploaded_files:
            file_path = uploaded_files[0].get("storage_path") or uploaded_files[0].get(
                "file_path", ""
            )
            p = Path(file_path)
            if not p.is_absolute():
                p = Path(settings.upload_dir) / file_path
            state["merged_df_path"] = str(p)
        state["merge_plan"] = {"status": "skipped", "reason": "single_file"}

        # Write to session doc for single-file case
        try:
            from session_doc.server import upsert_structured
            sid = str(state.get("session_id", ""))
            upsert_structured(
                sid, "Merge Strategy",
                "Single file — no merge needed.",
                metadata={"status": "skipped", "reason": "single_file"},
            )
        except Exception as e:
            logger.warning("merge_planning_node: session_doc write failed", error=str(e))

        mark_step_done(state, STEP)
        return state

    # Check business proposal phase
    phase = check_proposal_phase(state, STEP)

    if phase == "propose":
        return await _propose_merge(state, uploaded_files)
    elif phase == "execute":
        return await _execute_merge(state, uploaded_files)
    elif phase == "revision_requested":
        if should_revise(state, STEP):
            increment_revision_count(state, STEP)
            return await _propose_merge(state, uploaded_files, revision=True)
        # Max revisions — use current proposal as-is
        return await _execute_merge(state, uploaded_files)
    elif phase == "rejected":
        emit_trace(state, "INFO", STEP, {
            "message": "Merge plan rejected; using first file only"
        })
        file_path = uploaded_files[0].get("storage_path") or uploaded_files[0].get(
            "file_path", ""
        )
        p = Path(file_path)
        if not p.is_absolute():
            p = Path(settings.upload_dir) / file_path
        state["merged_df_path"] = str(p)
        state["merge_plan"] = {"status": "skipped", "reason": "rejected"}
        clear_business_proposal(state)
        mark_step_skipped(state, STEP, "user_approved_no_merge")
        state["next_action"] = "orchestrator"
        return state
    else:
        # skip — still pending
        state["next_action"] = "wait"
        return state


async def _propose_merge(
    state: AgentState,
    uploaded_files: list[dict],
    revision: bool = False,
) -> AgentState:
    """Generate merge plan proposal via MCP tool + LLM."""
    feedback = ""
    if revision:
        feedback = get_proposal_feedback(state, STEP)

    try:
        from merge_planner.server import TableInput, detect_keys

        # Build table inputs
        table_inputs: list[TableInput] = []
        for file_info in uploaded_files:
            file_path = file_info.get("storage_path") or file_info.get("file_path", "")
            p = Path(file_path)
            if not p.is_absolute():
                p = Path(settings.upload_dir) / file_path
            table_inputs.append(
                TableInput(
                    file_path=str(p),
                    alias=file_info.get("filename", p.stem),
                )
            )

        # Detect join keys
        plans = detect_keys(table_inputs)

        if not plans:
            logger.warning("merge_planning_node: no merge keys detected")
            # Propose fallback — let user decide
            plan = {
                "merge_steps": [],
                "tables": [t.alias for t in table_inputs],
                "status": "no_keys_found",
                "fallback": "use_first_file",
            }
            summary = (
                f"No automatic join keys detected between "
                f"{len(table_inputs)} tables. Will use first file only."
            )
            return set_business_proposal(
                state, STEP, "merge_plan", plan, summary,
                "Could not find common columns for joining tables.",
            )

        best_plan = plans[0]

        # Build structured plan for proposal
        merge_steps = [{
            "left_table": best_plan.left_table,
            "right_table": best_plan.right_table,
            "left_key": best_plan.left_key,
            "right_key": best_plan.right_key,
            "join_type": best_plan.merge_type,
            "confidence": best_plan.confidence,
        }]

        alternatives = [
            {
                "left_table": p.left_table,
                "right_table": p.right_table,
                "left_key": p.left_key,
                "right_key": p.right_key,
                "join_type": p.merge_type,
                "confidence": p.confidence,
            }
            for p in plans[1:4]
        ]

        plan = {
            "merge_steps": merge_steps,
            "tables": [t.alias for t in table_inputs],
            "total_candidates": len(plans),
        }

        summary = (
            f"Merge {len(table_inputs)} tables using {best_plan.merge_type} join "
            f"on {best_plan.left_key} = {best_plan.right_key} "
            f"(confidence: {best_plan.confidence:.0%})"
        )
        if feedback:
            summary += " (revised based on feedback)"

        reasoning = (
            f"Selected {best_plan.merge_type} join based on key overlap analysis. "
            f"Confidence: {best_plan.confidence:.0%}. "
            f"{len(plans)} candidate plan(s) evaluated."
        )

        emit_trace(state, "AI_REASONING", STEP, {
            "message": summary,
            "merge_type": best_plan.merge_type,
            "confidence": best_plan.confidence,
            "total_plans": len(plans),
        })

        return set_business_proposal(
            state, STEP, "merge_plan", plan, summary, reasoning,
            alternatives=alternatives,
        )

    except Exception as e:
        logger.error("merge_planning_node: key detection failed", error=str(e))
        # Fallback proposal
        plan = {
            "merge_steps": [],
            "tables": [f.get("filename", "") for f in uploaded_files],
            "status": "detection_failed",
            "error": str(e),
            "fallback": "use_first_file",
        }
        return set_business_proposal(
            state, STEP, "merge_plan", plan,
            f"Merge key detection failed: {e}. Will use first file.",
            "Automatic key detection encountered an error.",
        )


async def _execute_merge(state: AgentState, uploaded_files: list[dict]) -> AgentState:
    """Execute the approved merge plan."""
    plan = state.get("pending_proposal_plan", {})
    merge_steps = plan.get("merge_steps", [])

    if not merge_steps:
        # No merge steps — use first file
        file_path = uploaded_files[0].get("storage_path") or uploaded_files[0].get(
            "file_path", ""
        )
        p = Path(file_path)
        if not p.is_absolute():
            p = Path(settings.upload_dir) / file_path
        state["merged_df_path"] = str(p)
        state["merge_plan"] = {"status": "skipped", "reason": "no_merge_steps"}
        clear_business_proposal(state)
        mark_step_done(state, STEP)
        state["next_action"] = "orchestrator"
        return state

    try:
        from merge_planner.server import MergePlan, TableInput, execute_merge

        # Build table inputs for path resolution
        table_inputs: list[TableInput] = []
        for file_info in uploaded_files:
            file_path = file_info.get("storage_path") or file_info.get("file_path", "")
            p = Path(file_path)
            if not p.is_absolute():
                p = Path(settings.upload_dir) / file_path
            table_inputs.append(
                TableInput(
                    file_path=str(p),
                    alias=file_info.get("filename", p.stem),
                )
            )
        alias_to_path = {t.alias: t.file_path for t in table_inputs}

        step_info = merge_steps[0]

        # Resolve paths
        left_table = alias_to_path.get(
            step_info["left_table"], step_info["left_table"]
        )
        right_table = alias_to_path.get(
            step_info["right_table"], step_info["right_table"]
        )

        best_plan = MergePlan(
            left_table=left_table,
            right_table=right_table,
            left_key=step_info["left_key"],
            right_key=step_info["right_key"],
            merge_type=step_info.get("join_type", "inner"),
            confidence=step_info.get("confidence", 0.5),
        )

        # Check for many-to-many join risk
        import pandas as pd

        left_df = (
            pd.read_csv(left_table, nrows=1000)
            if left_table.endswith(".csv")
            else pd.read_excel(left_table, nrows=1000)
        )
        right_df = (
            pd.read_csv(right_table, nrows=1000)
            if right_table.endswith(".csv")
            else pd.read_excel(right_table, nrows=1000)
        )

        left_dupes = (
            left_df[best_plan.left_key].duplicated().any()
            if best_plan.left_key in left_df.columns
            else False
        )
        right_dupes = (
            right_df[best_plan.right_key].duplicated().any()
            if best_plan.right_key in right_df.columns
            else False
        )

        if left_dupes and right_dupes:
            logger.warning(
                "merge_planning_node: many-to-many join detected",
                left_key=best_plan.left_key,
                right_key=best_plan.right_key,
            )

        # Execute merge — store in session-centric directory
        session_id = state.get("session_id", "")
        output_dir = Path(settings.upload_dir) / str(session_id) / "processed"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(output_dir / f"merged_{uuid.uuid4().hex[:8]}.csv")

        result = execute_merge(best_plan, output_path)

        if result.success:
            state["merged_df_path"] = result.output_path
            state["merge_plan"] = {
                "status": "merged",
                "left_key": best_plan.left_key,
                "right_key": best_plan.right_key,
                "merge_type": best_plan.merge_type,
                "confidence": best_plan.confidence,
                "output_rows": result.row_count,
                "output_columns": result.column_count,
                "dataset_path": result.output_path,
            }
            logger.info(
                "merge_planning_node: merge completed",
                rows=result.row_count,
                columns=result.column_count,
            )

            emit_trace(state, "TOOL_RESULT", STEP, {
                "message": (
                    f"Merge completed: {result.row_count} rows, "
                    f"{result.column_count} columns"
                ),
                "rows": result.row_count,
                "columns": result.column_count,
            })

            # Update session doc
            try:
                from session_doc.server import upsert_structured
                sid = str(state.get("session_id", ""))
                narrative = (
                    f"Merged on {best_plan.left_key} = {best_plan.right_key} "
                    f"({best_plan.merge_type}), confidence {best_plan.confidence:.0%}. "
                    f"Result: {result.row_count} rows, {result.column_count} columns."
                )
                upsert_structured(sid, "Merge Strategy", narrative, metadata={
                    "left_key": best_plan.left_key,
                    "right_key": best_plan.right_key,
                    "merge_type": best_plan.merge_type,
                    "confidence": best_plan.confidence,
                    "output_rows": result.row_count,
                    "output_columns": result.column_count,
                    "output_path": result.output_path,
                })
            except Exception as e:
                logger.warning(
                    "merge_planning_node: session_doc upsert failed", error=str(e)
                )
        else:
            logger.error("merge_planning_node: merge failed", errors=result.errors)
            state["merge_plan"] = {"status": "failed", "errors": result.errors}
            state["merged_df_path"] = table_inputs[0].file_path
            state["error"] = f"Merge failed: {'; '.join(result.errors)}"

    except Exception as e:
        logger.error("merge_planning_node: merge execution failed", error=str(e))
        state["error"] = str(e)
        # Fallback to first file
        if uploaded_files:
            file_path = uploaded_files[0].get("storage_path") or uploaded_files[0].get(
                "file_path", ""
            )
            p = Path(file_path)
            if not p.is_absolute():
                p = Path(settings.upload_dir) / file_path
            state["merged_df_path"] = str(p)

    clear_business_proposal(state)

    # Only mark DONE on success; mark FAILED if error occurred
    if state.get("error"):
        mark_step_failed(state, STEP)
    else:
        mark_step_done(state, STEP)

    state["next_action"] = "orchestrator"
    return state
