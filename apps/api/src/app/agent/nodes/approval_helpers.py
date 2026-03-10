"""Helpers for the two-phase approval pattern in code-generating nodes.

Phase 1 (propose): Node generates a code description, sets pending_* fields,
    and returns with next_action="wait". The graph ends and AgentService
    creates a CodeProposal in the DB.

Phase 2 (execute): On resume, the node receives approval_status in its state
    and either executes or skips.

Self-heal: If denied and denial count < MAX_DENIALS, the node can re-propose
    with modifications instead of skipping.
"""

from __future__ import annotations

from typing import Any

from app.agent.state import AgentState
from app.services.step_state_service import DEPENDENCY_GRAPH, DONE, FAILED, NOT_STARTED, READY

MAX_DENIALS = 3


def check_approval_phase(state: AgentState, step: str) -> str:
    """Determine what phase a code-generating node is in.

    Returns:
        "propose" — first visit, should generate code description and wait
        "execute" — user approved, proceed with execution
        "denied"  — user denied, may re-propose if under MAX_DENIALS
        "skip"    — still pending (shouldn't normally reach here)
    """
    if state.get("pending_step") == step:
        status = state.get("approval_status", "")
        if status == "approved":
            return "execute"
        elif status == "denied":
            return "denied"
        else:
            return "skip"
    return "propose"


def get_denial_count(state: AgentState, step: str) -> int:
    """Get the number of times a step's code has been denied."""
    denial_counts: dict = state.get("denial_counts", {})  # type: ignore[assignment]
    return denial_counts.get(step, 0)


def increment_denial_count(state: AgentState, step: str) -> int:
    """Increment and return the denial count for a step."""
    denial_counts: dict = dict(state.get("denial_counts", {}))  # type: ignore[arg-type]
    denial_counts[step] = denial_counts.get(step, 0) + 1
    state["denial_counts"] = denial_counts  # type: ignore[literal-required]
    return denial_counts[step]


def should_repropose(state: AgentState, step: str) -> bool:
    """Check if a denied step should re-propose (under MAX_DENIALS threshold)."""
    count = get_denial_count(state, step)
    return count < MAX_DENIALS


def get_denial_feedback(state: AgentState, step: str) -> list[str]:
    """Get user denial feedback strings for a step."""
    feedback: dict[str, list[str]] = state.get("denial_feedback", {})
    return feedback.get(step, [])


def set_proposal(
    state: AgentState,
    step: str,
    code: str,
    description: str,
    context: dict[str, Any] | None = None,
) -> AgentState:
    """Set state fields for a code proposal and pause the pipeline.

    Args:
        state: Current agent state.
        step: Pipeline step name.
        code: Code to propose.
        description: Human-readable description.
        context: Optional rich context dict (ai_explanation, tool_tried, etc.)
            stored with the CodeProposal and displayed in the frontend modal.
    """
    state["pending_step"] = step
    state["pending_code"] = code
    state["pending_code_description"] = description
    state["next_action"] = "wait"
    if context is not None:
        state["pending_context"] = context
    return state


def clear_approval(state: AgentState) -> AgentState:
    """Clear approval fields after execution or denial."""
    state["pending_step"] = ""
    state["pending_code"] = ""
    state["pending_code_description"] = ""
    state["approval_status"] = ""
    state["approved_code"] = ""
    return state


def mark_step_done(state: AgentState, step: str) -> AgentState:
    """Mark step as DONE in step_states and make dependents READY."""
    step_states = dict(state.get("step_states", {}))
    step_states[step] = DONE

    for dep_step, deps in DEPENDENCY_GRAPH.items():
        if step in deps:
            if all(step_states.get(d) == DONE for d in deps):
                if step_states.get(dep_step) in (NOT_STARTED, None):
                    step_states[dep_step] = READY

    state["step_states"] = step_states
    return state


def mark_step_failed(state: AgentState, step: str) -> AgentState:
    """Mark step as FAILED — real execution/system/tool failure.

    Does NOT cascade READY to dependents; they remain NOT_STARTED
    or whatever state they were in, preventing downstream progress.
    """
    step_states = dict(state.get("step_states", {}))
    step_states[step] = FAILED
    state["step_states"] = step_states
    return state


