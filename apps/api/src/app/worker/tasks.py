from __future__ import annotations

import uuid

import structlog

from app.database import async_session
from app.services.agent_service import AgentService
from app.services.event_service import EventService

logger = structlog.get_logger()


async def run_step(ctx: dict, session_id: str, step: str) -> dict:
    """Arq task that runs an agent step for a session."""
    logger.info("worker.run_step", session_id=session_id, step=step)

    async with async_session() as db:
        event_service = EventService()
        agent_service = AgentService(db=db, event_service=event_service)
        result = await agent_service.run_step(uuid.UUID(session_id), step)

    return result


async def resume_step(
    ctx: dict, session_id: str, proposal_id: str | None = None
) -> dict:
    """Arq task that resumes pipeline after approval/denial."""
    logger.info(
        "worker.resume_step",
        session_id=session_id,
        proposal_id=proposal_id,
    )

    async with async_session() as db:
        event_service = EventService()
        agent_service = AgentService(db=db, event_service=event_service)
        result = await agent_service.resume(
            uuid.UUID(session_id), proposal_id=proposal_id
        )

    return result


async def rerun_from_step(ctx: dict, session_id: str, step: str) -> dict:
    """Arq task that reruns the pipeline from a specific step."""
    logger.info("worker.rerun_from_step", session_id=session_id, step=step)

    async with async_session() as db:
        event_service = EventService()
        agent_service = AgentService(db=db, event_service=event_service)
        result = await agent_service.run_step(uuid.UUID(session_id), step)

    return result
