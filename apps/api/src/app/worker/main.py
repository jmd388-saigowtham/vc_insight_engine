from __future__ import annotations

from arq.connections import RedisSettings

from app.config import settings
from app.worker.tasks import rerun_from_step, resume_step, run_step


def _parse_redis_url(url: str) -> RedisSettings:
    """Parse a redis:// URL into arq RedisSettings."""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    return RedisSettings(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        database=int(parsed.path.lstrip("/") or "0"),
        password=parsed.password,
    )


class WorkerSettings:
    functions = [run_step, resume_step, rerun_from_step]
    redis_settings = _parse_redis_url(settings.redis_url)
    max_jobs = 10
    job_timeout = 600
