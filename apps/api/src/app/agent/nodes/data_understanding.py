"""Data understanding node — AI-generated summary of data quality, patterns, risks.

This is an EXPLICIT separate node from profiling. It reads profiling results
and generates a structured data understanding summary using the LLM.
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from app.agent.nodes.approval_helpers import mark_step_done
from app.agent.nodes.node_helpers import emit_trace
from app.agent.state import AgentState

logger = structlog.get_logger()

DATA_UNDERSTANDING_PROMPT = """\
You are an AI data scientist analyzing a dataset for a venture capital firm.

## Business Context
- Company: {company_name}
- Industry: {industry}
- Business Goal: {business_context}

## Uploaded Files
{file_summary}

## Column Profiles
{column_profiles}

## Dtype Decisions
{dtype_decisions}

## Instructions
Produce a comprehensive data understanding summary. Analyze:

1. **Table Purpose & Grain**: What entity does each table represent? What is
   the granularity (one row per customer, per transaction, etc.)?
2. **Data Quality Assessment**: Null patterns, outliers, cardinality anomalies,
   data freshness indicators.
3. **Relationships**: If multiple files, how do they relate? Potential join keys.
4. **Candidate Target Columns**: Which columns could serve as prediction targets
   for VC use cases (churn, expansion, cross-sell, upsell)?
5. **Risk Flags**: Potential data leakage, severe class imbalance, insufficient
   data, missing critical features.
6. **Key Patterns**: Notable distributions, correlations, business-relevant
   patterns visible from profiling alone.

Respond with ONLY valid JSON:
{{
  "table_summaries": [
    {{
      "file": "<filename>",
      "entity": "<what each row represents>",
      "row_count": <number>,
      "key_columns": ["<col1>", "<col2>"],
      "quality_score": "<good|fair|poor>"
    }}
  ],
  "data_quality": {{
    "overall_score": "<good|fair|poor>",
    "null_issues": ["<column with high nulls and impact>"],
    "outlier_flags": ["<column with potential outliers>"],
    "cardinality_anomalies": ["<description>"]
  }},
  "candidate_targets": [
    {{
      "column": "<name>",
      "use_case": "<churn|expansion|cross_sell|upsell>",
      "confidence": 0.8,
      "reasoning": "<why this column>"
    }}
  ],
  "risk_flags": ["<risk description>"],
  "key_patterns": ["<pattern description>"],
  "recommendations": "<1-2 sentence summary of recommended approach>"
}}\
"""


async def data_understanding_node(state: AgentState) -> AgentState:
    """Generate AI-driven data understanding summary."""
    step = "data_understanding"
    session_id = str(state.get("session_id", ""))
    logger.info("data_understanding_node: executing", session_id=session_id)

    emit_trace(state, "TOOL_CALL", step, {
        "message": "Generating data understanding summary"
    })

    # Build context from profiling results
    files = state.get("uploaded_files", [])
    profiles = state.get("column_profiles", [])
    dtype_decisions = state.get("dtype_decisions", {})

    file_summary = "\n".join(
        f"- {f.get('filename', 'unknown')} ({f.get('row_count', '?')} rows, "
        f"{f.get('column_count', '?')} columns)"
        for f in files
    ) or "No files uploaded"

    profile_text = json.dumps(profiles[:50], indent=2, default=str)

    try:
        from app.agent.llm import invoke_llm_json

        prompt = DATA_UNDERSTANDING_PROMPT.format(
            company_name=state.get("company_name", "Unknown"),
            industry=state.get("industry", "Unknown"),
            business_context=state.get("business_context", "Not provided"),
            file_summary=file_summary,
            column_profiles=profile_text,
            dtype_decisions=json.dumps(dtype_decisions, default=str),
        )

        summary: dict[str, Any] = await invoke_llm_json(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": "Analyze this data and respond with JSON."},
            ],
            schema_hint='{"table_summaries": [...], "data_quality": {...}, ...}',
        )

        state["data_understanding_summary"] = summary

        emit_trace(state, "TOOL_RESULT", step, {
            "message": "Data understanding summary generated",
            "summary": summary,
        })

        # Update session memory
        try:
            from session_doc.server import upsert_structured
            memory_content = _format_memory(summary)
            upsert_structured(session_id, "Data Understanding", memory_content, metadata={
                "table_count": len(summary.get("table_summaries", [])),
                "overall_quality": summary.get("data_quality", {}).get("overall_score", "unknown"),
                "candidate_targets": [
                    t.get("column") for t in summary.get("candidate_targets", [])
                ],
                "risk_count": len(summary.get("risk_flags", [])),
            })
        except Exception:
            pass

    except Exception as e:
        logger.error("data_understanding_node: LLM call failed", error=str(e))

        # Fallback: generate basic summary from profiles
        summary = _fallback_summary(files, profiles)
        state["data_understanding_summary"] = summary

        emit_trace(state, "INFO", step, {
            "message": f"LLM failed ({e}); using basic data summary",
        })

    mark_step_done(state, step)
    state["next_action"] = "orchestrator"
    return state


def _fallback_summary(
    files: list[dict[str, Any]],
    profiles: list[dict[str, Any]],
) -> dict[str, Any]:
    """Generate a basic summary without LLM."""
    table_summaries = []
    for f in files:
        table_summaries.append({
            "file": f.get("filename", "unknown"),
            "entity": "unknown",
            "row_count": f.get("row_count"),
            "key_columns": [],
            "quality_score": "unknown",
        })

    # Find columns with high nulls
    null_issues = []
    for p in profiles:
        if p.get("null_pct", 0) > 30:
            null_issues.append(
                f"{p.get('column_name', '?')}: {p.get('null_pct', 0):.0f}% nulls"
            )

    return {
        "table_summaries": table_summaries,
        "data_quality": {
            "overall_score": "unknown",
            "null_issues": null_issues,
            "outlier_flags": [],
            "cardinality_anomalies": [],
        },
        "candidate_targets": [],
        "risk_flags": [],
        "key_patterns": [],
        "recommendations": "Manual review recommended — LLM analysis unavailable.",
    }


def _format_memory(summary: dict[str, Any]) -> str:
    """Format data understanding summary for session memory."""
    lines = []

    for ts in summary.get("table_summaries", []):
        lines.append(
            f"- **{ts.get('file', '?')}**: {ts.get('entity', '?')} "
            f"({ts.get('row_count', '?')} rows, quality: {ts.get('quality_score', '?')})"
        )

    dq = summary.get("data_quality", {})
    lines.append(f"\nOverall data quality: {dq.get('overall_score', 'unknown')}")

    if dq.get("null_issues"):
        lines.append("Null issues: " + "; ".join(dq["null_issues"][:5]))

    targets = summary.get("candidate_targets", [])
    if targets:
        lines.append("\nCandidate targets:")
        for t in targets:
            lines.append(
                f"- {t.get('column', '?')} ({t.get('use_case', '?')}, "
                f"confidence: {t.get('confidence', '?')})"
            )

    risks = summary.get("risk_flags", [])
    if risks:
        lines.append("\nRisk flags: " + "; ".join(risks[:5]))

    recs = summary.get("recommendations", "")
    if recs:
        lines.append(f"\nRecommendation: {recs}")

    return "\n".join(lines)
