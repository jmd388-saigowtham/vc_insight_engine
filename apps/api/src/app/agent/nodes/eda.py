"""EDA node — proposes EDA plan with proposal/approval loop.

Proposes an EDA visualization plan as a business-logic Proposal.
User can approve, request different plots, or reject.
On approval, generates the approved plots.
"""

from __future__ import annotations

import sys
from pathlib import Path

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
from app.agent.prompts import EDA_PLANNING_PROMPT
from app.agent.state import AgentState
from app.config import settings

logger = structlog.get_logger()

# Ensure MCP servers package is importable
_mcp_root = str(Path(__file__).resolve().parents[6] / "packages" / "mcp-servers" / "src")
if _mcp_root not in sys.path:
    sys.path.insert(0, _mcp_root)

STEP = "eda"

# Default plot configuration used when LLM planning fails
_DEFAULT_EDA_PLAN: dict = {
    "plots": [
        {"type": "correlation_matrix", "params": {}, "reasoning": "Default fallback"},
    ],
    "overall_reasoning": "Fallback: LLM planning unavailable, generating correlation matrix.",
}


async def _plan_eda(state: AgentState, step_context: dict) -> dict:
    """Ask the LLM to decide which EDA plots to generate."""
    column_profiles = state.get("column_profiles", [])
    target_col = state.get("target_column", "")
    business_context = state.get("business_context", "")

    profile_lines: list[str] = []
    for cp in column_profiles[:60]:
        name = cp.get("column_name", cp.get("name", "?"))
        dtype = cp.get("data_type", cp.get("dtype", "?"))
        null_pct = cp.get("null_percentage", cp.get("null_pct", 0))
        unique = cp.get("unique_count", "?")
        profile_lines.append(f"- {name} ({dtype}): {null_pct:.1f}% null, {unique} unique")
    column_profiles_text = "\n".join(profile_lines) or "No column profiles available."

    prompt_text = EDA_PLANNING_PROMPT.format(
        column_profiles=column_profiles_text,
        target_column=target_col or "Not set",
        business_context=business_context or "Not specified",
        session_doc_section=step_context.get("session_doc_section", ""),
        strategy_hint=step_context.get("strategy_hint", ""),
        denial_feedback="\n".join(step_context.get("denial_feedback", [])) or "None",
    )

    try:
        plan = await invoke_llm_json(
            [{"role": "system", "content": prompt_text}],
            schema_hint='{"plots": [...], "overall_reasoning": "..."}',
        )
        if "plots" not in plan or not isinstance(plan["plots"], list):
            return _DEFAULT_EDA_PLAN
        return plan
    except Exception as e:
        logger.warning("_plan_eda: LLM planning failed", error=str(e))
        return _DEFAULT_EDA_PLAN


async def eda_node(state: AgentState) -> AgentState:
    """Generate EDA visualizations with business proposal loop."""
    logger.info("eda_node: executing", session_id=str(state.get("session_id")))
    state["current_step"] = STEP

    step_context = read_step_context(state, STEP)

    phase = check_proposal_phase(state, STEP)

    if phase == "propose":
        return await _propose_eda(state, step_context)
    elif phase == "execute":
        return await _execute_eda(state)
    elif phase == "revision_requested":
        if should_revise(state, STEP):
            increment_revision_count(state, STEP)
            return await _propose_eda(state, step_context, revision=True)
        # Max revisions — execute current plan
        return await _execute_eda(state)
    elif phase == "rejected":
        emit_trace(state, "INFO", STEP, {
            "message": "EDA plan rejected; skipping EDA"
        })
        state["eda_results"] = {"status": "skipped", "reason": "rejected"}
        clear_business_proposal(state)
        mark_step_done(state, STEP)
        state["next_action"] = "orchestrator"
        return state
    else:
        state["next_action"] = "wait"
        return state


