from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.code_proposal import CodeProposal
from app.models.session import Session


async def _create_session(db: AsyncSession) -> uuid.UUID:
    session_id = uuid.uuid4()
    session = Session(id=session_id, company_name="Code Corp")
    db.add(session)
    await db.commit()
    return session_id


async def _create_proposal(
    db: AsyncSession,
    session_id: uuid.UUID,
    step: str = "eda",
    code: str = "print('hello')",
    status: str = "pending",
) -> CodeProposal:
    proposal = CodeProposal(
        id=uuid.uuid4(),
        session_id=session_id,
        step=step,
        code=code,
        language="python",
        status=status,
    )
    db.add(proposal)
    await db.commit()
    await db.refresh(proposal)
    return proposal


@pytest.mark.asyncio
async def test_get_pending_proposal_none(client: AsyncClient, db_session: AsyncSession) -> None:
    session_id = await _create_session(db_session)

    response = await client.get(f"/sessions/{session_id}/code/pending")
    assert response.status_code == 200
    assert response.json() is None


@pytest.mark.asyncio
async def test_get_pending_proposal(client: AsyncClient, db_session: AsyncSession) -> None:
    session_id = await _create_session(db_session)
    proposal = await _create_proposal(db_session, session_id, "eda", "import pandas as pd")

    response = await client.get(f"/sessions/{session_id}/code/pending")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(proposal.id)
    assert data["step"] == "eda"
    assert data["code"] == "import pandas as pd"
    assert data["status"] == "pending"
    assert data["language"] == "python"


@pytest.mark.asyncio
async def test_get_pending_skips_approved(client: AsyncClient, db_session: AsyncSession) -> None:
    session_id = await _create_session(db_session)
    await _create_proposal(db_session, session_id, "eda", "old code", status="approved")
    pending = await _create_proposal(db_session, session_id, "modeling", "new code")

    response = await client.get(f"/sessions/{session_id}/code/pending")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(pending.id)
    assert data["code"] == "new code"


@pytest.mark.asyncio
async def test_approve_proposal(client: AsyncClient, db_session: AsyncSession) -> None:
    session_id = await _create_session(db_session)
    proposal = await _create_proposal(db_session, session_id)

    response = await client.post(f"/code/{proposal.id}/approve")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "approved"
    assert data["resolved_at"] is not None


@pytest.mark.asyncio
async def test_deny_proposal(client: AsyncClient, db_session: AsyncSession) -> None:
    session_id = await _create_session(db_session)
    proposal = await _create_proposal(db_session, session_id)

    response = await client.post(f"/code/{proposal.id}/deny")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "denied"
    assert data["resolved_at"] is not None


@pytest.mark.asyncio
async def test_deny_proposal_with_feedback(client: AsyncClient, db_session: AsyncSession) -> None:
    session_id = await _create_session(db_session)
    proposal = await _create_proposal(db_session, session_id)

    response = await client.post(
        f"/code/{proposal.id}/deny",
        json={"feedback": "Use a safer approach"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "denied"
    assert data["result_stderr"] == "Use a safer approach"


@pytest.mark.asyncio
async def test_approve_already_approved(client: AsyncClient, db_session: AsyncSession) -> None:
    session_id = await _create_session(db_session)
    proposal = await _create_proposal(db_session, session_id, status="approved")

    response = await client.post(f"/code/{proposal.id}/approve")
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_deny_already_denied(client: AsyncClient, db_session: AsyncSession) -> None:
    session_id = await _create_session(db_session)
    proposal = await _create_proposal(db_session, session_id, status="denied")

    response = await client.post(f"/code/{proposal.id}/deny")
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_approve_not_found(client: AsyncClient) -> None:
    fake_id = uuid.uuid4()
    response = await client.post(f"/code/{fake_id}/approve")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_deny_not_found(client: AsyncClient) -> None:
    fake_id = uuid.uuid4()
    response = await client.post(f"/code/{fake_id}/deny")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_approve_then_deny_fails(client: AsyncClient, db_session: AsyncSession) -> None:
    """Once approved, deny should return 409."""
    session_id = await _create_session(db_session)
    proposal = await _create_proposal(db_session, session_id)

    approve_resp = await client.post(f"/code/{proposal.id}/approve")
    assert approve_resp.status_code == 200

    deny_resp = await client.post(f"/code/{proposal.id}/deny")
    assert deny_resp.status_code == 409


@pytest.mark.asyncio
async def test_proposal_response_fields(client: AsyncClient, db_session: AsyncSession) -> None:
    session_id = await _create_session(db_session)
    proposal = await _create_proposal(db_session, session_id, "preprocessing", "df.dropna()")

    response = await client.get(f"/sessions/{session_id}/code/pending")
    data = response.json()
    assert "id" in data
    assert "session_id" in data
    assert "step" in data
    assert "code" in data
    assert "language" in data
    assert "status" in data
    assert "created_at" in data
    assert data["result_stdout"] is None
    assert data["result_stderr"] is None
    assert data["execution_time"] is None


@pytest.mark.asyncio
async def test_approve_with_edited_code(client: AsyncClient, db_session: AsyncSession) -> None:
    """Approving with edited code should persist the edit."""
    session_id = await _create_session(db_session)
    original_code = "import pandas as pd\ndf = pd.read_csv('data.csv')"
    edited_code = "import pandas as pd\ndf = pd.read_csv('data.csv', nrows=1000)"
    proposal = await _create_proposal(db_session, session_id, "eda", original_code)

    response = await client.post(
        f"/code/{proposal.id}/approve",
        json={"code": edited_code},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "approved"
    assert data["code"] == edited_code


@pytest.mark.asyncio
async def test_approve_without_edited_code_preserves_original(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Approving without sending code should keep the original."""
    session_id = await _create_session(db_session)
    original_code = "print('original')"
    proposal = await _create_proposal(db_session, session_id, "modeling", original_code)

    response = await client.post(f"/code/{proposal.id}/approve")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "approved"
    assert data["code"] == original_code


@pytest.mark.asyncio
async def test_approve_with_same_code_no_edit(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Sending the same code should not count as an edit."""
    session_id = await _create_session(db_session)
    code = "print('same')"
    proposal = await _create_proposal(db_session, session_id, "eda", code)

    response = await client.post(
        f"/code/{proposal.id}/approve",
        json={"code": code},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "approved"
    assert data["code"] == code
