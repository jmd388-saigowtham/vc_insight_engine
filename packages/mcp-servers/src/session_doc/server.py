"""Session context document — stores and retrieves per-session markdown documents.

Uses file-based JSON storage as a placeholder until DB integration.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------

_STORE_DIR = Path(tempfile.gettempdir()) / "vc_engine_sessions"


def _store_path(session_id: str) -> Path:
    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", session_id)
    return _STORE_DIR / f"{safe_id}.json"


def _load(session_id: str) -> dict:
    path = _store_path(session_id)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "session_id": session_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "document": "",
    }


def _save(session_id: str, data: dict) -> None:
    _STORE_DIR.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    _store_path(session_id).write_text(
        json.dumps(data, indent=2), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class SessionDocOutput(BaseModel):
    session_id: str
    document: str
    created_at: str
    updated_at: str
    sections: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _extract_sections(document: str) -> list[str]:
    """Return a list of H2 section names found in *document*."""
    return re.findall(r"^## (.+)$", document, re.MULTILINE)


def read(session_id: str) -> SessionDocOutput:
    """Read the full session document.  Returns an empty doc if none exists."""
    data = _load(session_id)
    return SessionDocOutput(
        session_id=data["session_id"],
        document=data["document"],
        created_at=data["created_at"],
        updated_at=data["updated_at"],
        sections=_extract_sections(data["document"]),
    )


def upsert(session_id: str, section: str, content: str) -> SessionDocOutput:
    """Insert or replace a ``## Section`` block inside the session document.

    If a section with the given name already exists its content is replaced;
    otherwise the new section is appended at the end.
    """
    data = _load(session_id)
    doc = data["document"]
    header = f"## {section}"

    # Pattern: match from "## Section" to just before the next "## " or end
    pattern = re.compile(
        rf"^{re.escape(header)}\n.*?(?=^## |\Z)",
        re.MULTILINE | re.DOTALL,
    )

    new_block = f"{header}\n{content}\n\n"

    if pattern.search(doc):
        doc = pattern.sub(new_block, doc)
    else:
        if doc and not doc.endswith("\n"):
            doc += "\n"
        doc += new_block

    data["document"] = doc.rstrip("\n") + "\n"
    _save(session_id, data)

    return SessionDocOutput(
        session_id=data["session_id"],
        document=data["document"],
        created_at=data["created_at"],
        updated_at=data["updated_at"],
        sections=_extract_sections(data["document"]),
    )


def get_section(session_id: str, section: str) -> str:
    """Extract and return the content of a specific ``## Section`` block.

    Returns an empty string if the section does not exist.
    """
    data = _load(session_id)
    doc = data["document"]
    header = f"## {section}"

    pattern = re.compile(
        rf"^{re.escape(header)}\n(.*?)(?=^## |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(doc)
    if match:
        return match.group(1).strip()
    return ""
