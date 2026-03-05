from __future__ import annotations

import structlog

from app.agent.state import AgentState

logger = structlog.get_logger()


async def profiling_node(state: AgentState) -> AgentState:
    logger.info("profiling_node: executing", session_id=str(state.get("session_id")))
    state["current_step"] = "profiling"
    return state
