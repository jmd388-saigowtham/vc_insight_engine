from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db_session, get_event_service
from app.models.code_proposal import CodeProposal
from app.schemas.code import CodeApprovalRequest, CodeProposalResponse
from app.schemas.event import TraceEventCreate
from app.services.event_service import EventService

router = APIRouter()


@router.get("/sessions/{session_id}/code/pending", response_model=CodeProposalResponse | None)
async def get_pending_proposal(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> CodeProposalResponse | None:
    stmt = (
        select(CodeProposal)
        .where(CodeProposal.session_id == session_id, CodeProposal.status == "pending")
        .order_by(CodeProposal.created_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    proposal = result.scalar_one_or_none()
    if proposal is None:
        return None
    return CodeProposalResponse.model_validate(proposal)


@router.post("/code/{proposal_id}/approve", response_model=CodeProposalResponse)
async def approve_proposal(
    proposal_id: uuid.UUID,
    data: CodeApprovalRequest | None = None,
    db: AsyncSession = Depends(get_db_session),
    event_service: EventService = Depends(get_event_service),
) -> CodeProposalResponse:
    proposal = await db.get(CodeProposal, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Code proposal not found")
    if proposal.status != "pending":
        raise HTTPException(status_code=409, detail=f"Proposal already {proposal.status}")

    proposal.status = "approved"
    proposal.resolved_at = datetime.now(timezone.utc)

    # Persist user-edited code if provided
    edited = False
    if data and data.code and data.code != proposal.code:
        proposal.code = data.code
        edited = True

    await db.commit()
    await db.refresh(proposal)

    # Emit CODE_EDITED event if code was changed, then CODE_APPROVED
    try:
        if edited:
            await event_service.emit(
                db,
                proposal.session_id,
                TraceEventCreate(
                    event_type="CODE_EDITED",
                    step=proposal.step,
                    payload={"proposal_id": str(proposal.id)},
                ),
            )
        await event_service.emit(
            db,
            proposal.session_id,
            TraceEventCreate(
                event_type="CODE_APPROVED",
                step=proposal.step,
                payload={"proposal_id": str(proposal.id), "edited": edited},
            ),
        )
    except Exception:
        pass

    return CodeProposalResponse.model_validate(proposal)


@router.post("/code/{proposal_id}/deny", response_model=CodeProposalResponse)
async def deny_proposal(
    proposal_id: uuid.UUID,
    data: CodeApprovalRequest | None = None,
    db: AsyncSession = Depends(get_db_session),
    event_service: EventService = Depends(get_event_service),
) -> CodeProposalResponse:
    proposal = await db.get(CodeProposal, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Code proposal not found")
    if proposal.status != "pending":
        raise HTTPException(status_code=409, detail=f"Proposal already {proposal.status}")

    proposal.status = "denied"
    proposal.resolved_at = datetime.now(timezone.utc)
    if data and data.feedback:
        proposal.result_stderr = data.feedback
    await db.commit()
    await db.refresh(proposal)

    # Emit CODE_DENIED event
    try:
        await event_service.emit(
            db,
            proposal.session_id,
            TraceEventCreate(
                event_type="CODE_DENIED",
                step=proposal.step,
                payload={
                    "proposal_id": str(proposal.id),
                    "feedback": data.feedback if data else "",
                },
            ),
        )
    except Exception:
        pass

    return CodeProposalResponse.model_validate(proposal)
