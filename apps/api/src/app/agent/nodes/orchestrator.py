"""Orchestrator node — LLM-first routing hub that decides the next pipeline action.

Uses a thin fast-path guard for trivial deterministic cases (approval gates,
all-done, running steps), then delegates to the LLM for primary routing
decisions via CoT-SC (Chain-of-Thought Self-Consistency) with majority voting.
Falls back to a simple "first READY step" heuristic only when the LLM call
itself fails.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog

from app.agent.llm import invoke_llm_json
from app.agent.nodes.node_helpers import emit_trace
from app.agent.state import AgentState
from app.services.step_state_service import (
    DEPENDENCY_GRAPH,
    DONE,
    FAILED,
    READY,
    RUNNING,
    STEP_ORDER,
)

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# State summarisation
# ---------------------------------------------------------------------------

def _summarize_state(state: AgentState) -> dict[str, str]:
    """Build a rich summary of the current state for the LLM prompt.

    Includes session doc content, denial history, and artifact summary in
    addition to the basic step-state / file information.
    """
    step_states: dict[str, str] = state.get("step_states", {})

    # --- failed steps (used in error summary) ---
    failed = [s for s in STEP_ORDER if step_states.get(s) == FAILED]

    # --- uploaded files ---
    files: list[dict[str, Any]] = state.get("uploaded_files", [])
    file_summary = ", ".join(
        f.get("filename", "unknown") for f in files
    ) or "none"

    # --- errors ---
    errors = state.get("error") or "none"
    if failed:
        errors += f" (failed steps: {', '.join(failed)})"

    # --- session doc ---
    session_doc = state.get("session_doc", "") or "No session document yet."

    # --- denial history ---
    denial_counts: dict[str, int] = state.get("denial_counts", {})
    denial_feedback: dict[str, list[str]] = state.get("denial_feedback", {})
    denial_lines: list[str] = []
    for step in STEP_ORDER:
        count = denial_counts.get(step, 0)
        if count > 0:
            feedback = denial_feedback.get(step, [])
            feedback_str = "; ".join(feedback) if feedback else "no feedback"
            denial_lines.append(
                f"- {step}: denied {count}x — {feedback_str}"
            )
    denial_history = "\n".join(denial_lines) if denial_lines else "No denials."

    # --- artifact summary ---
    artifact_parts: list[str] = []
    if state.get("eda_results"):
        eda = state["eda_results"]
        n_plots = len(eda) if isinstance(eda, (list, dict)) else 0
        artifact_parts.append(f"EDA: {n_plots} plots/results")
    if state.get("hypotheses"):
        artifact_parts.append(f"Hypotheses: {len(state['hypotheses'])} tested")
    if state.get("model_results"):
        mr = state["model_results"]
        if isinstance(mr, dict):
            models = mr.get("models", [])
            best = mr.get("best_model", "unknown")
            artifact_parts.append(
                f"Models: {len(models)} trained, best={best}"
            )
        else:
            artifact_parts.append("Models: results available")
    if state.get("explainability_results"):
        artifact_parts.append("SHAP: explainability results available")
    if state.get("recommendations"):
        artifact_parts.append(
            f"Recommendations: {len(state['recommendations'])} generated"
        )
    if state.get("report_path"):
        artifact_parts.append("Report: generated")
    artifact_summary = "\n".join(
        f"- {p}" for p in artifact_parts
    ) if artifact_parts else "No artifacts yet."

    # --- available steps (dependencies met, currently READY) ---
    available: list[str] = []
    for step in STEP_ORDER:
        if step_states.get(step) == READY:
            deps = DEPENDENCY_GRAPH[step]
            if all(step_states.get(d) == DONE for d in deps):
                available.append(step)
    available_steps = ", ".join(available) if available else "none"

    # --- completed session doc sections ---
    try:
        from session_doc.server import get_section
        sid = str(state.get("session_id", ""))
        MANDATORY_SECTIONS = [
            "Data Inventory", "Column Dictionary", "Dtype Decisions",
            "Merge Strategy", "Value Creation Analysis", "Target Variable",
            "Feature Selection", "EDA Findings", "Preprocessing Decisions",
            "Hypotheses & Results", "Feature Engineering", "Model Results",
            "Trained Model Paths", "Generated Code Paths", "Threshold Decisions",
            "Explainability", "Recommendations", "Report",
            "Risk Flags & Warnings", "Experiment Log",
        ]
        completed_sections = []
        pending_sections = []
        for s in MANDATORY_SECTIONS:
            content = get_section(sid, s)
            if content and content != "_Pending_":
                completed_sections.append(s)
            else:
                pending_sections.append(s)
    except Exception:
        completed_sections = []
        pending_sections = []

    if completed_sections:
        session_doc += (
            f"\n\n## Session Doc Status\n"
            f"Completed sections: {', '.join(completed_sections)}\n"
            f"Pending sections: {', '.join(pending_sections)}"
        )

    return {
        "company_name": state.get("company_name", "Unknown"),
        "industry": state.get("industry", "Unknown"),
        "business_context": state.get("business_context", "Not provided"),
        "step_states": json.dumps(step_states, indent=2),
        "uploaded_files": file_summary,
        "target_column": state.get("target_column", "not identified"),
        "errors": errors,
        "session_doc": session_doc,
        "denial_history": denial_history,
        "artifact_summary": artifact_summary,
        "available_steps": available_steps,
    }


# ---------------------------------------------------------------------------
# CoT-SC (Chain-of-Thought Self-Consistency) functions
# ---------------------------------------------------------------------------

async def _generate_candidate_plans(
    state: AgentState, summary: dict[str, str]
) -> list[dict[str, Any]]:
    """Generate multiple candidate plans using CoT-SC (Self-Consistency).

    Makes parallel LLM calls at different temperatures and returns
    all candidate responses for majority voting.
    """
    from app.agent.prompts import ORCHESTRATOR_COT_SC_PROMPT

    prompt = ORCHESTRATOR_COT_SC_PROMPT.format(**summary)
    temperatures = [0.1, 0.3, 0.5]

    async def _call_at_temp(temp: float) -> dict[str, Any]:
        try:
            msgs = [
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": (
                        "Decide the next pipeline action with step-by-step reasoning. "
                        "Respond with JSON only."
                    ),
                },
            ]
            hint = (
                '{"next_action": "<step|wait|end>", '
                '"reasoning": "<string>", '
                '"strategy_hint": "<string>", '
                '"confidence": 0.85}'
            )
            try:
                parsed: dict[str, Any] = await invoke_llm_json(
                    msgs, schema_hint=hint, temperature=temp,
                )
            except Exception as temp_err:
                # Some models (o1, o3) only support default temperature
                if "temperature" in str(temp_err).lower() and "unsupported" in str(temp_err).lower():
                    logger.info("CoT-SC: model does not support temp=%s, using default", temp)
                    parsed = await invoke_llm_json(msgs, schema_hint=hint)
                else:
                    raise
            # Validate required keys
            if "next_action" not in parsed or not isinstance(
                parsed.get("next_action"), str
            ):
                import re
                # Attempt regex repair for next_action
                raw = str(parsed)
                match = re.search(r'"next_action"\s*:\s*"([^"]+)"', raw)
                if match:
                    parsed["next_action"] = match.group(1)
                else:
                    raise ValueError("Missing next_action in LLM response")
            parsed.setdefault("reasoning", "")
            parsed.setdefault("confidence", 0.5)
            parsed.setdefault("strategy_hint", "")
            parsed["temperature"] = temp
            return parsed
        except Exception as e:
            emit_trace(state, "WARNING", "orchestrator", {
                "message": f"CoT-SC candidate failed at temp={temp}",
                "error": str(e),
            })
            return {
                "next_action": "__failed__",
                "reasoning": f"LLM call failed: {e}",
                "confidence": 0.0,
                "temperature": temp,
            }

    candidates = await asyncio.gather(
        *[_call_at_temp(t) for t in temperatures]
    )
    return list(candidates)


def _select_best_candidate(
    candidates: list[dict[str, Any]], state: AgentState
) -> dict[str, Any]:
    """Select the best candidate via majority vote on next_action.

    Filters out failed candidates (confidence 0.0 / __failed__ action).
    Tiebreak by highest confidence score.
    """
    if not candidates:
        return {
            "next_action": "end",
            "reasoning": "No candidates",
            "strategy_hint": "",
            "confidence": 0.0,
        }

    # Filter out failed candidates
    valid = [
        c for c in candidates
        if c.get("next_action") != "__failed__" and c.get("confidence", 0) > 0.0
    ]

    if not valid:
        # All candidates failed — pause safely instead of ending
        emit_trace(state, "WARNING", "orchestrator", {
            "message": "All CoT-SC candidates failed — pausing pipeline safely",
            "candidate_count": len(candidates),
        })
        return {
            "next_action": "wait",
            "reasoning": "All CoT-SC candidates failed. Pausing pipeline for safety.",
            "strategy_hint": "",
            "confidence": 0.0,
        }

    # Count votes per action
    votes: dict[str, list[dict[str, Any]]] = {}
    for c in valid:
        action = c.get("next_action", "end")
        votes.setdefault(action, []).append(c)

    # Find majority action
    best_action = max(votes, key=lambda a: len(votes[a]))
    best_candidates = votes[best_action]

    # Tiebreak by confidence
    return max(best_candidates, key=lambda c: c.get("confidence", 0.0))


async def _reflect_on_results(
    state: AgentState, summary: dict[str, str]
) -> str:
    """Reflect on the results of the last completed step.

    Returns a reflection string that can inform the next decision.
    """
    step_states: dict[str, str] = state.get("step_states", {})

    # Find the most recently completed step
    last_step = ""
    for step in reversed(STEP_ORDER):
        if step_states.get(step) == DONE:
            last_step = step
            break

    if not last_step:
        return ""

    try:
        from app.agent.prompts import ORCHESTRATOR_REFLECTION_PROMPT

        # Build step result summary
        step_result_summary = ""
        if last_step == "modeling" and state.get("model_results"):
            mr = state["model_results"]
            if isinstance(mr, dict):
                step_result_summary = (
                    f"Models trained: {len(mr.get('models', []))}, "
                    f"best: {mr.get('best_model', 'unknown')}"
                )
        elif last_step == "eda" and state.get("eda_results"):
            step_result_summary = "EDA results available"
        elif last_step == "hypothesis" and state.get("hypotheses"):
            step_result_summary = f"{len(state['hypotheses'])} hypotheses tested"
        else:
            step_result_summary = f"Step {last_step} completed"

        prompt = ORCHESTRATOR_REFLECTION_PROMPT.format(
            company_name=summary.get("company_name", ""),
            industry=summary.get("industry", ""),
            last_step=last_step,
            step_result_summary=step_result_summary,
            session_doc=summary.get("session_doc", ""),
            step_states=summary.get("step_states", "{}"),
        )

        parsed = await invoke_llm_json(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": "Reflect on the last step results. JSON only."},
            ],
            schema_hint=(
                '{"assessment": "<string>", "concerns": [], '
                '"adjustments": "<string>", "context_for_next": "<string>"}'
            ),
        )

        return parsed.get("context_for_next", "")
    except Exception as e:
        logger.debug("orchestrator: reflection failed", error=str(e))
        return ""


# ---------------------------------------------------------------------------
# Fast-path guard — only trivially deterministic cases
# ---------------------------------------------------------------------------

def _fast_path_guard(state: AgentState) -> str | None:
    """Handle cases that never need LLM reasoning.

    Returns a next_action string for trivial cases, or ``None`` when the
    LLM should make the decision.

    Trivial cases handled:
    1. awaiting_approval is set  ->  "wait"
    2. pending approval_status   ->  dispatch to that step
    3. all steps DONE            ->  "end"
    4. any step RUNNING          ->  "wait"
    """
    step_states: dict[str, str] = state.get("step_states", {})

    # 1. Pending approval gate — nothing to decide, just wait
    if state.get("awaiting_approval"):
        return "wait"

    # 2. A step was just approved/denied (code proposal) — dispatch back to it
    pending = state.get("pending_step")
    if pending and state.get("approval_status"):
        return pending

    # 3. A business-logic proposal was just resolved — dispatch back to it
    proposal_step = state.get("pending_proposal_step")
    if proposal_step and state.get("proposal_status"):
        return proposal_step

    # 4. A business-logic proposal is pending (no status yet) — wait
    if proposal_step and not state.get("proposal_status"):
        return "wait"

    # 5. Every pipeline step is complete
    if all(step_states.get(s) == DONE for s in STEP_ORDER):
        return "end"

    # 6. Something is already executing
    if any(step_states.get(s) == RUNNING for s in STEP_ORDER):
        return "wait"

    # Not a trivial case — let the LLM decide
    return None


# ---------------------------------------------------------------------------
# Fallback: first READY step (used when LLM call fails)
# ---------------------------------------------------------------------------

def _has_failed_dependency(step: str, step_states: dict[str, str]) -> bool:
    """Check if any dependency (transitive) of a step is FAILED."""
    deps = DEPENDENCY_GRAPH.get(step, [])
    for d in deps:
        if step_states.get(d) == FAILED:
            return True
        # Check transitively
        if _has_failed_dependency(d, step_states):
            return True
    return False


def _fallback_next_ready(state: AgentState) -> str:
    """Return the first READY step whose dependencies are all DONE.

    Used only as a last-resort fallback when the LLM call fails entirely.
    Skips steps whose dependencies include FAILED steps.
    If no step is runnable, returns ``"end"``.
    """
    step_states: dict[str, str] = state.get("step_states", {})
    for step in STEP_ORDER:
        if step_states.get(step) == READY:
            deps = DEPENDENCY_GRAPH[step]
            if all(step_states.get(d) == DONE for d in deps):
                if not _has_failed_dependency(step, step_states):
                    return step
    return "end"


# ---------------------------------------------------------------------------
# Post-LLM validation
# ---------------------------------------------------------------------------

_VALID_META_ACTIONS = {"wait", "end"}


def _validate_llm_action(
    next_action: str,
    state: AgentState,
) -> str | None:
    """Validate an action returned by the LLM.

    Returns the action if valid, or ``None`` if it should be rejected.

    Checks:
    - action is a known step name or a meta-action (wait / end)
    - if it is a step, all its dependencies must be met
    """
    if next_action in _VALID_META_ACTIONS:
        return next_action

    if next_action not in STEP_ORDER:
        logger.warning(
            "orchestrator: LLM returned unknown action",
            action=next_action,
        )
        return None

    step_states: dict[str, str] = state.get("step_states", {})
    deps = DEPENDENCY_GRAPH.get(next_action, [])
    if not all(step_states.get(d) == DONE for d in deps):
        logger.warning(
            "orchestrator: LLM chose step with unmet dependencies",
            action=next_action,
            unmet=[d for d in deps if step_states.get(d) != DONE],
        )
        return None

    # Block steps whose dependency chain includes FAILED steps
    if _has_failed_dependency(next_action, step_states):
        logger.warning(
            "orchestrator: LLM chose step with FAILED dependency",
            action=next_action,
        )
        return None

    return next_action


# ---------------------------------------------------------------------------
# Main orchestrator node
# ---------------------------------------------------------------------------

async def orchestrator_node(state: AgentState) -> AgentState:
    """Central orchestrator node — decides what to do next.

    Flow:
    1. **Fast-path guard** — handles trivially deterministic cases
       (approval gates, all-done, running steps) without an LLM call.
    1b. **Reflection** — reflects on the last completed step to gather
       context for the next decision.
    2. **CoT-SC reasoning** — the primary decision path.  Generates
       multiple candidate plans at different temperatures and selects
       the best via majority vote on ``next_action``.
    3. **Post-LLM validation** — ensures the chosen step exists and its
       dependencies are met.  Rejects invalid choices.
    4. **Fallback** — if the LLM call raises or returns an invalid action,
       falls back to ``_fallback_next_ready()`` (first READY step).
    5. **Emit trace** — writes a DECISION event with reasoning for the
       live-trace sidebar.
    """
    session_id = str(state.get("session_id", ""))
    logger.info("orchestrator_node: executing", session_id=session_id)

    # ---- 0. Loop detection ----
    # Track consecutive routing to the same node to prevent infinite loops
    loop_history: list[str] = list(state.get("_loop_history", []))  # type: ignore[arg-type]
    MAX_SAME_NODE = 2  # max times to route to the same node consecutively

    # ---- 1. Fast-path guard ----
    fast_action = _fast_path_guard(state)
    if fast_action is not None:
        state["next_action"] = fast_action
        state["llm_plan"] = f"Fast-path: {fast_action}"
        state["orchestrator_reasoning"] = f"Deterministic guard: {fast_action}"
        state["strategy_hint"] = ""

        emit_trace(state, "DECISION", "orchestrator", {
            "next_action": fast_action,
            "reasoning": state["orchestrator_reasoning"],
            "strategy_hint": "",
            "source": "fast_path",
        })

        logger.info("orchestrator_node: fast-path decision", action=fast_action)
        return state

    # ---- 1b. Reflect on last step results ----
    summary: dict[str, str] | None = None
    try:
        summary = _summarize_state(state)
        reflection = await _reflect_on_results(state, summary)
        if reflection:
            state["orchestrator_reflection"] = reflection
            # Inject reflection into strategy_hint for the next node
            existing_hint = state.get("strategy_hint", "")
            if existing_hint:
                state["strategy_hint"] = (
                    f"{existing_hint}. Context from reflection: {reflection}"
                )
    except Exception:
        summary = _summarize_state(state)

    # ---- 2. CoT-SC reasoning (primary path) ----
    next_action: str | None = None
    reasoning = ""
    strategy_hint = ""
    source = "cot_sc"

    try:
        if not summary:
            summary = _summarize_state(state)

        # Generate multiple candidates
        candidates = await _generate_candidate_plans(state, summary)
        state["orchestrator_candidates"] = candidates

        # If all candidates failed, _select_best_candidate handles it
        # (returns "wait" instead of "end")
        all_failed = all(
            c.get("next_action") == "__failed__"
            for c in candidates
        )
        if all_failed:
            emit_trace(state, "WARNING", "orchestrator", {
                "message": "All CoT-SC candidates failed — using fallback",
            })

        # Select best via majority vote
        best = _select_best_candidate(candidates, state)
        raw_action = best.get("next_action", "end")
        reasoning = best.get("reasoning", "")
        strategy_hint = best.get("strategy_hint", "")

        # Log candidate diversity
        actions = [c.get("next_action") for c in candidates]
        if len(set(actions)) > 1:
            logger.info(
                "orchestrator: CoT-SC candidates diverged",
                actions=actions,
                selected=raw_action,
            )
            source = "cot_sc_majority"
        else:
            source = "cot_sc_unanimous"

        # ---- 3. Post-LLM validation ----
        next_action = _validate_llm_action(raw_action, state)
        if next_action is None:
            logger.warning(
                "orchestrator_node: LLM action rejected, using fallback",
                raw_action=raw_action,
            )
            next_action = _fallback_next_ready(state)
            reasoning = (
                f"LLM suggested '{raw_action}' but it was invalid "
                f"(unknown step or unmet dependencies). "
                f"Falling back to first ready step: {next_action}"
            )
            source = "fallback_after_invalid_llm"

    except Exception as e:
        # ---- 4. Fallback on LLM failure ----
        logger.error(
            "orchestrator_node: LLM call failed, falling back to heuristic",
            error=str(e),
        )
        next_action = _fallback_next_ready(state)
        reasoning = f"LLM call failed ({e}). Falling back to first ready step."
        strategy_hint = ""
        source = "fallback_after_llm_error"

    # ---- Loop detection ----
    # If we've routed to the same node MAX_SAME_NODE times consecutively,
    # there's likely a bug (node failing silently). Force "wait" to break the loop.
    if next_action and next_action not in ("wait", "end"):
        consecutive = 0
        for prev in reversed(loop_history):
            if prev == next_action:
                consecutive += 1
            else:
                break
        if consecutive >= MAX_SAME_NODE:
            logger.warning(
                "orchestrator: loop detected — same node chosen %d+ times, forcing wait",
                MAX_SAME_NODE,
                action=next_action,
                loop_history=loop_history[-5:],
            )
            emit_trace(state, "WARNING", "orchestrator", {
                "message": f"Loop detected: '{next_action}' chosen {consecutive + 1} consecutive times. "
                           f"Forcing pipeline pause.",
                "looping_node": next_action,
                "consecutive_count": consecutive + 1,
            })
            next_action = "wait"
            reasoning = (
                f"Loop detected: same node '{loop_history[-1]}' chosen "
                f"{consecutive + 1} consecutive times. Pausing pipeline."
            )
            source = "loop_breaker"

        loop_history.append(next_action)
    else:
        # Reset history on wait/end
        loop_history = []

    state["_loop_history"] = loop_history  # type: ignore[literal-required]

    # ---- Commit decision to state ----
    state["next_action"] = next_action
    state["llm_plan"] = reasoning
    state["orchestrator_reasoning"] = reasoning
    state["strategy_hint"] = strategy_hint

    # ---- 5. Emit DECISION trace event ----
    emit_trace(state, "DECISION", "orchestrator", {
        "next_action": next_action,
        "reasoning": reasoning,
        "strategy_hint": strategy_hint,
        "source": source,
    })

    logger.info(
        "orchestrator_node: decision",
        action=next_action,
        source=source,
        reasoning=reasoning[:120],
    )

    return state
