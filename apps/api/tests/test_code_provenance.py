"""Tests for code provenance — revision chain, reuse search, execution tracking.

Proves:
- Code entries have parent_id linking to originals
- get_provenance_chain follows chain oldest-to-newest
- search_by_intent finds matching code
- update_status records execution results
- Artifacts linked to code entries
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure MCP servers package is importable
_project_root = Path(__file__).resolve().parents[3]
_mcp_src = str(_project_root / "packages" / "mcp-servers" / "src")
if _mcp_src not in sys.path:
    sys.path.insert(0, _mcp_src)


class TestCodeProvenanceChain:
    """Test code revision chain via parent_id."""

    def test_store_creates_entry_with_no_parent(self):
        from code_registry.server import store

        entry = store(
            session_id="prov-chain-1",
            step="preprocessing",
            code="# original code",
            intent="Handle missing values",
        )
        assert entry.parent_id is None
        assert entry.intent == "Handle missing values"

    def test_store_revision_links_to_parent(self):
        from code_registry.server import store

        v1 = store(
            session_id="prov-chain-2",
            step="eda",
            code="# v1",
            intent="Generate scatter plot",
        )
        v2 = store(
            session_id="prov-chain-2",
            step="eda",
            code="# v2 revised",
            intent="Generate scatter plot (revised)",
            parent_id=v1.id,
        )
        assert v2.parent_id == v1.id

    def test_full_provenance_chain(self):
        from code_registry.server import get_provenance_chain, store

        v1 = store(
            session_id="prov-chain-3",
            step="modeling",
            code="# train v1",
            intent="Train random forest",
        )
        v2 = store(
            session_id="prov-chain-3",
            step="modeling",
            code="# train v2",
            intent="Train random forest (tuned)",
            parent_id=v1.id,
        )
        v3 = store(
            session_id="prov-chain-3",
            step="modeling",
            code="# train v3",
            intent="Train random forest (final)",
            parent_id=v2.id,
        )

        chain = get_provenance_chain("prov-chain-3", v3.id)
        assert len(chain) == 3
        assert chain[0].id == v1.id  # oldest first
        assert chain[1].id == v2.id
        assert chain[2].id == v3.id

    def test_provenance_chain_single_entry(self):
        from code_registry.server import get_provenance_chain, store

        entry = store(
            session_id="prov-chain-4",
            step="eda",
            code="# single entry",
        )
        chain = get_provenance_chain("prov-chain-4", entry.id)
        assert len(chain) == 1
        assert chain[0].id == entry.id


class TestCodeReuse:
    """Test code reuse search by intent."""

    def test_search_by_intent_finds_match(self):
        from code_registry.server import search_by_intent, store

        store(
            session_id="reuse-1",
            step="preprocessing",
            code="df.fillna(df.median())",
            intent="Impute missing values with median",
        )
        store(
            session_id="reuse-1",
            step="modeling",
            code="RandomForestClassifier()",
            intent="Train random forest classifier",
        )

        results = search_by_intent("reuse-1", "missing values")
        assert len(results) >= 1
        assert any("missing" in (r.intent or "").lower() for r in results)

    def test_search_by_intent_no_match(self):
        from code_registry.server import search_by_intent, store

        store(
            session_id="reuse-2",
            step="eda",
            code="# histogram",
            intent="Generate histogram plot",
        )

        results = search_by_intent("reuse-2", "neural network training")
        # Should either be empty or not match "neural network"
        matching = [r for r in results if "neural" in (r.intent or "").lower()]
        assert len(matching) == 0

    def test_search_by_intent_case_insensitive(self):
        from code_registry.server import search_by_intent, store

        store(
            session_id="reuse-3",
            step="feature_eng",
            code="# polynomial features",
            intent="Create Polynomial Features",
        )

        results = search_by_intent("reuse-3", "polynomial")
        assert len(results) >= 1


class TestExecutionTracking:
    """Test execution result tracking via update_status."""

    def test_update_status_records_execution(self):
        from code_registry.server import store, update_status

        entry = store(
            session_id="exec-1",
            step="eda",
            code="# generate plot",
            status="approved",
        )

        updated = update_status(
            session_id="exec-1",
            entry_id=entry.id,
            status="executed",
            stdout="Plot saved to /artifacts/plot.png",
            artifacts_produced=["/artifacts/plot.png"],
        )

        assert updated is not None
        assert updated.status == "executed"
        assert "Plot saved" in (updated.stdout or "")
        assert "/artifacts/plot.png" in updated.artifacts_produced

    def test_update_status_records_failure(self):
        from code_registry.server import store, update_status

        entry = store(
            session_id="exec-2",
            step="modeling",
            code="# train model",
            status="approved",
        )

        updated = update_status(
            session_id="exec-2",
            entry_id=entry.id,
            status="failed",
            stderr="ModuleNotFoundError: xgboost",
        )

        assert updated is not None
        assert updated.status == "failed"
        assert "ModuleNotFoundError" in (updated.stderr or "")

    def test_update_status_nonexistent_entry(self):
        from code_registry.server import update_status

        result = update_status(
            session_id="exec-3",
            entry_id="nonexistent-id",
            status="executed",
        )
        assert result is None


class TestCodeEntryFields:
    """Test that code entries preserve all provenance fields."""

    def test_store_with_all_provenance_fields(self):
        from code_registry.server import store

        entry = store(
            session_id="fields-1",
            step="preprocessing",
            code="import pandas",
            intent="Load and clean data",
            status="stored",
        )
        assert entry.session_id == "fields-1"
        assert entry.step == "preprocessing"
        assert entry.code == "import pandas"
        assert entry.intent == "Load and clean data"
        assert entry.status == "stored"
        assert entry.parent_id is None
        assert entry.created_at is not None

    def test_store_with_artifacts(self):
        from code_registry.server import retrieve, store

        store(
            session_id="fields-2",
            step="explainability",
            code="# SHAP analysis",
            status="executed",
            stdout="SHAP summary plot saved",
            artifacts_produced=["/shap/summary.png", "/shap/waterfall.png"],
        )

        entries = retrieve("fields-2", step="explainability")
        assert len(entries) >= 1
        assert len(entries[0].artifacts_produced) == 2
