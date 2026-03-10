from __future__ import annotations

import sys
from pathlib import Path

import structlog

from app.agent.llm import invoke_llm_json
from app.agent.nodes.approval_helpers import (
    check_approval_phase,
    clear_approval,
    get_denial_feedback,
    increment_denial_count,
    mark_step_done,
    mark_step_failed,
    set_proposal,
    should_repropose,
)
from app.agent.nodes.node_helpers import build_context_payload, emit_trace, read_step_context
from app.agent.prompts import ADAPTIVE_REVISION_PROMPT
from app.agent.state import AgentState
from app.config import settings

logger = structlog.get_logger()

_mcp_root = str(Path(__file__).resolve().parents[6] / "packages" / "mcp-servers" / "src")
if _mcp_root not in sys.path:
    sys.path.insert(0, _mcp_root)

STEP = "explainability"

_DEFAULT_SHAP_CONFIG = {"sample_size": 500, "max_display": 20, "waterfall_count": 3}

SHAP_CONFIG_PROMPT = """\
You are an AI data scientist configuring SHAP explainability analysis.

## Model Details
- Best model: {model_name}
- Model type: {model_type}
- Feature count: {feature_count}
- Dataset rows: {row_count}
- Target column: {target_column}

## Previous Context
{session_doc_section}

## Strategy Hint
{strategy_hint}

## Instructions
Choose SHAP configuration parameters based on model complexity and dataset size.

Consider:
- Larger models (gradient boosting, random forest) need larger sample sizes for \
stable SHAP values
- Very wide datasets (many features) benefit from higher max_display
- More waterfall plots help when feature interactions are complex
- Balance compute cost vs. explanation quality

Respond with ONLY valid JSON:
{{"sample_size": <100-2000>, "max_display": <10-50>, "waterfall_count": <1-10>, \
"reasoning": "<why these parameters>"}}\
"""


def _build_explainability_code(
    state: AgentState, shap_config: dict | None = None,
) -> str:
    """Build a readable code description of the SHAP analysis."""
    model_results = state.get("model_results", {})
    models = model_results.get("models", [])
    best = next((m for m in models if m.get("best")), models[0] if models else {})
    target_col = state.get("target_column", "")
    config = shap_config or _DEFAULT_SHAP_CONFIG

    lines = [
        "# SHAP Explainability Analysis",
        f"# Best model: {best.get('model_name', 'N/A')}",
        f"# Target column: {target_col or 'N/A'}",
        f"# Sample size: {config['sample_size']}, Top features: {config['max_display']}",
        "",
        "from modeling_explain.server import shap_analysis",
        "",
        f"# Run SHAP analysis on the best model ({best.get('model_name', 'N/A')})",
        "# Generates:",
        f"#   - Summary plot (top {config['max_display']} features)",
        f"#   - {config['waterfall_count']} waterfall plots",
        "#   - Feature importance rankings",
        "",
        "shap_result = shap_analysis(",
        f"    model_path='{best.get('model_path', '<model_file>')}',",
        "    data_path=data_path,",
        f"    target_col='{target_col}',",
        "    output_dir='<session>/artifacts/shap/',",
        ")",
    ]
    return "\n".join(lines)


async def _get_shap_config_from_llm(
    state: AgentState, step_context: dict,
) -> dict:
    """Ask the LLM for SHAP configuration based on model complexity.

    Falls back to _DEFAULT_SHAP_CONFIG if the LLM call fails.
    """
    model_results = state.get("model_results", {})
    models = model_results.get("models", [])
    best = next((m for m in models if m.get("best")), models[0] if models else {})

    # Estimate feature count from column profiles or model results
    feature_count = len(state.get("selected_features", []))
    if not feature_count:
        feature_count = len(state.get("column_profiles", []))

    # Estimate row count from uploaded files
    files = state.get("uploaded_files", [])
    row_count = files[0].get("row_count", 0) if files else 0

    prompt = SHAP_CONFIG_PROMPT.format(
        model_name=best.get("model_name", "unknown"),
        model_type=best.get("model_name", "unknown"),
        feature_count=feature_count,
        row_count=row_count,
        target_column=state.get("target_column", ""),
        session_doc_section=step_context.get("session_doc_section", ""),
        strategy_hint=step_context.get("strategy_hint", ""),
    )

    try:
        result = await invoke_llm_json(
            [{"role": "user", "content": prompt}],
            schema_hint='{"sample_size": int, "max_display": int, '
                        '"waterfall_count": int, "reasoning": str}',
        )
        # Validate and clamp values
        config = {
            "sample_size": max(100, min(2000, int(result.get("sample_size", 500)))),
            "max_display": max(10, min(50, int(result.get("max_display", 20)))),
            "waterfall_count": max(1, min(10, int(result.get("waterfall_count", 3)))),
        }
        reasoning = result.get("reasoning", "")
        return {**config, "reasoning": reasoning}
    except Exception as e:
        logger.warning(
            "explainability_node: LLM config failed, using defaults", error=str(e),
        )
        return {**_DEFAULT_SHAP_CONFIG, "reasoning": "Defaults (LLM unavailable)"}


