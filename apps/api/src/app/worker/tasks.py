from __future__ import annotations

import uuid

import structlog

from app.services.agent_service import AgentService

logger = structlog.get_logger()


async def run_step(ctx: dict, session_id: str, step: str) -> dict:
    """Arq task that runs an agent step for a session."""
    logger.info("worker.run_step", session_id=session_id, step=step)
    agent_service = AgentService()
    result = await agent_service.run_step(uuid.UUID(session_id), step)
    return result