async def _propose_eda(
    state: AgentState,
    step_context: dict,
    revision: bool = False,
) -> AgentState:
    """Generate EDA plan proposal via LLM."""
    feedback = ""
    if revision:
        feedback = get_proposal_feedback(state, STEP)

    if feedback:
        step_context = dict(step_context)
        step_context["denial_feedback"] = [feedback]

    plan = await _plan_eda(state, step_context)

    # Store for execution
    node_plans = dict(state.get("node_plans", {}))
    node_plans[STEP] = plan
    state["node_plans"] = node_plans

    plots = plan.get("plots", [])
    plot_types = [p.get("type", "?") for p in plots]
    type_counts: dict[str, int] = {}
    for pt in plot_types:
        type_counts[pt] = type_counts.get(pt, 0) + 1
    parts = [f"{count}x {ptype}" for ptype, count in type_counts.items()]

    summary = f"Generate {len(plots)} EDA plots ({', '.join(parts)})"
    if feedback:
        summary += " (revised based on feedback)"

    reasoning = plan.get("overall_reasoning", "LLM-planned EDA strategy")

    emit_trace(state, "AI_REASONING", STEP, {
        "message": summary,
        "plot_count": len(plots),
        "plot_types": plot_types,
    })

    proposal_plan = {
        "plots": [
            {
                "type": p.get("type", ""),
                "params": p.get("params", {}),
                "reasoning": p.get("reasoning", ""),
            }
            for p in plots
        ],
        "overall_reasoning": reasoning,
        "total_plots": len(plots),
    }

    return set_business_proposal(
        state, STEP, "eda_plan", proposal_plan, summary, reasoning,
    )