async def _get_revised_config_from_llm(
    state: AgentState, step_context: dict, current_config: dict,
) -> dict:
    """Use ADAPTIVE_REVISION_PROMPT to revise SHAP config after denial."""
    denial_feedback = step_context.get("denial_feedback", [])
    denial_count = step_context.get("denial_count", 0)

    prompt = ADAPTIVE_REVISION_PROMPT.format(
        original_plan=str(current_config),
        step=STEP,
        denial_feedback="\n".join(denial_feedback) if denial_feedback else "No specific feedback",
        denial_count=denial_count,
        max_denials=3,
        context=step_context.get("session_doc_section", ""),
    )

    try:
        result = await invoke_llm_json(
            [{"role": "user", "content": prompt}],
            schema_hint='{"revised_plan": {"sample_size": int, "max_display": int, '
                        '"waterfall_count": int}, "explanation": str, '
                        '"addresses_feedback": str}',
        )
        revised = result.get("revised_plan", {})
        config = {
            "sample_size": max(100, min(2000, int(revised.get("sample_size", 500)))),
            "max_display": max(10, min(50, int(revised.get("max_display", 20)))),
            "waterfall_count": max(1, min(10, int(revised.get("waterfall_count", 3)))),
        }
        explanation = result.get("explanation", "")
        return {**config, "explanation": explanation}
    except Exception as e:
        logger.warning(
            "explainability_node: LLM revision failed, using defaults", error=str(e),
        )
        return {**_DEFAULT_SHAP_CONFIG, "explanation": "Defaults (LLM revision unavailable)"}