def mark_step_skipped(state: AgentState, step: str, reason: str) -> AgentState:
    """Mark step as DONE with a skip reason — user-approved skip path.

    Use when the user explicitly approves skipping (e.g. single file,
    no merge needed). Records the skip reason in state metadata and
    cascades READY to dependents just like mark_step_done.
    """
    # Record skip reason in state metadata
    skip_reasons: dict = dict(state.get("skip_reasons", {}))  # type: ignore[arg-type]
    skip_reasons[step] = reason
    state["skip_reasons"] = skip_reasons  # type: ignore[literal-required]

    # Delegate to mark_step_done for the actual DONE + cascade logic
    return mark_step_done(state, step)


def revert_step_to_ready(state: AgentState, step: str) -> AgentState:
    """Revert step back to READY — user rejected but step is revisable.

    Use when the user rejects a proposal but the step should remain
    open for the orchestrator to re-propose.
    """
    step_states = dict(state.get("step_states", {}))
    step_states[step] = READY
    state["step_states"] = step_states
    return state


# ---------------------------------------------------------------------------
# Business-logic proposal helpers (plan-level approval)
# ---------------------------------------------------------------------------

MAX_REVISIONS = 3


def check_proposal_phase(state: AgentState, step: str) -> str:
    """Determine what phase a proposal-generating node is in.

    Returns:
        "propose" — first visit, should generate plan and wait
        "execute" — user approved, proceed with execution
        "revision_requested" — user requested changes, revise and re-propose
        "rejected" — user rejected, offer alternatives or wait
        "skip" — still pending (shouldn't normally reach here)
    """
    if state.get("pending_proposal_step") == step:
        status = state.get("proposal_status", "")
        if status == "approved":
            return "execute"
        elif status == "revision_requested":
            return "revision_requested"
        elif status == "rejected":
            return "rejected"
        elif status:
            return status
        else:
            return "skip"
    return "propose"


def set_business_proposal(
    state: AgentState,
    step: str,
    proposal_type: str,
    plan: dict[str, Any],
    summary: str,
    reasoning: str,
    alternatives: list[dict[str, Any]] | None = None,
) -> AgentState:
    """Set state fields for a business-logic proposal and pause the pipeline."""
    state["pending_proposal_step"] = step
    state["pending_proposal_type"] = proposal_type
    state["pending_proposal_plan"] = plan
    state["pending_proposal_summary"] = summary
    state["pending_proposal_reasoning"] = reasoning
    state["pending_proposal_alternatives"] = alternatives or []
    state["next_action"] = "wait"
    return state


def clear_business_proposal(state: AgentState) -> AgentState:
    """Clear business-logic proposal fields after resolution."""
    state["pending_proposal_step"] = ""
    state["pending_proposal_type"] = ""
    state["pending_proposal_plan"] = {}
    state["pending_proposal_summary"] = ""
    state["pending_proposal_reasoning"] = ""
    state["pending_proposal_alternatives"] = []
    state["proposal_status"] = ""
    state["proposal_feedback"] = ""
    return state


def get_proposal_feedback(state: AgentState, step: str) -> str:
    """Get user feedback for a proposal revision request."""
    return state.get("proposal_feedback", "")


def should_revise(state: AgentState, step: str) -> bool:
    """Check if a proposal should be revised (under MAX_REVISIONS threshold)."""
    revision_counts: dict = state.get("proposal_revision_count", {})  # type: ignore[assignment]
    count = revision_counts.get(step, 0)
    return count < MAX_REVISIONS


def increment_revision_count(state: AgentState, step: str) -> int:
    """Increment and return the revision count for a step's proposal."""
    revision_counts: dict = dict(state.get("proposal_revision_count", {}))  # type: ignore[arg-type]
    revision_counts[step] = revision_counts.get(step, 0) + 1
    state["proposal_revision_count"] = revision_counts  # type: ignore[literal-required]
    return revision_counts[step]
