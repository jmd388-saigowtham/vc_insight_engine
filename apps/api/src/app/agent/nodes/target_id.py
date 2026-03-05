from __future__ import annotations

import structlog

from app.agent.state import AgentState

logger = structlog.get_logger()


async def target_id_node(state: AgentState) -> AgentState:
    logger.info("target_id_node: executing", session_id=str(state.get("session_id")))
    state["current_step"] = "target_id"
    return state
