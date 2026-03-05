from __future__ import annotations

import uuid

import structlog

logger = structlog.get_logger()


class AgentService:
    async def run_step(self, session_id: uuid.UUID, step: str) -> dict:
        """Enqueue a step execution to the Arq worker."""
        logger.info("agent_service.run_step", session_id=str(session_id), step=step)
        return {"session_id": str(session_id), "step": step, "status": "queued"}

    async def get_status(self, session_id: uuid.UUID) -> dict:
        """Get the current agent state for a session."""
        logger.info("agent_service.get_status", session_id=str(session_id))
        return {"session_id": str(session_id), "status": "idle"}
