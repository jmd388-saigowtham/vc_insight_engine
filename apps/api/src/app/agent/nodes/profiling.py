from __future__ import annotations

import structlog

from app.agent.nodes.approval_helpers import mark_step_done
from app.agent.nodes.node_helpers import emit_trace, read_step_context
from app.agent.state import AgentState
from app.config import settings

logger = structlog.get_logger()


async def profiling_node(state: AgentState) -> AgentState:
    """Profile each uploaded file using the data_ingest MCP server."""
    logger.info("profiling_node: executing", session_id=str(state.get("session_id")))
    state["current_step"] = "profiling"

    # Read session doc context before acting
    read_step_context(state, "profiling")

    uploaded_files = state.get("uploaded_files", [])
    if not uploaded_files:
        logger.warning("profiling_node: no uploaded files found")
        state["error"] = "No files to profile"
        return state

    try:
        from data_ingest.server import ProfileInput, profile

        all_profiles: list[dict] = []

        for file_info in uploaded_files:
            file_path = file_info.get("storage_path") or file_info.get("file_path", "")
            if not file_path:
                logger.warning("profiling_node: missing path", file_info=file_info)
                continue

            # Resolve relative paths against upload_dir
            from pathlib import Path

            p = Path(file_path)
            if not p.is_absolute():
                p = Path(settings.upload_dir) / file_path
            file_path = str(p)

            logger.info("profiling_node: profiling file", file_path=file_path)

            emit_trace(state, "TOOL_CALL", "profiling", {
                "tool": "data_ingest.profile",
                "file_path": file_path,
                "sample_size": 100_000,
            })

            result = profile(ProfileInput(file_path=file_path, sample_size=100_000))

            file_profiles = []
            for col_profile in result.columns:
                profile_dict = col_profile.model_dump()
                profile_dict["file_path"] = file_path
                profile_dict["file_id"] = file_info.get("id", "")
                file_profiles.append(profile_dict)

            all_profiles.extend(file_profiles)

            emit_trace(state, "TOOL_RESULT", "profiling", {
                "columns": len(result.columns),
                "rows": result.row_count,
                "file_path": file_path,
            })

            logger.info(
                "profiling_node: profiled file",
                file_path=file_path,
                columns=len(result.columns),
                rows=result.row_count,
            )

        state["column_profiles"] = all_profiles
        logger.info(
            "profiling_node: completed",
            total_profiles=len(all_profiles),
        )

        # Update session doc with structured data
        try:
            from session_doc.server import upsert
            sid = str(state.get("session_id", ""))
            summary = (
                f"Profiled {len(uploaded_files)} file(s), "
                f"{len(all_profiles)} total columns."
            )
            # Data Inventory
            file_summaries = []
            for fi in uploaded_files:
                file_summaries.append(
                    f"- {fi.get('filename', '?')} ({fi.get('file_type', '?')})"
                    f" — {fi.get('row_count', '?')} rows, {fi.get('column_count', '?')} cols"
                )
            upsert(sid, "Data Inventory", "\n".join(file_summaries) if file_summaries else summary)

            # Column Dictionary
            col_lines = []
            for cp in all_profiles[:60]:
                name = cp.get("column_name", cp.get("name", "?"))
                dtype = cp.get("data_type", cp.get("dtype", "?"))
                null_pct = cp.get("null_percentage", cp.get("null_pct", 0))
                unique = cp.get("unique_count", "?")
                col_lines.append(f"- **{name}** ({dtype}): {null_pct:.1f}% null, {unique} unique")
            upsert(sid, "Column Dictionary", "\n".join(col_lines) if col_lines else summary)
        except Exception as e:
            logger.warning("profiling_node: session_doc upsert failed", error=str(e))

    except Exception as e:
        logger.error("profiling_node: failed", error=str(e))
        state["error"] = str(e)

    mark_step_done(state, "profiling")
    return state
