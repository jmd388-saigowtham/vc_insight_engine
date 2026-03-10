from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import Session
from app.schemas.session import SessionCreate, SessionUpdate

import structlog

logger = structlog.get_logger()

STEP_ORDER = [
    "onboarding", "upload", "profiling", "workspace", "target",
    "feature-selection", "eda", "hypotheses", "hypothesis-results",
    "models", "shap", "report",
]

# Steps that don't need proposal/artifact validation to advance
NON_PIPELINE_STEPS = {"onboarding", "upload", "profiling"}


class SessionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, data: SessionCreate) -> Session:
        session = Session(
            id=uuid.uuid4(),
            company_name=data.company_name,
            industry=data.industry,
            business_context=data.business_context,
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def get(self, session_id: uuid.UUID) -> Session | None:
        return await self.db.get(Session, session_id)

    async def list_all(self, limit: int = 50, offset: int = 0) -> list[Session]:
        stmt = (
            select(Session)
            .order_by(Session.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def update(self, session_id: uuid.UUID, data: SessionUpdate) -> Session | None:
        session = await self.get(session_id)
        if session is None:
            return None
        update_data = data.model_dump(exclude_unset=True)

        # Validate current_step advancement for proposal-gated steps
        new_step = update_data.get("current_step")
        if new_step and session.current_step:
            current_idx = STEP_ORDER.index(session.current_step) if session.current_step in STEP_ORDER else -1
            new_idx = STEP_ORDER.index(new_step) if new_step in STEP_ORDER else -1
            completing_step = session.current_step

            if new_idx > current_idx and completing_step not in NON_PIPELINE_STEPS:
                try:
                    from app.services.step_state_service import StepStateService
                    svc = StepStateService(self.db)
                    is_valid = await svc.validate_completion(session_id, completing_step)
                    if not is_valid:
                        logger.warning(
                            "session_service.update: blocked step advancement — no completion evidence",
                            session_id=str(session_id),
                            from_step=completing_step,
                            to_step=new_step,
                        )
                        # Remove current_step from update — still apply other fields
                        update_data.pop("current_step", None)
                except Exception as e:
                    logger.warning("session_service.update: validate_completion failed", error=str(e))

        for key, value in update_data.items():
            setattr(session, key, value)
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def update_business_context(
        self, session_id: uuid.UUID, business_context: str
    ) -> Session | None:
        session = await self.get(session_id)
        if session is None:
            return None
        session.business_context = business_context
        await self.db.commit()
        await self.db.refresh(session)
        return session
