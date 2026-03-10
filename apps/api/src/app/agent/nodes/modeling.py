"""Modeling node — proposes model selection with proposal/approval loop.

Proposes model families, tuning strategy, and split strategy as a
business-logic Proposal. User can approve, request different models, or reject.
On approval, trains approved models.
"""

from __future__ import annotations

import sys
import uuid as _uuid_mod
from pathlib import Path
from typing import Any

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
from app.agent.nodes.node_helpers import emit_trace, react_execute, read_step_context, update_session_memory_md
from app.agent.prompts import MODEL_SELECTION_PROMPT
from app.agent.state import AgentState
from app.config import settings

logger = structlog.get_logger()

_mcp_root = str(Path(__file__).resolve().parents[6] / "packages" / "mcp-servers" / "src")
if _mcp_root not in sys.path:
    sys.path.insert(0, _mcp_root)

STEP = "modeling"

_DEFAULT_MODELS = ["logistic_regression", "random_forest", "gradient_boosting"]


def _gather_data_characteristics(state: AgentState) -> dict[str, Any]:
    """Collect data characteristics from state for LLM model selection."""
    profiles = state.get("column_profiles", [])
    target_col = state.get("target_column", "")

    row_count = 0
    feature_count = 0
    numeric_count = 0
    categorical_count = 0
    has_high_cardinality = False

    for prof in profiles:
        col_name = prof.get("column_name", "")
        if col_name == target_col:
            continue
        feature_count += 1
        dtype = prof.get("data_type", "")
        if dtype in ("int64", "float64", "number"):
            numeric_count += 1
        else:
            categorical_count += 1
            unique = prof.get("unique_count", 0)
            if unique and unique > 20:
                has_high_cardinality = True

    for prof in profiles:
        rc = prof.get("row_count", 0)
        if rc:
            row_count = rc
            break

    class_balance = "unknown"
    for prof in profiles:
        if prof.get("column_name", "") == target_col:
            unique = prof.get("unique_count", 0)
            if unique == 2:
                sample = prof.get("sample_values", [])
                if sample:
                    zeros = sum(
                        1 for v in sample
                        if str(v) in ("0", "False", "false", "no", "No")
                    )
                    ones = len(sample) - zeros
                    if len(sample) > 0:
                        minority_ratio = min(zeros, ones) / len(sample)
                        class_balance = f"{minority_ratio:.1%} minority class"
            break

    return {
        "row_count": row_count,
        "feature_count": feature_count,
        "class_balance": class_balance,
        "feature_types": f"{numeric_count} numeric, {categorical_count} categorical",
        "has_high_cardinality": has_high_cardinality,
    }


async def _select_models_via_llm(
    state: AgentState,
    step_context: dict[str, Any],
) -> dict[str, Any]:
    """Ask the LLM to select model types based on data characteristics."""
    data_chars = _gather_data_characteristics(state)

    prompt_vars = {
        "row_count": data_chars["row_count"],
        "feature_count": data_chars["feature_count"],
        "target_column": state.get("target_column", ""),
        "class_balance": data_chars["class_balance"],
        "feature_types": data_chars["feature_types"],
        "has_high_cardinality": data_chars["has_high_cardinality"],
        "company_name": state.get("company_name", ""),
        "industry": state.get("industry", ""),
        "business_context": state.get("business_context", ""),
        "session_doc_section": step_context.get("session_doc_section", ""),
        "strategy_hint": step_context.get("strategy_hint", ""),
        "denial_feedback": "\n".join(step_context.get("denial_feedback", [])) or "None",
    }

    try:
        result = await invoke_llm_json(
            [
                {"role": "system", "content": MODEL_SELECTION_PROMPT.format(**prompt_vars)},
                {"role": "user", "content": "Select the best models."},
            ],
            schema_hint='{"model_types": [...], "reasoning": "...", '
                        '"tune_hyperparams": true, "split_strategy": "auto"}',
        )

        valid_types = {
            "logistic_regression", "random_forest", "gradient_boosting",
            "svm", "extra_trees", "knn",
        }
        model_types = [m for m in result.get("model_types", []) if m in valid_types]
        if not model_types:
            model_types = list(_DEFAULT_MODELS)

        return {
            "model_types": model_types,
            "reasoning": result.get("reasoning", ""),
            "tune_hyperparams": result.get("tune_hyperparams", True),
            "split_strategy": result.get("split_strategy", "auto"),
        }
    except Exception as e:
        logger.warning("modeling_node: LLM selection failed", error=str(e))
        return {
            "model_types": list(_DEFAULT_MODELS),
            "reasoning": "Fallback: LLM failed; using standard ensemble.",
            "tune_hyperparams": True,
            "split_strategy": "auto",
        }


