"""Hypothesis node — proposes hypothesis batch with proposal/approval loop.

Proposes a set of statistical hypotheses as a business-logic Proposal.
User can approve, modify, or reject. On approval, runs approved tests.
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
    mark_step_failed,
    set_business_proposal,
    should_revise,
)
from app.agent.nodes.node_helpers import emit_trace, read_step_context, update_session_memory_md
from app.agent.state import AgentState
from app.config import settings

logger = structlog.get_logger()

_mcp_root = str(Path(__file__).resolve().parents[6] / "packages" / "mcp-servers" / "src")
if _mcp_root not in sys.path:
    sys.path.insert(0, _mcp_root)

_shared_root = str(Path(__file__).resolve().parents[6] / "packages")
if _shared_root not in sys.path:
    sys.path.insert(0, _shared_root)

STEP = "hypothesis"

HYPOTHESIS_SELECTION_PROMPT = """\
You are an AI data scientist selecting hypotheses for statistical testing.

## Business Context
- Company: {company_name}
- Industry: {industry}
- Goal: {business_context}
- Target Column: {target_column}

## Available Columns
{columns}

## Previous Context
{session_doc_section}

## Strategy Hint
{strategy_hint}

## User Feedback (if revision)
{feedback}

## Instructions
Explain your rationale for which statistical hypotheses to test given this \
dataset and business context. Consider:
- Which features are most likely to have a statistically significant \
relationship with the target?
- What types of tests (t-test, chi-square, correlation) are appropriate for \
the column types?
- How do the business goals inform which relationships matter most?

