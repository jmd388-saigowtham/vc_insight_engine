from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import Session
from app.schemas.session import SessionCreate, SessionUpdate


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