async def modeling_node(state: AgentState) -> AgentState:
    """Train ML models with business proposal loop for model selection."""
    logger.info("modeling_node: executing", session_id=str(state.get("session_id")))
    state["current_step"] = STEP

    step_context = read_step_context(state, STEP)

    phase = check_proposal_phase(state, STEP)

    if phase == "propose":
        return await _propose_modeling(state, step_context)
    elif phase == "execute":
        return await _execute_modeling(state)
    elif phase == "revision_requested":
        if should_revise(state, STEP):
            increment_revision_count(state, STEP)
            return await _propose_modeling(state, step_context, revision=True)
        return await _execute_modeling(state)
    elif phase == "rejected":
        emit_trace(state, "INFO", STEP, {
            "message": "Model selection rejected; skipping modeling"
        })
        state["model_results"] = {"status": "skipped", "reason": "rejected"}
        clear_business_proposal(state)
        mark_step_done(state, STEP)
        state["next_action"] = "orchestrator"
        return state
    else:
        state["next_action"] = "wait"
        return state


async def _propose_modeling(
    state: AgentState,
    step_context: dict,
    revision: bool = False,
) -> AgentState:
    """Generate model selection proposal via LLM."""
    feedback = ""
    if revision:
        feedback = get_proposal_feedback(state, STEP)

    if feedback:
        step_context = dict(step_context)
        step_context["denial_feedback"] = [feedback]

    selection = await _select_models_via_llm(state, step_context)
    model_types = selection["model_types"]
    reasoning = selection["reasoning"]

    # Store for execution
    node_plans = dict(state.get("node_plans", {}))
    node_plans[STEP] = selection
    state["node_plans"] = node_plans

    data_chars = _gather_data_characteristics(state)

    plan = {
        "model_types": model_types,
        "tune_hyperparams": selection["tune_hyperparams"],
        "split_strategy": selection["split_strategy"],
        "data_characteristics": data_chars,
        "reasoning": reasoning,
    }

    summary = (
        f"Train {', '.join(model_types)} with "
        f"{'hyperparameter tuning' if selection['tune_hyperparams'] else 'defaults'}"
    )
    if feedback:
        summary += " (revised based on feedback)"

    emit_trace(state, "MODEL_SELECTION", STEP, {
        "model_types": model_types,
        "reasoning": reasoning,
        "data_characteristics": data_chars,
    })

    return set_business_proposal(
        state, STEP, "model_selection", plan, summary, reasoning,
    )


