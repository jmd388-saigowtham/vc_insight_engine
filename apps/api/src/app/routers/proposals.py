"""Router for business-logic proposals and user feedback.

Proposals represent plan-level decisions (merge strategy, target selection,
feature set, etc.) that require user approval before execution.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db_session, get_event_service
from app.models.proposal import Proposal
from app.models.user_feedback import UserFeedback
from app.schemas.event import TraceEventCreate
from app.schemas.proposal import (
    ProposalResponse,
    ProposalRevisionRequest,
    ProposalSelectionRequest,
    UserFeedbackCreate,
    UserFeedbackResponse,
)
from app.services.event_service import EventService

router = APIRouter()


async def _get_proposal_or_404(
    proposal_id: uuid.UUID, db: AsyncSession
) -> Proposal:
    proposal = await db.get(Proposal, proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return proposal


# ── Proposal endpoints ────────────────────────────────────────────


@router.get(
    "/sessions/{session_id}/proposals",
    response_model=list[ProposalResponse],
)
async def list_proposals(
    session_id: uuid.UUID,
    step: str | None = Query(None),
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db_session),
) -> list[ProposalResponse]:
    """List proposals for a session, optionally filtered by step/status."""
    stmt = (
        select(Proposal)
        .where(Proposal.session_id == session_id)
        .order_by(Proposal.created_at.desc())
    )
    if step:
        stmt = stmt.where(Proposal.step == step)
    if status:
        stmt = stmt.where(Proposal.status == status)
    result = await db.execute(stmt)
    return [ProposalResponse.model_validate(p) for p in result.scalars().all()]


@router.get(
    "/sessions/{session_id}/proposals/pending",
    response_model=list[ProposalResponse],
)
async def list_pending_proposals(
    session_id: uuid.UUID,
    step: str | None = Query(None),
    db: AsyncSession = Depends(get_db_session),
) -> list[ProposalResponse]:
    """List pending proposals for a session."""
    stmt = (
        select(Proposal)
        .where(Proposal.session_id == session_id)
        .where(Proposal.status == "pending")
        .order_by(Proposal.created_at.desc())
    )
    if step:
        stmt = stmt.where(Proposal.step == step)
    result = await db.execute(stmt)
    return [ProposalResponse.model_validate(p) for p in result.scalars().all()]


@router.get(
    "/proposals/{proposal_id}",
    response_model=ProposalResponse,
)
async def get_proposal(
    proposal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> ProposalResponse:
    """Get a single proposal by ID."""
    proposal = await _get_proposal_or_404(proposal_id, db)
    return ProposalResponse.model_validate(proposal)


@router.get(
    "/proposals/{proposal_id}/history",
    response_model=list[ProposalResponse],
)
async def get_proposal_history(
    proposal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> list[ProposalResponse]:
    """Get the full revision chain for a proposal."""
    proposal = await _get_proposal_or_404(proposal_id, db)

    # Walk up the parent chain
    chain: list[Proposal] = [proposal]
    current = proposal
    while current.parent_id:
        parent = await db.get(Proposal, current.parent_id)
        if not parent:
            break
        chain.append(parent)
        current = parent

    # Walk down: find all versions in the chain
    stmt = (
        select(Proposal)
        .where(Proposal.session_id == proposal.session_id)
        .where(Proposal.step == proposal.step)
        .where(Proposal.proposal_type == proposal.proposal_type)
        .order_by(Proposal.version.asc())
    )
    result = await db.execute(stmt)
    all_versions = list(result.scalars().all())

    return [ProposalResponse.model_validate(p) for p in all_versions]


@router.post(
    "/proposals/{proposal_id}/approve",
    response_model=ProposalResponse,
)
async def approve_proposal(
    proposal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    event_service: EventService = Depends(get_event_service),
) -> ProposalResponse:
    """Approve a pending proposal."""
    proposal = await _get_proposal_or_404(proposal_id, db)
    if proposal.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Proposal is '{proposal.status}', not 'pending'",
        )

    proposal.status = "approved"
    proposal.resolved_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(proposal)

    await event_service.emit(
        db,
        proposal.session_id,
        TraceEventCreate(
            event_type="PROPOSAL_APPROVED",
            step=proposal.step,
            payload={
                "proposal_id": str(proposal.id),
                "proposal_type": proposal.proposal_type,
                "version": proposal.version,
            },
        ),
    )

    return ProposalResponse.model_validate(proposal)


@router.post(
    "/proposals/{proposal_id}/revise",
    response_model=ProposalResponse,
)
async def revise_proposal(
    proposal_id: uuid.UUID,
    body: ProposalRevisionRequest,
    db: AsyncSession = Depends(get_db_session),
    event_service: EventService = Depends(get_event_service),
) -> ProposalResponse:
    """Request revision of a proposal with user feedback."""
    proposal = await _get_proposal_or_404(proposal_id, db)
    if proposal.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Proposal is '{proposal.status}', not 'pending'",
        )

    proposal.status = "revised"
    proposal.user_feedback = body.feedback
    proposal.resolved_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(proposal)

    await event_service.emit(
        db,
        proposal.session_id,
        TraceEventCreate(
            event_type="PROPOSAL_REVISED",
            step=proposal.step,
            payload={
                "proposal_id": str(proposal.id),
                "proposal_type": proposal.proposal_type,
                "version": proposal.version,
                "feedback": body.feedback,
            },
        ),
    )

    return ProposalResponse.model_validate(proposal)


@router.post(
    "/proposals/{proposal_id}/reject",
    response_model=ProposalResponse,
)
async def reject_proposal(
    proposal_id: uuid.UUID,
    body: ProposalRevisionRequest | None = None,
    db: AsyncSession = Depends(get_db_session),
    event_service: EventService = Depends(get_event_service),
) -> ProposalResponse:
    """Reject a proposal. Workflow pauses; AI offers alternatives."""
    proposal = await _get_proposal_or_404(proposal_id, db)
    if proposal.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Proposal is '{proposal.status}', not 'pending'",
        )

    proposal.status = "rejected"
    if body and body.feedback:
        proposal.user_feedback = body.feedback
    proposal.resolved_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(proposal)

    await event_service.emit(
        db,
        proposal.session_id,
        TraceEventCreate(
            event_type="PROPOSAL_REJECTED",
            step=proposal.step,
            payload={
                "proposal_id": str(proposal.id),
                "proposal_type": proposal.proposal_type,
                "version": proposal.version,
                "feedback": body.feedback if body else None,
            },
        ),
    )

    return ProposalResponse.model_validate(proposal)


@router.post(
    "/proposals/{proposal_id}/select",
    response_model=ProposalResponse,
)
async def select_proposal_option(
    proposal_id: uuid.UUID,
    body: ProposalSelectionRequest,
    db: AsyncSession = Depends(get_db_session),
    event_service: EventService = Depends(get_event_service),
) -> ProposalResponse:
    """Select one option from a multi-choice proposal (e.g., opportunity analysis)."""
    proposal = await _get_proposal_or_404(proposal_id, db)
    if proposal.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Proposal is '{proposal.status}', not 'pending'",
        )

    # Validate selected_index against alternatives
    alternatives = proposal.alternatives or []
    plan = dict(proposal.plan or {})
    options = plan.get("options", alternatives)
    if not options or body.selected_index >= len(options):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid selection index {body.selected_index}",
        )

    # Store the selection in a new dict (triggers SQLAlchemy change detection)
    updated_plan = {
        **plan,
        "selected_index": body.selected_index,
        "selected_option": options[body.selected_index],
    }
    proposal.plan = updated_plan
    proposal.status = "approved"
    if body.feedback:
        proposal.user_feedback = body.feedback
    proposal.resolved_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(proposal)

    await event_service.emit(
        db,
        proposal.session_id,
        TraceEventCreate(
            event_type="PROPOSAL_APPROVED",
            step=proposal.step,
            payload={
                "proposal_id": str(proposal.id),
                "proposal_type": proposal.proposal_type,
                "version": proposal.version,
                "selected_index": body.selected_index,
            },
        ),
    )

    return ProposalResponse.model_validate(proposal)


# ── User Feedback endpoints ───────────────────────────────────────


@router.post(
    "/sessions/{session_id}/feedback",
    response_model=UserFeedbackResponse,
    status_code=201,
)
async def submit_feedback(
    session_id: uuid.UUID,
    body: UserFeedbackCreate,
    db: AsyncSession = Depends(get_db_session),
    event_service: EventService = Depends(get_event_service),
) -> UserFeedbackResponse:
    """Submit free-form feedback for the AI agent."""
    feedback = UserFeedback(
        id=uuid.uuid4(),
        session_id=session_id,
        step=body.step,
        message=body.message,
        status="pending",
    )
    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)

    await event_service.emit(
        db,
        session_id,
        TraceEventCreate(
            event_type="USER_FEEDBACK",
            step=body.step,
            payload={"message": body.message, "feedback_id": str(feedback.id)},
        ),
    )

    return UserFeedbackResponse.model_validate(feedback)


@router.get(
    "/sessions/{session_id}/feedback",
    response_model=list[UserFeedbackResponse],
)
async def list_feedback(
    session_id: uuid.UUID,
    step: str | None = Query(None),
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db_session),
) -> list[UserFeedbackResponse]:
    """List user feedback for a session."""
    stmt = (
        select(UserFeedback)
        .where(UserFeedback.session_id == session_id)
        .order_by(UserFeedback.created_at.desc())
    )
    if step:
        stmt = stmt.where(UserFeedback.step == step)
    if status:
        stmt = stmt.where(UserFeedback.status == status)
    result = await db.execute(stmt)
    return [UserFeedbackResponse.model_validate(f) for f in result.scalars().all()]
