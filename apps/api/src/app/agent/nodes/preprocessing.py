from __future__ import annotations

import structlog

from app.agent.state import AgentState

logger = structlog.get_logger()


async def preprocessing_node(state: AgentState) -> AgentState:
    logger.info("preprocessing_node: executing", session_id=str(state.get("session_id")))
    state["current_step"] = "preprocessing"
    return state
