"""Session context document — stores and retrieves per-session markdown documents.

Supports two storage backends:
1. Database storage (via SQLAlchemy, when DB URL is available)
2. File-based JSON storage (fallback for standalone usage)

The canonical format is a human-readable Markdown document.  Each pipeline
stage appends / updates its own ``## Section`` heading.  Structured metadata
(feature lists, model metrics, code paths) can be embedded as fenced code
blocks within a section for programmatic access.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Storage helpers — file-based fallback
# ---------------------------------------------------------------------------

_STORE_DIR = Path(
    os.environ.get("SESSION_DOC_DIR", str(Path(tempfile.gettempdir()) / "vc_engine_sessions"))
)

# Database storage directory override (set by the API when DB is available)
_DB_STORE_DIR: Path | None = None
_USE_DB_FILE = True  # Use persistent file storage by default

# ---------------------------------------------------------------------------
# Mandatory sections (in order) — every session doc should have these
# ---------------------------------------------------------------------------
MANDATORY_SECTIONS: list[str] = [
    "Business Context",
    "Data Inventory",
    "Column Dictionary",
    "Dtype Decisions",
    "Merge Strategy",
    "Value Creation Analysis",
    "Target Variable",
    "Feature Selection",
    "EDA Findings",
    "Preprocessing Decisions",
    "Hypotheses & Results",
    "Feature Engineering",
    "Model Results",
    "Trained Model Paths",
    "Threshold Decisions",
    "Explainability",
    "Recommendations",
    "Report",
    "Generated Code Paths",
    "Revision History",
]


def _store_path(session_id: str) -> Path:
    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", session_id)
    # Use upload_dir-based storage if available, otherwise temp dir
    store_dir = _DB_STORE_DIR or _STORE_DIR
    return store_dir / "session_docs" / f"{safe_id}.json"


def configure_storage(upload_dir: str) -> None:
    """Configure persistent storage directory (called from API startup)."""
    global _DB_STORE_DIR
    _DB_STORE_DIR = Path(upload_dir)


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
    path = _store_path(session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(
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


def initialize(
    session_id: str,
    *,
    company_name: str = "",
    industry: str = "",
    business_context: str = "",
) -> SessionDocOutput:
    """Create a new session document with mandatory section scaffolding.

    Called at session start (before the first pipeline run).
    If a document already exists it is returned unchanged.
    """
    data = _load(session_id)
    if data["document"].strip():
        # Already initialized — return as-is
        return SessionDocOutput(
            session_id=data["session_id"],
            document=data["document"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            sections=_extract_sections(data["document"]),
        )

    # Build initial markdown with business context and empty section stubs
    lines = [f"# Session: {session_id}", ""]
    if company_name:
        lines.append(f"**Company:** {company_name}")
    if industry:
        lines.append(f"**Industry:** {industry}")
    if business_context:
        lines.append(f"**Goal:** {business_context}")
    if company_name or industry or business_context:
        lines.append("")

    for section in MANDATORY_SECTIONS:
        lines.append(f"## {section}")
        if section == "Business Context":
            ctx_parts = []
            if company_name:
                ctx_parts.append(f"Company: {company_name}")
            if industry:
                ctx_parts.append(f"Industry: {industry}")
            if business_context:
                ctx_parts.append(f"Goal: {business_context}")
            lines.append("\n".join(ctx_parts) if ctx_parts else "_Pending_")
        else:
            lines.append("_Pending_")
        lines.append("")

    data["document"] = "\n".join(lines)
    _save(session_id, data)

    return SessionDocOutput(
        session_id=data["session_id"],
        document=data["document"],
        created_at=data["created_at"],
        updated_at=data["updated_at"],
        sections=_extract_sections(data["document"]),
    )


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


def upsert_structured(
    session_id: str,
    section: str,
    narrative: str,
    metadata: dict[str, Any] | None = None,
) -> SessionDocOutput:
    """Upsert a section with both narrative text and optional structured metadata.

    The metadata is embedded as a fenced JSON code block for programmatic access.
    """
    parts = [narrative]
    if metadata:
        parts.append("")
        parts.append("```json")
        parts.append(json.dumps(metadata, indent=2, default=str))
        parts.append("```")
    return upsert(session_id, section, "\n".join(parts))


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


def get_section_metadata(session_id: str, section: str) -> dict[str, Any] | None:
    """Extract the fenced JSON metadata block from a section, if present."""
    content = get_section(session_id, section)
    if not content:
        return None

    pattern = re.compile(r"```json\s*\n(.*?)\n```", re.DOTALL)
    match = pattern.search(content)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None
    return None


def append_to_revision_history(
    session_id: str,
    step: str,
    action: str,
    detail: str = "",
) -> SessionDocOutput:
    """Append an entry to the Revision History section."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    entry = f"- [{timestamp}] **{step}**: {action}"
    if detail:
        entry += f" — {detail}"

    existing = get_section(session_id, "Revision History")
    if existing and existing != "_Pending_":
        new_content = existing + "\n" + entry
    else:
        new_content = entry
    return upsert(session_id, "Revision History", new_content)
