"""Code registry — stores and retrieves code snippets for analysis sessions.

Uses file-based JSON storage as a placeholder until DB integration.
"""

from __future__ import annotations

import json
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------

_STORE_DIR = Path(tempfile.gettempdir()) / "vc_engine_code_registry"


def _store_path(session_id: str) -> Path:
    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", session_id)
    return _STORE_DIR / f"{safe_id}.json"


def _load_entries(session_id: str) -> list[dict[str, Any]]:
    path = _store_path(session_id)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return []


def _save_entries(session_id: str, entries: list[dict[str, Any]]) -> None:
    _STORE_DIR.mkdir(parents=True, exist_ok=True)
    _store_path(session_id).write_text(
        json.dumps(entries, indent=2), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class CodeEntry(BaseModel):
    id: str
    session_id: str
    step: str
    code: str
    language: str = "python"
    created_at: str


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def store(
    session_id: str,
    step: str,
    code: str,
    language: str = "python",
) -> CodeEntry:
    """Store a code snippet with metadata."""
    entries = _load_entries(session_id)
    entry = CodeEntry(
        id=uuid.uuid4().hex[:12],
        session_id=session_id,
        step=step,
        code=code,
        language=language,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    entries.append(entry.model_dump())
    _save_entries(session_id, entries)
    return entry


def retrieve(
    session_id: str,
    step: str | None = None,
) -> list[CodeEntry]:
    """Get code entries for a session, optionally filtered by step."""
    entries = _load_entries(session_id)
    if step is not None:
        entries = [e for e in entries if e["step"] == step]
    return [CodeEntry(**e) for e in entries]


def get_latest(session_id: str) -> CodeEntry | None:
    """Get the most recent code entry for a session."""
    entries = _load_entries(session_id)
    if not entries:
        return None
    return CodeEntry(**entries[-1])
