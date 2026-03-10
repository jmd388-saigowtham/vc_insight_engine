"""Opportunity analysis node — Value Creation Recommendations.

Runs after data understanding. Calls LLM with data understanding summary,
business context, and industry to propose MULTIPLE value creation
recommendations. User selects one recommendation to pursue.

This is NOT a simple approve/reject — this is a directional choice
that shapes the rest of the pipeline.
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from app.agent.nodes.approval_helpers import (
    check_proposal_phase,
    clear_business_proposal,
    get_proposal_feedback,
    increment_revision_count,
    mark_step_done,
    set_business_proposal,
    should_revise,
)
from app.agent.nodes.node_helpers import emit_trace
from app.agent.state import AgentState

logger = structlog.get_logger()

OPPORTUNITY_ANALYSIS_PROMPT = """\
You are a senior VC data scientist identifying value creation opportunities
for a portfolio company.

## Business Context
- Company: {company_name}
- Industry: {industry}
- Business Goal: {business_context}

## Data Understanding Summary
{data_understanding}

## Column Profiles (key columns)
{key_columns}

## Previous Feedback (if revision)
{feedback}

## Instructions
Based on the data and business context, propose 2-4 distinct value creation
recommendations. Each recommendation should represent a different analytical
direction the team could pursue.

For EACH recommendation, provide:
1. **Title**: Clear, actionable name (e.g., "Customer Churn Prediction")
2. **Description**: 2-3 sentences on what this analysis would achieve
3. **Use Case**: churn, expansion, cross_sell, upsell, or other
4. **Feasibility**: How well the available data supports this analysis (0.0-1.0)
5. **Confidence**: How confident you are this will yield actionable insights (0.0-1.0)
6. **Data Requirements**: Which columns/tables are needed
7. **Potential Target**: Which column would serve as the prediction target
8. **Business Impact**: Expected business impact if successful
9. **Risks**: Key risks or data limitations

The user will SELECT one of these to pursue — they are not approving/rejecting,
they are choosing a direction.