async def explainability_node(state: AgentState) -> AgentState:
    """Generate SHAP explanations for the best trained model."""
    logger.info("explainability_node: executing", session_id=str(state.get("session_id")))
    state["current_step"] = STEP

    # ── Read step context before planning ──
    step_context = read_step_context(state, STEP)

    emit_trace(state, "AI_REASONING", STEP, {
        "message": "Reading step context for explainability planning",
        "strategy_hint": step_context.get("strategy_hint", ""),
        "denial_count": step_context.get("denial_count", 0),
    })

    phase = check_approval_phase(state, STEP)

    if phase == "propose":
        # ── LLM decides SHAP config based on model complexity ──
        shap_config = await _get_shap_config_from_llm(state, step_context)

        emit_trace(state, "AI_REASONING", STEP, {
            "message": "LLM selected SHAP configuration based on model complexity",
            "config": {
                "sample_size": shap_config["sample_size"],
                "max_display": shap_config["max_display"],
                "waterfall_count": shap_config["waterfall_count"],
            },
            "reasoning": shap_config.get("reasoning", ""),
        })

        # Store config in node_plans for later execution
        node_plans = dict(state.get("node_plans", {}))
        node_plans[STEP] = shap_config
        state["node_plans"] = node_plans

        code = _build_explainability_code(state, shap_config=shap_config)
        desc = (
            f"Run SHAP analysis on best model: "
            f"{shap_config['sample_size']} samples, "
            f"top {shap_config['max_display']} features, "
            f"{shap_config['waterfall_count']} waterfall plots"
        )
        context_payload = build_context_payload(
            state, STEP,
            ai_explanation=shap_config.get("reasoning", ""),
        )
        set_proposal(state, STEP, code, desc, context=context_payload)
        logger.info("explainability_node: proposed code for approval")
        return state

    if phase == "denied":
        clear_approval(state)
        count = increment_denial_count(state, STEP)
        if should_repropose(state, STEP):
            # ── Use ADAPTIVE_REVISION_PROMPT with user feedback ──
            current_config = state.get("node_plans", {}).get(STEP, _DEFAULT_SHAP_CONFIG)
            revised = await _get_revised_config_from_llm(state, step_context, current_config)

            emit_trace(state, "AI_REASONING", STEP, {
                "message": f"Revision {count + 1}: LLM revised SHAP config after denial",
                "revised_config": {
                    "sample_size": revised["sample_size"],
                    "max_display": revised["max_display"],
                    "waterfall_count": revised["waterfall_count"],
                },
                "explanation": revised.get("explanation", ""),
                "user_feedback": get_denial_feedback(state, STEP),
            })

            # Update stored plan
            node_plans = dict(state.get("node_plans", {}))
            node_plans[STEP] = revised
            state["node_plans"] = node_plans

            logger.info(
                "explainability_node: code denied, re-proposing with LLM-revised config",
                denial_count=count,
                sample_size=revised["sample_size"],
            )
            code = _build_explainability_code(state, shap_config=revised)
            desc = (
                f"[Revision {count + 1}] SHAP analysis: {revised['sample_size']} samples, "
                f"top {revised['max_display']} features, "
                f"{revised['waterfall_count']} waterfall plots"
            )
            context_payload = build_context_payload(
                state, STEP,
                ai_explanation=revised.get("explanation", ""),
            )
            set_proposal(state, STEP, code, desc, context=context_payload)
            return state
        logger.info("explainability_node: max denials reached, marking FAILED")
        mark_step_failed(state, STEP)
        return state

    if phase == "skip":
        state["next_action"] = "wait"
        return state

    # ── phase == "execute" — run the actual SHAP analysis ──
    clear_approval(state)

    try:
        from modeling_explain.server import shap_analysis

        session_id = state.get("session_id")
        model_results = state.get("model_results", {})
        files = state.get("uploaded_files", [])
        target_col = state.get("target_column", "")

        models = model_results.get("models", [])
        if not models:
            state["error"] = "No model results available for explainability"
            return state

        # Find the best model
        best = next((m for m in models if m.get("best")), models[0])
        model_path = best.get("model_path")

        if not model_path or not Path(model_path).exists():
            state["error"] = f"Best model file not found: {model_path}"
            return state

        # Get data path
        data_path = (
            state.get("features_df_path")
            or state.get("cleaned_df_path")
            or state.get("merged_df_path")
        )
        if not data_path:
            primary = files[0] if files else {}
            data_path = primary.get("storage_path", "")
            if not Path(data_path).exists():
                data_path = str(Path(settings.upload_dir) / data_path)

        if not data_path or not Path(data_path).exists():
            state["error"] = f"Data file not found for SHAP: {data_path}"
            return state

        output_dir = str(
            Path(settings.upload_dir) / str(session_id) / "artifacts" / "shap"
        )
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        emit_trace(state, "TOOL_CALL", STEP, {
            "tool": "modeling_explain.shap_analysis",
            "args": {
                "model": best.get("model_name"),
                "target": target_col,
                "output_dir": output_dir,
            },
        })

        shap_result = shap_analysis(
            model_path=model_path,
            data_path=data_path,
            target_col=target_col,
            output_dir=output_dir,
        )

        state["explainability_results"] = {
            "model_name": best.get("model_name"),
            "summary_plot_path": shap_result.summary_plot_path,
            "feature_importance": shap_result.feature_importance,
            "waterfall_plots": shap_result.waterfall_plots,
        }

        emit_trace(state, "TOOL_RESULT", STEP, {
            "tool": "modeling_explain.shap_analysis",
            "success": True,
            "top_features": len(shap_result.feature_importance),
            "waterfall_count": len(shap_result.waterfall_plots),
        })

        logger.info(
            "explainability_node: completed",
            session_id=str(session_id),
            model=best.get("model_name"),
            top_features=len(shap_result.feature_importance),
        )

        # Store explainability code in code_registry
        try:
            from code_registry.server import store
            shap_config = state.get("node_plans", {}).get(STEP, _DEFAULT_SHAP_CONFIG)
            store(
                session_id=str(state.get("session_id", "")),
                step="explainability",
                code=_build_explainability_code(state, shap_config=shap_config),
                description=f"SHAP analysis on {best.get('model_name', 'N/A')}",
            )
        except Exception as e:
            logger.warning("explainability_node: code_registry store failed", error=str(e))

        # Update session doc
        try:
            from session_doc.server import upsert_structured
            sid = str(state.get("session_id", ""))
            top_feats = [
                f["feature"] for f in shap_result.feature_importance[:5]
            ]
            narrative = (
                f"SHAP analysis on {best.get('model_name', 'N/A')}. "
                f"Top features: {', '.join(top_feats)}. "
                f"{len(shap_result.feature_importance)} features ranked."
            )
            upsert_structured(sid, "Explainability", narrative, metadata={
                "model_name": best.get("model_name"),
                "feature_importance": [
                    {"feature": f["feature"], "importance": f.get("importance")}
                    for f in shap_result.feature_importance[:20]
                ],
                "summary_plot_path": shap_result.summary_plot_path,
                "waterfall_plots": shap_result.waterfall_plots,
            })
        except Exception as e:
            logger.warning("explainability_node: session_doc upsert failed", error=str(e))

    except Exception as e:
        logger.error("explainability_node: failed", error=str(e))
        state["error"] = str(e)

    mark_step_done(state, STEP)
    return state
