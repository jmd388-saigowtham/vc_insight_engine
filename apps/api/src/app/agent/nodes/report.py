from __future__ import annotations

import structlog

from app.agent.state import AgentState

logger = structlog.get_logger()


async def report_node(state: AgentState) -> AgentState:
    logger.info("report_node: executing", session_id=str(state.get("session_id")))
    state["current_step"] = "report"
    return state