async def _execute_modeling(state: AgentState) -> AgentState:
    """Execute the approved model training."""
    emit_trace(state, "PLAN", STEP, {
        "message": "Executing approved model training plan..."
    })

    plan = state.get("pending_proposal_plan", {})
    model_types = plan.get("model_types", [])
    if not model_types:
        stored_plan = state.get("node_plans", {}).get(STEP, {})
        model_types = stored_plan.get("model_types", list(_DEFAULT_MODELS))

    try:
        from modeling_explain.server import detect_leakage, train

        session_id = state.get("session_id")
        files = state.get("uploaded_files", [])
        target_col = state.get("target_column", "")

        if not files or not target_col:
            state["error"] = "Missing files or target column for modeling"
            clear_business_proposal(state)
            mark_step_done(state, STEP)
            state["next_action"] = "orchestrator"
            return state

        file_path = (
            state.get("features_df_path")
            or state.get("cleaned_df_path")
            or state.get("merged_df_path")
        )
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

        # Leakage detection
        emit_trace(state, "TOOL_CALL", STEP, {
            "server": "modeling_explain", "tool": "detect_leakage",
            "message": "Checking for target leakage...",
        })
        try:
            leaky = detect_leakage(file_path, target_col)
            if leaky:
                leaky_names = [item["feature"] for item in leaky]
                logger.warning("modeling_node: leakage detected", features=leaky_names)
                emit_trace(state, "AI_REASONING", STEP, {
                    "message": f"Potential leakage in: {', '.join(leaky_names)}",
                    "leaky_features": leaky_names,
                })
        except Exception as e:
            logger.warning("modeling_node: leakage detection failed", error=str(e))

        output_dir = str(Path(settings.upload_dir) / str(session_id) / "models")
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        selected_features = state.get("selected_features") or None

        emit_trace(state, "TOOL_CALL", STEP, {
            "server": "modeling_explain", "tool": "train",
            "message": f"Training {len(model_types)} models: {', '.join(model_types)}...",
        })

        results = train(
            data_path=file_path,
            target_col=target_col,
            model_types=model_types,
            output_dir=output_dir,
            selected_features=selected_features,
        )

        result_dicts = [r.model_dump() for r in results]
        best = next((r for r in result_dicts if r.get("best")), None)

        state["model_results"] = {
            "models": result_dicts,
            "best_model": best.get("model_name") if best else None,
            "output_dir": output_dir,
        }

        emit_trace(state, "TOOL_RESULT", STEP, {
            "message": (
                f"Trained {len(result_dicts)} models. "
                f"Best: {best.get('model_name', 'N/A') if best else 'N/A'}"
            ),
            "models_trained": len(result_dicts),
            "best_model": best.get("model_name") if best else None,
        })

        # Register models & log experiments
        try:
            from app.database import async_session as _async_session
            from app.services.experiment_tracker import ExperimentTracker
            from app.services.model_registry import ModelRegistry

            sid = session_id if isinstance(session_id, _uuid_mod.UUID) else _uuid_mod.UUID(str(session_id))
            async with _async_session() as _db:
                registry = ModelRegistry(db=_db)
                tracker = ExperimentTracker(db=_db)
                for r in result_dicts:
                    await registry.register_model(
                        session_id=sid,
                        model_name=r.get("model_name", ""),
                        model_path=r.get("model_path"),
                        metrics=r.get("metrics"),
                    )
                    await tracker.log_run(
                        session_id=sid,
                        run_name=r.get("model_name", ""),
                        parameters={"model_types": model_types},
                        metrics=r.get("metrics", {}),
                        model_type=r.get("model_name", ""),
                    )
        except Exception as e:
            logger.warning("modeling_node: registry/tracker failed", error=str(e))

        # Store in code_registry
        try:
            from code_registry.server import store
            store(
                session_id=str(state.get("session_id", "")),
                step="modeling",
                code=f"# Trained models: {', '.join(model_types)}",
                description=f"Model training: {', '.join(model_types)}",
            )
        except Exception as e:
            logger.warning("modeling_node: code_registry failed", error=str(e))

        # Update session doc
        try:
            from session_doc.server import upsert_structured
            sid = str(state.get("session_id", ""))
            model_summaries = []
            models_metadata = []
            for r in result_dicts:
                m = r.get("metrics", {})
                diag = r.get("diagnostics", {})
                fit_status = diag.get("status", "")
                model_summaries.append(
                    f"{r.get('model_name', '?')} (F1={m.get('f1', 0):.2f}"
                    f"{', ' + fit_status if fit_status else ''})"
                )
                models_metadata.append({
                    "model_name": r.get("model_name"),
                    "metrics": m,
                    "model_path": r.get("model_path"),
                    "is_best": r.get("best", False),
                })
            best_name = best.get("model_name", "N/A") if best else "N/A"
            narrative = (
                f"Trained {len(result_dicts)} model(s): {'; '.join(model_summaries)}. "
                f"Best: {best_name}."
            )
            upsert_structured(sid, "Model Results", narrative, metadata={
                "models": models_metadata,
                "best_model": best_name,
                "output_dir": output_dir,
            })

            # Also update Trained Model Paths
            model_paths = [r.get("model_path", "") for r in result_dicts if r.get("model_path")]
            if model_paths:
                path_lines = [f"- {p}" for p in model_paths]
                upsert_structured(sid, "Trained Model Paths",
                                  "\n".join(path_lines),
                                  metadata={"paths": model_paths})
        except Exception as e:
            logger.warning("modeling_node: session_doc upsert failed", error=str(e))

    except Exception as e:
        logger.error("modeling_node: failed", error=str(e))
        state["error"] = str(e)

    clear_business_proposal(state)

    # Only mark DONE on success; FAILED on error
    if state.get("error"):
        mark_step_failed(state, STEP)
    else:
        mark_step_done(state, STEP)
        # Update session memory
        try:
            model_results = state.get("model_results", {})
            best = model_results.get("best_model", "N/A")
            count = len(model_results.get("models", []))
            update_session_memory_md(state, STEP, (
                f"Trained {count} model(s)\n"
                f"Best model: {best}\n"
            ))
        except Exception:
            pass

    state["next_action"] = "orchestrator"
    return state
