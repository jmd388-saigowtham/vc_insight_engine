"""Code registry — stores and retrieves code snippets for analysis sessions.

Uses file-based JSON storage as a placeholder until DB integration.
Supports provenance tracking: original → revised → user-edited → executed,
with linked stdout/stderr and proposal IDs.
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
    version: int = 1
    proposal_id: str | None = None
    parent_id: str | None = None
    description: str | None = None
    intent: str | None = None
    status: str = "stored"  # stored | approved | executed | failed
    stdout: str | None = None
    stderr: str | None = None
    artifacts_produced: list[str] = Field(default_factory=list)
    created_at: str


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def store(
    session_id: str,
    step: str,
    code: str,
    language: str = "python",
    proposal_id: str | None = None,
    description: str | None = None,
    *,
    parent_id: str | None = None,
    intent: str | None = None,
    status: str = "stored",
    stdout: str | None = None,
    stderr: str | None = None,
    artifacts_produced: list[str] | None = None,
) -> CodeEntry:
    """Store a code snippet with metadata and automatic versioning.

    Parameters
    ----------
    parent_id : str | None
        ID of the previous code entry this one revises (revision chain).
    intent : str | None
        Free-text description of what this code aims to accomplish.
        Used for intent-based search via ``search_by_intent()``.
    status : str
        Lifecycle status: stored, approved, executed, failed.
    stdout / stderr : str | None
        Execution output (populated after sandbox run).
    artifacts_produced : list[str] | None
        Paths to files created by execution.
    """
    entries = _load_entries(session_id)

    # Compute version: max existing version for same (session, step) + 1
    step_versions = [e.get("version", 1) for e in entries if e["step"] == step]
    next_version = max(step_versions, default=0) + 1

    entry = CodeEntry(
        id=uuid.uuid4().hex[:12],
        session_id=session_id,
        step=step,
        code=code,
        language=language,
        version=next_version,
        proposal_id=proposal_id,
        parent_id=parent_id,
        description=description,
        intent=intent,
        status=status,
        stdout=stdout,
        stderr=stderr,
        artifacts_produced=artifacts_produced or [],
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


def get_history(session_id: str, step: str) -> list[CodeEntry]:
    """Get version history for a specific step, ordered by version."""
    entries = _load_entries(session_id)
    step_entries = [e for e in entries if e["step"] == step]
    step_entries.sort(key=lambda e: e.get("version", 1))
    return [CodeEntry(**e) for e in step_entries]


def search_by_intent(session_id: str, query: str) -> list[CodeEntry]:
    """Search for reusable code by intent / purpose / description.

    Performs case-insensitive substring matching against the ``intent``,
    ``description``, and ``step`` fields.  Returns matches ordered by
    most recent first.
    """
    entries = _load_entries(session_id)
    query_lower = query.lower()

    matched: list[dict[str, Any]] = []
    for e in entries:
        searchable = " ".join(
            str(e.get(f, "")) for f in ("intent", "description", "step", "code")
        ).lower()
        if query_lower in searchable:
            matched.append(e)

    # Most recent first
    matched.reverse()
    return [CodeEntry(**e) for e in matched]


def get_provenance_chain(session_id: str, entry_id: str) -> list[CodeEntry]:
    """Follow the parent_id chain to get the full provenance of a code entry.

    Returns the chain from the original (oldest) to the given entry (newest).
    """
    entries = _load_entries(session_id)
    by_id: dict[str, dict[str, Any]] = {e["id"]: e for e in entries}

    chain: list[dict[str, Any]] = []
    current_id: str | None = entry_id
    seen: set[str] = set()

    while current_id and current_id in by_id and current_id not in seen:
        seen.add(current_id)
        entry = by_id[current_id]
        chain.append(entry)
        current_id = entry.get("parent_id")

    chain.reverse()  # oldest first
    return [CodeEntry(**e) for e in chain]


def update_status(
    session_id: str,
    entry_id: str,
    status: str,
    *,
    stdout: str | None = None,
    stderr: str | None = None,
    artifacts_produced: list[str] | None = None,
) -> CodeEntry | None:
    """Update the status and execution results of a code entry."""
    entries = _load_entries(session_id)
    for e in entries:
        if e["id"] == entry_id:
            e["status"] = status
            if stdout is not None:
                e["stdout"] = stdout
            if stderr is not None:
                e["stderr"] = stderr
            if artifacts_produced is not None:
                e["artifacts_produced"] = artifacts_produced
            _save_entries(session_id, entries)
            return CodeEntry(**e)
    return None
