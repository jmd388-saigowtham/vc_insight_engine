from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import engine
from app.dependencies import get_db_session
from app.middleware.rate_limit import RateLimitMiddleware
from app.routers import (
    artifacts,
    code,
    events,
    health,
    pipeline,
    profiling,
    proposals,
    sessions,
    uploads,
)
from app.services.cleanup_service import cleanup_old_files


def configure_logging() -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping().get(settings.log_level, logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    upload_path = Path(settings.upload_dir)
    upload_path.mkdir(parents=True, exist_ok=True)

    # Configure session_doc to use persistent storage under upload_dir
    try:
        from session_doc.server import configure_storage
        configure_storage(settings.upload_dir)
    except ImportError:
        pass

    yield
    await engine.dispose()


app = FastAPI(
    title="VC Insight Engine API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RateLimitMiddleware)

app.include_router(health.router, tags=["health"])
app.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
app.include_router(uploads.router, tags=["uploads"])
app.include_router(profiling.router, tags=["profiling"])
app.include_router(events.router, tags=["events"])
app.include_router(code.router, tags=["code"])
app.include_router(artifacts.router, tags=["artifacts"])
app.include_router(pipeline.router, tags=["pipeline"])
app.include_router(proposals.router, tags=["proposals"])


@app.post("/admin/cleanup", tags=["admin"])
async def admin_cleanup(
    max_age_days: int = 30,
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, int]:
    """Delete uploaded files older than max_age_days for completed sessions."""
    return await cleanup_old_files(db, max_age_days=max_age_days)
