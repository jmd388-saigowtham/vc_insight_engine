from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import Session
from app.schemas.session import SessionCreate, SessionUpdate
from app.services.session_service import STEP_ORDER, SessionService


@pytest.mark.asyncio
async def test_create_session(db_session: AsyncSession) -> None:
    service = SessionService(db_session)
    session = await service.create(SessionCreate(company_name="TestCo", industry="SaaS"))

    assert session.company_name == "TestCo"
    assert session.industry == "SaaS"
    assert session.current_step == "onboarding"
    assert session.status == "active"
    assert session.id is not None


@pytest.mark.asyncio
async def test_get_session(db_session: AsyncSession) -> None:
    service = SessionService(db_session)
    created = await service.create(SessionCreate(company_name="GetCo"))

    fetched = await service.get(created.id)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.company_name == "GetCo"


@pytest.mark.asyncio
async def test_get_session_not_found(db_session: AsyncSession) -> None:
    service = SessionService(db_session)
    result = await service.get(uuid.uuid4())
    assert result is None


@pytest.mark.asyncio
async def test_list_all(db_session: AsyncSession) -> None:
    service = SessionService(db_session)
    await service.create(SessionCreate(company_name="A"))
    await service.create(SessionCreate(company_name="B"))

    sessions = await service.list_all()
    assert len(sessions) >= 2


@pytest.mark.asyncio
async def test_list_all_with_limit(db_session: AsyncSession) -> None:
    service = SessionService(db_session)
    for i in range(5):
        await service.create(SessionCreate(company_name=f"Co{i}"))

    sessions = await service.list_all(limit=3)
    assert len(sessions) == 3


@pytest.mark.asyncio
async def test_update_session_name(db_session: AsyncSession) -> None:
    service = SessionService(db_session)
    created = await service.create(SessionCreate(company_name="OldName"))

    updated = await service.update(created.id, SessionUpdate(company_name="NewName"))
    assert updated is not None
    assert updated.company_name == "NewName"


@pytest.mark.asyncio
async def test_update_session_not_found(db_session: AsyncSession) -> None:
    service = SessionService(db_session)
    result = await service.update(uuid.uuid4(), SessionUpdate(company_name="X"))
    assert result is None


@pytest.mark.asyncio
async def test_step_forward_allowed(db_session: AsyncSession) -> None:
    """Advancing from onboarding to upload should succeed."""
    service = SessionService(db_session)
    session = await service.create(SessionCreate(company_name="StepCo"))
    assert session.current_step == "onboarding"

    updated = await service.update(session.id, SessionUpdate(current_step="upload"))
    assert updated is not None
    assert updated.current_step == "upload"


@pytest.mark.asyncio
async def test_step_regression_now_allowed(db_session: AsyncSession) -> None:
    """Going backwards is now allowed (regression guard removed for go-back-and-edit)."""
    service = SessionService(db_session)
    session = await service.create(SessionCreate(company_name="RegressCo"))

    # Advance to upload
    await service.update(session.id, SessionUpdate(current_step="upload"))

    # Go back to onboarding — should now succeed
    updated = await service.update(session.id, SessionUpdate(current_step="onboarding"))
    assert updated is not None
    assert updated.current_step == "onboarding"


@pytest.mark.asyncio
async def test_step_same_step_allowed(db_session: AsyncSession) -> None:
    """Setting the same step is allowed (regression guard removed)."""
    service = SessionService(db_session)
    session = await service.create(SessionCreate(company_name="SameCo"))

    await service.update(session.id, SessionUpdate(current_step="profiling"))

    updated = await service.update(session.id, SessionUpdate(current_step="profiling"))
    assert updated is not None
    assert updated.current_step == "profiling"


@pytest.mark.asyncio
async def test_step_multi_advance(db_session: AsyncSession) -> None:
    """Advancing multiple steps forward should work."""
    service = SessionService(db_session)
    session = await service.create(SessionCreate(company_name="MultiCo"))

    # Jump from onboarding to eda (skip upload, profiling, workspace, target)
    updated = await service.update(session.id, SessionUpdate(current_step="eda"))
    assert updated is not None
    assert updated.current_step == "eda"


@pytest.mark.asyncio
async def test_step_change_with_other_fields(db_session: AsyncSession) -> None:
    """Step change and other field updates work together."""
    service = SessionService(db_session)
    session = await service.create(SessionCreate(company_name="MixCo"))

    await service.update(session.id, SessionUpdate(current_step="profiling"))

    # Change step AND company name
    updated = await service.update(
        session.id,
        SessionUpdate(current_step="onboarding", company_name="UpdatedName"),
    )
    assert updated is not None
    assert updated.current_step == "onboarding"  # regression now allowed
    assert updated.company_name == "UpdatedName"


@pytest.mark.asyncio
async def test_update_business_context(db_session: AsyncSession) -> None:
    service = SessionService(db_session)
    session = await service.create(SessionCreate(company_name="CtxCo"))

    updated = await service.update_business_context(session.id, "B2B SaaS analytics")
    assert updated is not None
    assert updated.business_context == "B2B SaaS analytics"


@pytest.mark.asyncio
async def test_update_business_context_not_found(db_session: AsyncSession) -> None:
    service = SessionService(db_session)
    result = await service.update_business_context(uuid.uuid4(), "context")
    assert result is None


@pytest.mark.asyncio
async def test_step_order_is_valid() -> None:
    """Verify STEP_ORDER has all 12 expected steps (including feature-selection)."""
    assert len(STEP_ORDER) == 12
    assert STEP_ORDER[0] == "onboarding"
    assert STEP_ORDER[-1] == "report"
    assert "upload" in STEP_ORDER
    assert "profiling" in STEP_ORDER
    assert "feature-selection" in STEP_ORDER
    assert "eda" in STEP_ORDER
    assert "models" in STEP_ORDER
    assert "shap" in STEP_ORDER