Respond with ONLY valid JSON:
{{
  "options": [
    {{
      "title": "<clear title>",
      "description": "<2-3 sentences>",
      "use_case": "<churn|expansion|cross_sell|upsell|other>",
      "feasibility": 0.85,
      "confidence": 0.8,
      "data_requirements": ["<col1>", "<col2>"],
      "potential_target": "<target column name>",
      "business_impact": "<expected impact>",
      "risks": ["<risk1>"]
    }}
  ],
  "overall_assessment": "<1-2 sentences on data readiness>"
}}\
"""


async def opportunity_analysis_node(state: AgentState) -> AgentState:
    """Propose value creation recommendations for user selection."""
    step = "opportunity_analysis"
    session_id = str(state.get("session_id", ""))
    logger.info("opportunity_analysis_node: executing", session_id=session_id)

    phase = check_proposal_phase(state, step)

    if phase == "propose":
        return await _propose_opportunities(state, step)
    elif phase == "execute":
        return await _execute_selection(state, step)
    elif phase == "revision_requested":
        if should_revise(state, step):
            increment_revision_count(state, step)
            return await _propose_opportunities(state, step, revision=True)
        # Max revisions reached — use first option as default
        clear_business_proposal(state)
        mark_step_done(state, step)
        state["next_action"] = "orchestrator"
        return state
    elif phase == "rejected":
        emit_trace(state, "INFO", step, {
            "message": "Opportunity analysis rejected; pausing for user direction"
        })
        clear_business_proposal(state)
        state["next_action"] = "wait"
        return state
    else:
        state["next_action"] = "wait"
        return state


async def _propose_opportunities(
    state: AgentState, step: str, revision: bool = False
) -> AgentState:
    """Generate opportunity recommendations via LLM."""
    data_understanding = state.get("data_understanding_summary", {})
    profiles = state.get("column_profiles", [])

    feedback = ""
    if revision:
        feedback = get_proposal_feedback(state, step)

    # Extract key columns for the prompt
    key_cols = []
    for p in profiles[:30]:
        key_cols.append({
            "name": p.get("column_name", ""),
            "type": p.get("data_type", ""),
            "null_pct": p.get("null_pct", 0),
            "unique_count": p.get("unique_count", 0),
        })

    try:
        from app.agent.llm import invoke_llm_json

        prompt = OPPORTUNITY_ANALYSIS_PROMPT.format(
            company_name=state.get("company_name", "Unknown"),
            industry=state.get("industry", "Unknown"),
            business_context=state.get("business_context", "Not provided"),
            data_understanding=json.dumps(data_understanding, indent=2, default=str),
            key_columns=json.dumps(key_cols, indent=2, default=str),
            feedback=feedback or "None",
        )

        result: dict[str, Any] = await invoke_llm_json(
            [
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": "Propose value creation opportunities. Respond with JSON.",
                },
            ],
            schema_hint='{"options": [...], "overall_assessment": "..."}',
        )

        options = result.get("options", [])
        overall = result.get("overall_assessment", "")

        state["opportunity_recommendations"] = options

        emit_trace(state, "TOOL_RESULT", step, {
            "message": f"Generated {len(options)} value creation recommendations",
            "options_count": len(options),
        })

        plan = {
            "options": options,
            "overall_assessment": overall,
        }

        summary = (
            f"{len(options)} value creation opportunities identified. "
            f"Select one to guide the analysis pipeline."
        )

        return set_business_proposal(
            state,
            step,
            "opportunity_analysis",
            plan,
            summary,
            overall,
            alternatives=[],  # Options are in plan.options, not alternatives
        )

    except Exception as e:
        logger.error("opportunity_analysis: LLM failed", error=str(e))

        # Fallback: propose generic analysis directions
        fallback_options = _fallback_opportunities(state)
        state["opportunity_recommendations"] = fallback_options

        plan = {
            "options": fallback_options,
            "overall_assessment": "LLM unavailable; generic opportunities proposed.",
        }

        return set_business_proposal(
            state,
            step,
            "opportunity_analysis",
            plan,
            "Select an analysis direction (LLM-generated recommendations unavailable)",
            "Fallback generic opportunities based on available data.",
        )


async def _execute_selection(state: AgentState, step: str) -> AgentState:
    """Process the user's selection."""
    selected = state.get("selected_opportunity", {})
    plan = state.get("pending_proposal_plan", {})

    if not selected and plan:
        # Try to get from plan
        selected_idx = plan.get("selected_index", 0)
        options = plan.get("options", [])
        if options and selected_idx < len(options):
            selected = options[selected_idx]
            state["selected_opportunity"] = selected

    if selected:
        emit_trace(state, "INFO", step, {
            "message": f"Selected opportunity: {selected.get('title', 'Unknown')}",
            "selected": selected,
        })

        # Update session memory
        try:
            from session_doc.server import upsert
            session_id = str(state.get("session_id", ""))
            memory = (
                f"Selected: **{selected.get('title', '')}**\n"
                f"Use case: {selected.get('use_case', '')}\n"
                f"Description: {selected.get('description', '')}\n"
                f"Potential target: {selected.get('potential_target', '')}\n"
                f"Business impact: {selected.get('business_impact', '')}"
            )
            upsert(session_id, "Value Creation Analysis", memory)
        except Exception:
            pass

    clear_business_proposal(state)
    mark_step_done(state, step)
    state["next_action"] = "orchestrator"
    return state


def _fallback_opportunities(state: AgentState) -> list[dict[str, Any]]:
    """Generate generic opportunity options without LLM."""
    profiles = state.get("column_profiles", [])

    # Look for common target-like columns
    options: list[dict[str, Any]] = []

    col_names = [p.get("column_name", "").lower() for p in profiles]

    if any("churn" in c for c in col_names):
        options.append({
            "title": "Customer Churn Prediction",
            "description": "Predict which customers are likely to churn.",
            "use_case": "churn",
            "feasibility": 0.8,
            "confidence": 0.7,
            "data_requirements": [],
            "potential_target": next(
                (p.get("column_name", "") for p in profiles
                 if "churn" in p.get("column_name", "").lower()),
                "",
            ),
            "business_impact": "Reduce customer attrition",
            "risks": ["May need more behavioral data"],
        })

    if any("revenue" in c or "spend" in c or "amount" in c for c in col_names):
        options.append({
            "title": "Revenue Expansion Analysis",
            "description": "Identify drivers of revenue growth.",
            "use_case": "expansion",
            "feasibility": 0.7,
            "confidence": 0.6,
            "data_requirements": [],
            "potential_target": "",
            "business_impact": "Increase revenue per customer",
            "risks": ["May require target derivation"],
        })

    if not options:
        options.append({
            "title": "General Predictive Analysis",
            "description": "Explore predictive patterns in the data.",
            "use_case": "other",
            "feasibility": 0.6,
            "confidence": 0.5,
            "data_requirements": [],
            "potential_target": "",
            "business_impact": "Data-driven insights",
            "risks": ["Target column needs identification"],
        })

    return options