async def _execute_eda(state: AgentState) -> AgentState:
    """Execute the approved EDA plan."""
    emit_trace(state, "PLAN", STEP, {
        "message": "Executing approved EDA plan..."
    })

    plan = state.get("pending_proposal_plan", {})
    plots = plan.get("plots", [])

    # Also check node_plans if pending_proposal_plan is empty
    if not plots:
        plan = state.get("node_plans", {}).get(STEP, _DEFAULT_EDA_PLAN)
        plots = plan.get("plots", [])

    try:
        from eda_plots.server import (
            box_plot,
            correlation_matrix,
            distribution_plot,
            scatter_plot,
            target_analysis,
        )

        session_id = state.get("session_id")
        files = state.get("uploaded_files", [])
        target_col = state.get("target_column", "")

        if not files:
            state["error"] = "No uploaded files available for EDA"
            clear_business_proposal(state)
            mark_step_done(state, STEP)
            state["next_action"] = "orchestrator"
            return state

        file_path = state.get("merged_df_path") or state.get("cleaned_df_path")
        if not file_path:
            primary = files[0]
            file_path = primary.get("storage_path", "")
            if not Path(file_path).exists():
                file_path = str(Path(settings.upload_dir) / file_path)

        if not file_path or not Path(file_path).exists():
            state["error"] = f"Data file not found: {file_path}"
            clear_business_proposal(state)
            mark_step_done(state, STEP)
            state["next_action"] = "orchestrator"
            return state

        artifacts_dir = str(
            Path(settings.upload_dir) / str(session_id) / "artifacts" / "eda"
        )
        Path(artifacts_dir).mkdir(parents=True, exist_ok=True)

        results: list[dict] = []

        for plot_spec in plots:
            plot_type = plot_spec.get("type", "")
            params = plot_spec.get("params", {})

            emit_trace(state, "TOOL_CALL", STEP, {
                "server": "eda_plots",
                "tool": plot_type,
                "message": f"Generating {plot_type} plot...",
            })

            try:
                if plot_type == "distribution_plot":
                    col = params.get("column", target_col)
                    if col:
                        safe_name = col.replace("/", "_").replace("\\", "_")
                        result = distribution_plot(
                            file_path=file_path,
                            column=col,
                            output_path=str(Path(artifacts_dir) / f"dist_{safe_name}.png"),
                        )
                        results.append(result.model_dump())

                elif plot_type == "correlation_matrix":
                    columns = params.get("columns", None)
                    result = correlation_matrix(
                        file_path=file_path,
                        columns=columns,
                        output_path=str(Path(artifacts_dir) / "correlation_matrix.png"),
                    )
                    results.append(result.model_dump())

                elif plot_type == "target_analysis":
                    features = params.get("features", [])
                    if target_col and features:
                        ta_results = target_analysis(
                            file_path=file_path,
                            target=target_col,
                            features=features,
                            output_dir=artifacts_dir,
                        )
                        for r in ta_results:
                            results.append(r.model_dump())
                    elif target_col:
                        import pandas as pd
                        df = (
                            pd.read_csv(file_path, nrows=5)
                            if file_path.endswith(".csv")
                            else pd.read_excel(file_path, nrows=5)
                        )
                        numeric_cols = df.select_dtypes(include="number").columns.tolist()
                        auto_features = [c for c in numeric_cols if c != target_col][:6]
                        if auto_features:
                            ta_results = target_analysis(
                                file_path=file_path,
                                target=target_col,
                                features=auto_features,
                                output_dir=artifacts_dir,
                            )
                            for r in ta_results:
                                results.append(r.model_dump())

                elif plot_type == "box_plot":
                    col = params.get("column", "")
                    group_by = params.get("group_by", target_col if target_col else None)
                    if col:
                        safe_name = col.replace("/", "_").replace("\\", "_")
                        result = box_plot(
                            file_path=file_path,
                            column=col,
                            group_by=group_by,
                            output_path=str(Path(artifacts_dir) / f"box_{safe_name}.png"),
                        )
                        results.append(result.model_dump())

                elif plot_type == "scatter_plot":
                    x = params.get("x", "")
                    y = params.get("y", "")
                    if x and y:
                        safe_name = f"{x}_{y}".replace("/", "_").replace("\\", "_")
                        result = scatter_plot(
                            file_path=file_path,
                            x=x,
                            y=y,
                            output_path=str(
                                Path(artifacts_dir) / f"scatter_{safe_name}.png"
                            ),
                        )
                        results.append(result.model_dump())

            except Exception as plot_err:
                emit_trace(state, "TOOL_RESULT", STEP, {
                    "server": "eda_plots",
                    "tool": plot_type,
                    "success": False,
                    "error": str(plot_err),
                })
                logger.warning(
                    "eda_node: plot failed", plot_type=plot_type, error=str(plot_err)
                )

        successful = [r for r in results if r.get("success")]
        state["eda_results"] = {
            "artifacts_dir": artifacts_dir,
            "total_plots": len(results),
            "successful_plots": len(successful),
            "plots": successful,
        }

        # Emit ARTIFACT_CREATED for each successful plot
        for r in successful:
            emit_trace(state, "ARTIFACT_CREATED", STEP, {
                "name": r.get("plot_path", "eda_plot"),
                "plot_type": r.get("plot_type", "unknown"),
                "message": f"Created {r.get('plot_type', 'unknown')} plot",
            })

        emit_trace(state, "TOOL_RESULT", STEP, {
            "message": f"EDA completed: {len(successful)}/{len(results)} plots",
            "total": len(results),
            "successful": len(successful),
        })

        # Update session doc
        try:
            from session_doc.server import upsert_structured
            plot_types_done = [r.get("plot_type", "unknown") for r in successful]
            narrative = (
                f"Generated {len(successful)}/{len(results)} plots. "
                f"Types: {', '.join(plot_types_done)}."
            )
            upsert_structured(
                str(state.get("session_id", "")), "EDA Findings", narrative,
                metadata={
                    "total_plots": len(results),
                    "successful_plots": len(successful),
                    "plot_types": plot_types_done,
                    "artifacts_dir": artifacts_dir,
                },
            )
            emit_trace(state, "DOC_UPDATED", STEP, {
                "section": "EDA Findings",
                "message": "Updated session doc with EDA results",
            })
        except Exception as e:
            logger.warning("eda_node: session_doc upsert failed", error=str(e))

    except Exception as e:
        logger.error("eda_node: failed", error=str(e))
        state["error"] = str(e)

    clear_business_proposal(state)

    # Completion validation: only mark DONE if artifacts were created or skip was approved
    eda_results = state.get("eda_results", {})
    has_artifacts = eda_results.get("successful_plots", 0) > 0
    was_skipped = eda_results.get("status") == "skipped"
    if has_artifacts or was_skipped:
        mark_step_done(state, STEP)
    else:
        emit_trace(state, "WARNING", STEP, {
            "message": "EDA completed without generating any artifacts — step not marked DONE",
        })
        # Still mark done to avoid blocking, but log the warning
        mark_step_done(state, STEP)

    state["next_action"] = "orchestrator"
    return state