Respond with ONLY valid JSON:
{{"rationale": "<2-3 sentences explaining hypothesis selection strategy>", \
"focus_areas": ["<area1>", "<area2>"]}}\
"""


async def hypothesis_node(state: AgentState) -> AgentState:
    """Generate and run statistical hypothesis tests with proposal loop."""
    logger.info("hypothesis_node: executing", session_id=str(state.get("session_id")))
    state["current_step"] = STEP

    step_context = read_step_context(state, STEP)

    phase = check_proposal_phase(state, STEP)

    if phase == "propose":
        return await _propose_hypotheses(state, step_context)
    elif phase == "execute":
        return await _execute_hypotheses(state)
    elif phase == "revision_requested":
        if should_revise(state, STEP):
            increment_revision_count(state, STEP)
            return await _propose_hypotheses(state, step_context, revision=True)
        return await _execute_hypotheses(state)
    elif phase == "rejected":
        emit_trace(state, "INFO", STEP, {
            "message": "Hypothesis testing rejected; skipping"
        })
        state["hypotheses"] = []
        clear_business_proposal(state)
        mark_step_done(state, STEP)
        state["next_action"] = "orchestrator"
        return state
    else:
        state["next_action"] = "wait"
        return state


async def _propose_hypotheses(
    state: AgentState,
    step_context: dict,
    revision: bool = False,
) -> AgentState:
    """Generate hypothesis batch proposal."""
    feedback = ""
    if revision:
        feedback = get_proposal_feedback(state, STEP)

    target_col = state.get("target_column", "")
    files = state.get("uploaded_files", [])

    if not files or not target_col:
        state["error"] = "Missing files or target column for hypothesis testing"
        return state

    file_path = state.get("merged_df_path") or state.get("cleaned_df_path")
    if not file_path:
        primary = files[0]
        file_path = primary.get("storage_path", "")
        if not Path(file_path).exists():
            file_path = str(Path(settings.upload_dir) / file_path)

    if not file_path or not Path(file_path).exists():
        state["error"] = f"Data file not found: {file_path}"
        return state

    try:
        import pandas as pd
        from shared.python.schemas import TableInfo
        from hypothesis.server import generate_hypotheses

        df_head = (
            pd.read_csv(file_path, nrows=5)
            if file_path.endswith(".csv")
            else pd.read_excel(file_path, nrows=5)
        )
        columns = df_head.columns.tolist()

        # Filter to selected features
        selected = state.get("selected_features")
        if selected:
            allowed = set(selected) | {target_col}
            columns = [c for c in columns if c in allowed]

        # Get LLM rationale
        rationale = ""
        focus_areas = []
        try:
            rationale_prompt = HYPOTHESIS_SELECTION_PROMPT.format(
                company_name=state.get("company_name", ""),
                industry=state.get("industry", ""),
                business_context=state.get("business_context", ""),
                target_column=target_col,
                columns=", ".join(columns),
                session_doc_section=step_context.get("session_doc_section", ""),
                strategy_hint=step_context.get("strategy_hint", ""),
                feedback=feedback or "None",
            )
            rationale_result = await invoke_llm_json(
                [{"role": "user", "content": rationale_prompt}],
                schema_hint='{"rationale": str, "focus_areas": [str]}',
            )
            rationale = rationale_result.get("rationale", "")
            focus_areas = rationale_result.get("focus_areas", [])
        except Exception as e:
            logger.warning("hypothesis_node: LLM rationale failed", error=str(e))
            rationale = "Automatic hypothesis generation based on column types"

        # Generate hypotheses via MCP tool
        session_id = state.get("session_id")
        table_info = TableInfo(
            file_id=str(session_id),
            filename=Path(file_path).name,
            row_count=0,
            column_count=len(columns),
            columns=columns,
        )

        hypotheses = generate_hypotheses(
            table_info=table_info,
            target=target_col,
            context=state.get("business_context", ""),
        )

        # Build proposal plan
        hyp_list = [
            {
                "id": h.id,
                "statement": h.statement,
                "test_type": h.test_type,
                "variables": h.variables,
                "expected_outcome": h.expected_outcome,
            }
            for h in hypotheses
        ]

        plan = {
            "hypotheses": hyp_list,
            "rationale": rationale,
            "focus_areas": focus_areas,
            "total_hypotheses": len(hyp_list),
            "file_path": file_path,
        }

        summary = f"Propose {len(hyp_list)} hypothesis tests for target '{target_col}'"
        if feedback:
            summary += " (revised based on feedback)"

        emit_trace(state, "AI_REASONING", STEP, {
            "message": summary,
            "hypothesis_count": len(hyp_list),
            "rationale": rationale,
        })

        return set_business_proposal(
            state, STEP, "hypothesis_batch", plan, summary, rationale,
        )

    except Exception as e:
        logger.error("hypothesis_node: proposal generation failed", error=str(e))
        state["error"] = str(e)
        return state


async def _execute_hypotheses(state: AgentState) -> AgentState:
    """Execute the approved hypothesis tests."""
    plan = state.get("pending_proposal_plan", {})
    hyp_list = plan.get("hypotheses", [])
    file_path = plan.get("file_path", "")

    if not hyp_list:
        state["hypotheses"] = []
        clear_business_proposal(state)
        mark_step_done(state, STEP)
        state["next_action"] = "orchestrator"
        return state

    if not file_path:
        file_path = state.get("merged_df_path") or state.get("cleaned_df_path", "")

    try:
        from shared.python.schemas import Hypothesis
        from hypothesis.server import run_test

        # Reconstruct Hypothesis objects
        hypotheses = []
        for h in hyp_list:
            hypotheses.append(Hypothesis(
                id=h.get("id", ""),
                statement=h.get("statement", ""),
                test_type=h.get("test_type", ""),
                variables=h.get("variables", []),
                expected_outcome=h.get("expected_outcome", ""),
            ))

        # Run each test
        test_results = []
        for hyp in hypotheses:
            emit_trace(state, "TOOL_CALL", STEP, {
                "tool": "hypothesis.run_test",
                "args": {
                    "hypothesis_id": hyp.id,
                    "test_type": hyp.test_type,
                },
            })

            result = run_test(file_path=file_path, hypothesis=hyp)
            test_results.append(result)

            emit_trace(state, "TOOL_RESULT", STEP, {
                "tool": "hypothesis.run_test",
                "hypothesis_id": hyp.id,
                "conclusion": result.conclusion,
                "p_value": result.p_value,
            })

        # Build results
        hyp_dicts = []
        for hyp, result in zip(hypotheses, test_results):
            hyp_dicts.append({
                "id": hyp.id,
                "statement": hyp.statement,
                "test_type": hyp.test_type,
                "variables": hyp.variables,
                "expected_outcome": hyp.expected_outcome,
                "result": result.model_dump(),
            })

        state["hypotheses"] = hyp_dicts

        supported = sum(1 for r in test_results if r.conclusion == "supported")
        rejected = sum(1 for r in test_results if r.conclusion == "rejected")

        emit_trace(state, "TOOL_RESULT", STEP, {
            "message": (
                f"Hypothesis testing complete: {supported}/{len(test_results)} "
                f"supported, {rejected} rejected"
            ),
            "total": len(test_results),
            "supported": supported,
            "rejected": rejected,
        })

        # Update session doc
        try:
            from session_doc.server import upsert_structured
            sid = str(state.get("session_id", ""))
            narrative = (
                f"Ran {len(test_results)} test(s): "
                f"{supported} supported, {rejected} rejected."
            )
            hyp_metadata = []
            for hyp, result in zip(hypotheses, test_results):
                hyp_metadata.append({
                    "statement": hyp.statement,
                    "test_type": hyp.test_type,
                    "conclusion": result.conclusion,
                    "p_value": result.p_value,
                })
            upsert_structured(sid, "Hypotheses & Results", narrative, metadata={
                "total_tests": len(test_results),
                "supported": supported,
                "rejected": rejected,
                "hypotheses": hyp_metadata,
            })
        except Exception as e:
            logger.warning("hypothesis_node: session_doc upsert failed", error=str(e))

    except Exception as e:
        logger.error("hypothesis_node: execution failed", error=str(e))
        state["error"] = str(e)

    clear_business_proposal(state)

    # Only mark DONE on success; FAILED on error
    if state.get("error"):
        mark_step_failed(state, STEP)
    else:
        mark_step_done(state, STEP)
        # Update session memory
        try:
            hyps = state.get("hypotheses", [])
            supported = sum(1 for h in hyps if h.get("result", {}).get("conclusion") == "supported")
            update_session_memory_md(state, STEP, (
                f"Tested {len(hyps)} hypothesis(es)\n"
                f"Supported: {supported}, Rejected: {len(hyps) - supported}\n"
            ))
        except Exception:
            pass

    state["next_action"] = "orchestrator"
    return state
