from __future__ import annotations

import structlog

from app.agent.state import AgentState

logger = structlog.get_logger()


async def feature_eng_node(state: AgentState) -> AgentState:
    logger.info("feature_eng_node: executing", session_id=str(state.get("session_id")))
    state["current_step"] = "feature_eng"
    return state
