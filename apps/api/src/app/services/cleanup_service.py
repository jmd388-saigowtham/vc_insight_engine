from __future__ import annotations

import datetime
from pathlib import Path

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import Session
from app.models.uploaded_file import UploadedFile

logger = structlog.get_logger()


async def cleanup_old_files(db: AsyncSession, max_age_days: int = 30) -> dict[str, int]:
    """Delete uploaded files older than max_age_days for completed sessions.

    Returns a summary with counts of deleted files and sessions cleaned.
    """
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=max_age_days)

    # Find completed sessions older than the cutoff
    stmt = (
        select(Session)
        .where(Session.status == "completed")
        .where(Session.created_at < cutoff)
    )
    result = await db.execute(stmt)
    sessions = list(result.scalars().all())

    files_deleted = 0
    sessions_cleaned = 0

    for session in sessions:
        file_stmt = select(UploadedFile).where(UploadedFile.session_id == session.id)
        file_result = await db.execute(file_stmt)
        files = list(file_result.scalars().all())

        if not files:
            continue

        for f in files:
            # Delete from disk
            path = Path(f.storage_path)
            if path.exists():
                try:
                    path.unlink()
                    files_deleted += 1
                except OSError:
                    logger.warning("failed_to_delete_file", path=str(path))

            await db.delete(f)

        sessions_cleaned += 1

    await db.commit()

    logger.info(
        "cleanup_completed",
        sessions_cleaned=sessions_cleaned,
        files_deleted=files_deleted,
    )

    return {
        "sessions_cleaned": sessions_cleaned,
        "files_deleted": files_deleted,
    }
