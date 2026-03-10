"""Composable helper functions for agent nodes.

Provides trace event emission, session doc reading, and action classification
that every node uses for the 5-phase protocol:
1. Read context  2. Plan via LLM  3. Classify  4. Execute/propose  5. Post-execute

Also provides:
- execute_via_policy: centralized policy enforcement with fallback
- react_execute: ReAct loop (think → act → observe → reflect → retry)
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Awaitable, Callable

import structlog

from app.agent.state import AgentState

logger = structlog.get_logger()

# Ensure MCP servers package is importable
_mcp_root = str(Path(__file__).resolve().parents[6] / "packages" / "mcp-servers" / "src")
if _mcp_root not in sys.path:
    sys.path.insert(0, _mcp_root)

# Ensure shared schemas package (packages/shared/) is importable
_packages_root = str(Path(__file__).resolve().parents[6] / "packages")
if _packages_root not in sys.path:
    sys.path.insert(0, _packages_root)

# Read-only (safe) MCP tools that can auto-execute without approval
_READ_ONLY_TOOLS = {
    ("data_ingest", "profile"),
    ("data_ingest", "sample"),
    ("data_ingest", "row_count"),
    ("data_ingest", "list_sheets"),
    ("session_doc", "read"),
    ("session_doc", "get_section"),
    ("eda_plots", "distribution_plot"),
    ("eda_plots", "correlation_matrix"),
    ("eda_plots", "scatter_plot"),
    ("eda_plots", "box_plot"),
    ("eda_plots", "target_analysis"),
    ("hypothesis", "generate_hypotheses"),
    ("hypothesis", "run_test"),
    ("hypothesis", "summarize_results"),
    ("modeling_explain", "shap_analysis"),
    ("modeling_explain", "feature_importance"),
    ("modeling_explain", "predict"),
    ("modeling_explain", "detect_leakage"),
    ("modeling_explain", "calibration_analysis"),
    ("modeling_explain", "learning_curve_analysis"),
    ("modeling_explain", "generate_model_card"),
    ("dtype_manager", "suggest_types"),
    ("dtype_manager", "validate_types"),
    ("code_registry", "retrieve"),
    ("code_registry", "get_latest"),
    ("merge_planner", "detect_keys"),
}

# Step → list of session doc sections that provide important context
STEP_CONTEXT_DEPENDENCIES: dict[str, list[str]] = {
    "modeling": ["Feature Selection", "Preprocessing Decisions", "Target Variable"],
    "explainability": ["Model Results", "Trained Model Paths"],
    "feature_eng": ["Feature Selection", "Dtype Decisions", "Preprocessing Decisions"],
    "hypothesis": ["EDA Findings", "Target Variable", "Data Inventory"],
    "recommendation": ["Model Results", "Explainability", "Hypotheses & Results"],
    "report": ["Model Results", "Recommendations", "Explainability", "EDA Findings"],
    "preprocessing": ["Dtype Decisions", "Feature Selection", "Target Variable"],
    "eda": ["Target Variable", "Data Inventory", "Dtype Decisions"],
    "feature_selection": ["Target Variable", "Data Inventory", "Dtype Decisions"],
    "target_id": ["Data Inventory", "Value Creation Analysis"],
    "threshold_calibration": ["Model Results", "Target Variable"],
}


def emit_trace(
    state: AgentState,
    event_type: str,
    step: str,
    payload: dict[str, Any],
) -> None:
    """Append a trace event to the state's trace_events list.

    These are persisted to DB and broadcast via SSE by agent_service
    incrementally during astream() execution.
    """
    events: list[dict[str, Any]] = list(state.get("trace_events", []))
    events.append({
        "event_type": event_type,
        "step": step,
        "payload": payload,
    })
    state["trace_events"] = events


def read_step_context(state: AgentState, step: str) -> dict[str, Any]:
    """Read all relevant context for a node before planning.

    Returns a dict with:
    - session_doc_section: content from session doc for this step
    - strategy_hint: guidance from orchestrator
    - denial_feedback: list of user feedback strings for this step
    - denial_count: number of times this step was denied
    - session_doc_full: full session doc text
    """
    context: dict[str, Any] = {
        "session_doc_section": "",
        "strategy_hint": state.get("strategy_hint", ""),
        "denial_feedback": [],
        "denial_count": 0,
        "session_doc_full": state.get("session_doc", ""),
    }

    # Read session doc section for this step
    try:
        from session_doc.server import get_section
        section_name = _step_to_section(step)
        section = get_section(str(state.get("session_id", "")), section_name)
        if section:
            context["session_doc_section"] = section
    except Exception as e:
        logger.debug("read_step_context: session doc read failed", error=str(e))

    # Read dependent sections for richer context
    dependent_sections: dict[str, str] = {}
    deps = STEP_CONTEXT_DEPENDENCIES.get(step, [])
    if deps:
        try:
            from session_doc.server import get_section
            sid = str(state.get("session_id", ""))
            for section_name in deps:
                content = get_section(sid, section_name)
                if content and content != "_Pending_":
                    dependent_sections[section_name] = content
        except Exception as e:
            logger.debug("read_step_context: dependent sections read failed", error=str(e))
    context["dependent_sections"] = dependent_sections

    # Read denial feedback
    denial_feedback: dict[str, list[str]] = state.get("denial_feedback", {})
    context["denial_feedback"] = denial_feedback.get(step, [])

    # Read denial count
    denial_counts: dict[str, int] = state.get("denial_counts", {})
    context["denial_count"] = denial_counts.get(step, 0)

    return context


def classify_action(server: str, tool: str) -> str:
    """Classify an MCP tool call as auto-executable or requiring approval.

    Returns:
        "auto" — safe read-only operation, can execute without user approval
        "approval_required" — mutating operation, needs user review
    """
    if (server, tool) in _READ_ONLY_TOOLS:
        return "auto"
    return "approval_required"


def build_context_payload(
    state: AgentState,
    step: str,
    *,
    ai_explanation: str = "",
    tool_tried: str = "",
    tool_insufficiency: str = "",
    alternative_strategies: list[str] | None = None,
) -> dict[str, Any]:
    """Build a rich context payload for code proposals.

    This context is stored with the CodeProposal and displayed
    in the frontend approval modal.
    """
    denial_counts: dict[str, int] = state.get("denial_counts", {})
    denial_feedback: dict[str, list[str]] = state.get("denial_feedback", {})

    return {
        "ai_explanation": ai_explanation,
        "tool_tried": tool_tried,
        "tool_insufficiency": tool_insufficiency,
        "alternative_strategies": alternative_strategies or [],
        "denial_count": denial_counts.get(step, 0),
        "max_denials": 3,
        "denial_feedback": denial_feedback.get(step, []),
    }


# ---------------------------------------------------------------------------
# Phase 12: execute_via_policy — centralized policy enforcement with fallback
# ---------------------------------------------------------------------------


async def execute_via_policy(
    state: AgentState,
    step: str,
    server: str,
    tool: str,
    arguments: dict[str, Any],
    description: str = "",
) -> Any:
    """Execute a tool via the ExecutionPolicyService.

    Provides centralized policy enforcement with fallback to direct
    MCP bridge calls if the policy service fails.

    Returns the tool result if auto-executed, or None if approval needed.
    """
    try:
        from app.services.execution_policy import ExecutionPolicyService

        policy = ExecutionPolicyService()
        result = await policy.execute_and_record(
            state, step, server, tool, arguments, description
        )

        # Emit trace events from the policy
        for event in result.trace_events:
            emit_trace(state, event["event_type"], event["step"], event["payload"])

        if result.success and not result.proposal_needed:
            return result.result
        elif result.proposal_needed:
            emit_trace(state, "INFO", step, {
                "message": f"Tool {server}.{tool} requires approval",
                "proposal_data": result.proposal_data,
            })
            return None
        else:
            emit_trace(state, "ERROR", step, {
                "message": f"Policy execution failed: {result.error}",
            })
            # Fall through to direct call
    except Exception as e:
        logger.warning(
            "execute_via_policy: policy service failed, falling back to direct call",
            error=str(e),
        )

    # Fallback: direct MCP bridge call
    try:
        from app.agent.tools.mcp_bridge import MCPBridge

        bridge = MCPBridge()
        return await bridge.call_tool(server, tool, arguments)
    except Exception as e:
        logger.error("execute_via_policy: direct call also failed", error=str(e))
        emit_trace(state, "ERROR", step, {
            "message": f"Tool call failed: {server}.{tool}: {e}",
        })
        return None


# ---------------------------------------------------------------------------
# react_execute — ReAct per-step loop (infrastructure, tested but not yet
# wired into nodes)
# ---------------------------------------------------------------------------


async def react_execute(
    state: AgentState,
    step: str,
    action_fn: Callable[[AgentState], Awaitable[Any]],
    validate_fn: Callable[[Any], tuple[bool, str]],
    max_retries: int = 3,
) -> Any:
    """ReAct loop: think -> act -> observe -> reflect -> retry/revise.

    Args:
        state: AgentState
        step: Pipeline step name
        action_fn: async callable(state) that performs the action, returns result
        validate_fn: callable(result) -> (success: bool, observation: str)
        max_retries: max retries before escalating to user

    Returns:
        result if success, or None (node should set proposal/wait state)
    """
    for attempt in range(max_retries):
        emit_trace(state, "AI_REASONING", step, {
            "phase": "think",
            "attempt": attempt + 1,
            "message": f"Attempt {attempt + 1}/{max_retries}",
        })

        try:
            result = await action_fn(state)
        except Exception as e:
            emit_trace(state, "AI_REASONING", step, {
                "phase": "observe",
                "error": str(e),
                "message": f"Action failed: {e}",
            })
            if attempt < max_retries - 1:
                emit_trace(state, "AI_REASONING", step, {
                    "phase": "reflect",
                    "message": "Retrying with adjusted parameters",
                })
                continue
            break

        success, observation = validate_fn(result)
        emit_trace(state, "AI_REASONING", step, {
            "phase": "observe",
            "success": success,
            "message": observation,
        })

        if success:
            emit_trace(state, "AI_REASONING", step, {
                "phase": "reflect",
                "message": f"Success after {attempt + 1} attempt(s)",
            })
            return result

        if attempt < max_retries - 1:
            emit_trace(state, "AI_REASONING", step, {
                "phase": "reflect",
                "message": f"Validation failed: {observation}. Retrying.",
            })

    # All retries exhausted — escalate to user
    emit_trace(state, "AI_REASONING", step, {
        "phase": "escalate",
        "message": "Max retries reached. Requesting user input.",
    })
    return None


# ---------------------------------------------------------------------------
# Session-centric storage helpers
# ---------------------------------------------------------------------------


def get_session_dir(state: AgentState) -> Path:
    """Return the session directory: <upload_dir>/<session_id>/."""
    from app.config import settings
    session_id = str(state.get("session_id", ""))
    session_dir = Path(settings.upload_dir) / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


def save_code_artifact(
    state: AgentState,
    step: str,
    code: str,
    description: str,
    version: int = 1,
) -> Path:
    """Save generated code to <session_dir>/code/<step>_v<version>.py.

    Adds a provenance header comment with step, version, and description.
    Returns the path to the saved file.
    """
    import datetime

    session_dir = get_session_dir(state)
    code_dir = session_dir / "code"
    code_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{step}_v{version}.py"
    filepath = code_dir / filename

    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    header = (
        f"# Auto-generated by VC Insight Engine\n"
        f"# Step: {step}\n"
        f"# Version: {version}\n"
        f"# Timestamp: {timestamp}\n"
        f"# Description: {description}\n"
        f"# Session: {state.get('session_id', '')}\n"
        f"#\n\n"
    )

    filepath.write_text(header + code, encoding="utf-8")
    logger.info(
        "save_code_artifact: saved",
        step=step,
        version=version,
        path=str(filepath),
    )
    return filepath


def update_session_memory_md(
    state: AgentState,
    step: str,
    content: str,
) -> Path:
    """Append a section to <session_dir>/memory/session.md.

    Each call appends a timestamped section for the given step.
    Returns the path to the session.md file.
    """
    import datetime

    session_dir = get_session_dir(state)
    memory_dir = session_dir / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)

    md_path = memory_dir / "session.md"

    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    step_title = step.replace("_", " ").title()

    section = f"\n## {step_title} ({timestamp})\n{content}\n"

    # Append (create if not exists)
    with open(md_path, "a", encoding="utf-8") as f:
        if md_path.stat().st_size == 0:
            f.write(f"# Session Memory — {state.get('company_name', 'Unknown')}\n")
        f.write(section)

    return md_path


def record_step_provenance(
    state: AgentState,
    step: str,
    code: str,
    stdout: str = "",
    stderr: str = "",
    artifacts: list[str] | None = None,
) -> None:
    """Record execution provenance for a step: code, output, artifacts."""
    try:
        from code_registry.server import store
        store(
            session_id=str(state.get("session_id", "")),
            step=step,
            code=code,
            description=f"Executed code for {step}",
        )
    except Exception as e:
        logger.warning("record_step_provenance: code_registry store failed", error=str(e))


def _step_to_section(step: str) -> str:
    """Map pipeline step names to session doc section titles."""
    mapping = {
        "profiling": "Column Dictionary",
        "dtype_handling": "Dtype Decisions",
        "data_understanding": "Data Inventory",
        "merge_planning": "Merge Strategy",
        "opportunity_analysis": "Value Creation Analysis",
        "target_id": "Target Variable",
        "feature_selection": "Feature Selection",
        "eda": "EDA Findings",
        "preprocessing": "Preprocessing Decisions",
        "hypothesis": "Hypotheses & Results",
        "hypothesis_generation": "Hypotheses & Results",
        "hypothesis_execution": "Hypotheses & Results",
        "feature_eng": "Feature Engineering",
        "modeling": "Model Results",
        "threshold_calibration": "Threshold Decisions",
        "explainability": "Explainability",
        "recommendation": "Recommendations",
        "report": "Report",
    }
    return mapping.get(step, step.replace("_", " ").title())
