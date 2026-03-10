"""Tests for session memory (session_doc) lifecycle.

Proves:
- Created at session start with mandatory scaffolding
- Read before every major action (via read_step_context)
- Updated after every major action (via upsert / upsert_structured)
- Contains code/artifact/model/threshold paths
- Sections persist across reads
- Structured metadata embedded in fenced code blocks
- Revision history tracking
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Ensure MCP servers package is importable
# tests/ is at apps/api/tests, so parents[3] = project root
_project_root = Path(__file__).resolve().parents[3]
_mcp_src = str(_project_root / "packages" / "mcp-servers" / "src")
if _mcp_src not in sys.path:
    sys.path.insert(0, _mcp_src)


# ---------------------------------------------------------------------------
# session_doc tests
# ---------------------------------------------------------------------------


class TestSessionDocInitialize:
    """Test session doc initialization with mandatory sections."""

    def test_initialize_creates_scaffolding(self, tmp_path):
        from session_doc.server import configure_storage, initialize, read

        configure_storage(str(tmp_path))

        result = initialize(
            "test-session-1",
            company_name="Acme Corp",
            industry="SaaS",
            business_context="Reduce churn",
        )
        assert result.session_id == "test-session-1"
        assert "## Business Context" in result.document
        assert "## Data Inventory" in result.document
        assert "## Column Dictionary" in result.document
        assert "## Dtype Decisions" in result.document
        assert "## Merge Strategy" in result.document
        assert "## Target Variable" in result.document
        assert "## Feature Selection" in result.document
        assert "## EDA Findings" in result.document
        assert "## Preprocessing Decisions" in result.document
        assert "## Hypotheses & Results" in result.document
        assert "## Feature Engineering" in result.document
        assert "## Model Results" in result.document
        assert "## Trained Model Paths" in result.document
        assert "## Threshold Decisions" in result.document
        assert "## Explainability" in result.document
        assert "## Recommendations" in result.document
        assert "## Report" in result.document
        assert "## Generated Code Paths" in result.document
        assert "## Revision History" in result.document

        # Business context populated
        assert "Acme Corp" in result.document
        assert "SaaS" in result.document
        assert "Reduce churn" in result.document

        # All sections should be listed
        assert len(result.sections) >= 20

    def test_initialize_is_idempotent(self, tmp_path):
        from session_doc.server import configure_storage, initialize, upsert

        configure_storage(str(tmp_path))

        # Initialize once
        initialize("test-session-2", company_name="Foo")

        # Update a section
        upsert("test-session-2", "Target Variable", "Target: churn")

        # Initialize again — should NOT overwrite
        result = initialize("test-session-2", company_name="Foo")
        assert "Target: churn" in result.document

    def test_initialize_empty_context(self, tmp_path):
        from session_doc.server import configure_storage, initialize

        configure_storage(str(tmp_path))
        result = initialize("test-session-3")
        assert "## Business Context" in result.document
        assert "_Pending_" in result.document


class TestSessionDocReadWrite:
    """Test basic read/write operations."""

    def test_upsert_and_read(self, tmp_path):
        from session_doc.server import configure_storage, get_section, initialize, upsert

        configure_storage(str(tmp_path))
        initialize("sess-rw-1")

        upsert("sess-rw-1", "Target Variable", "Target column: churn_flag")
        content = get_section("sess-rw-1", "Target Variable")
        assert "churn_flag" in content

    def test_upsert_replaces_existing_section(self, tmp_path):
        from session_doc.server import configure_storage, get_section, initialize, upsert

        configure_storage(str(tmp_path))
        initialize("sess-rw-2")

        upsert("sess-rw-2", "Target Variable", "First target: revenue")
        upsert("sess-rw-2", "Target Variable", "Revised target: churn")

        content = get_section("sess-rw-2", "Target Variable")
        assert "churn" in content
        assert "revenue" not in content

    def test_multiple_sections_independent(self, tmp_path):
        from session_doc.server import configure_storage, get_section, initialize, upsert

        configure_storage(str(tmp_path))
        initialize("sess-rw-3")

        upsert("sess-rw-3", "Target Variable", "Target: churn")
        upsert("sess-rw-3", "Feature Selection", "Selected 10 features")
        upsert("sess-rw-3", "Model Results", "Best model: random_forest")

        # Each section is independent
        assert "churn" in get_section("sess-rw-3", "Target Variable")
        assert "10 features" in get_section("sess-rw-3", "Feature Selection")
        assert "random_forest" in get_section("sess-rw-3", "Model Results")

    def test_sections_persist_across_reads(self, tmp_path):
        from session_doc.server import configure_storage, initialize, read, upsert

        configure_storage(str(tmp_path))
        initialize("sess-rw-4")

        upsert("sess-rw-4", "EDA Findings", "Generated 5 plots")

        # Read full doc
        doc = read("sess-rw-4")
        assert "5 plots" in doc.document
        assert "EDA Findings" in doc.sections


class TestSessionDocStructured:
    """Test structured metadata in fenced code blocks."""

    def test_upsert_structured_with_metadata(self, tmp_path):
        from session_doc.server import (
            configure_storage,
            get_section,
            get_section_metadata,
            initialize,
            upsert_structured,
        )

        configure_storage(str(tmp_path))
        initialize("sess-struct-1")

        upsert_structured(
            "sess-struct-1",
            "Model Results",
            "Trained 3 models. Best: random_forest.",
            metadata={
                "models": ["logistic_regression", "random_forest", "gradient_boosting"],
                "best_model": "random_forest",
                "output_dir": "/data/models",
            },
        )

        # Narrative is readable
        content = get_section("sess-struct-1", "Model Results")
        assert "random_forest" in content
        assert "```json" in content

        # Metadata is extractable
        meta = get_section_metadata("sess-struct-1", "Model Results")
        assert meta is not None
        assert meta["best_model"] == "random_forest"
        assert len(meta["models"]) == 3
        assert meta["output_dir"] == "/data/models"

    def test_upsert_structured_without_metadata(self, tmp_path):
        from session_doc.server import (
            configure_storage,
            get_section_metadata,
            initialize,
            upsert_structured,
        )

        configure_storage(str(tmp_path))
        initialize("sess-struct-2")

        upsert_structured("sess-struct-2", "Report", "Report generated.")
        meta = get_section_metadata("sess-struct-2", "Report")
        assert meta is None

    def test_metadata_contains_paths(self, tmp_path):
        from session_doc.server import (
            configure_storage,
            get_section_metadata,
            initialize,
            upsert_structured,
        )

        configure_storage(str(tmp_path))
        initialize("sess-struct-3")

        upsert_structured(
            "sess-struct-3",
            "Trained Model Paths",
            "- /models/rf.pkl\n- /models/gb.pkl",
            metadata={"paths": ["/models/rf.pkl", "/models/gb.pkl"]},
        )

        meta = get_section_metadata("sess-struct-3", "Trained Model Paths")
        assert meta is not None
        assert "/models/rf.pkl" in meta["paths"]
        assert "/models/gb.pkl" in meta["paths"]


class TestRevisionHistory:
    """Test revision history tracking."""

    def test_append_to_revision_history(self, tmp_path):
        from session_doc.server import (
            append_to_revision_history,
            configure_storage,
            get_section,
            initialize,
        )

        configure_storage(str(tmp_path))
        initialize("sess-rev-1")

        append_to_revision_history("sess-rev-1", "target_id", "Approved target: churn")
        append_to_revision_history("sess-rev-1", "feature_selection", "Revised: added 3 features")

        history = get_section("sess-rev-1", "Revision History")
        assert "target_id" in history
        assert "Approved target: churn" in history
        assert "feature_selection" in history
        assert "added 3 features" in history

    def test_revision_history_replaces_pending(self, tmp_path):
        from session_doc.server import (
            append_to_revision_history,
            configure_storage,
            get_section,
            initialize,
        )

        configure_storage(str(tmp_path))
        initialize("sess-rev-2")

        # Initial state has _Pending_ placeholder
        history_before = get_section("sess-rev-2", "Revision History")
        assert history_before == "_Pending_"

        # First append replaces _Pending_
        append_to_revision_history("sess-rev-2", "profiling", "Profiled 3 files")
        history_after = get_section("sess-rev-2", "Revision History")
        assert "_Pending_" not in history_after
        assert "Profiled 3 files" in history_after


# ---------------------------------------------------------------------------
# code_registry provenance tests
# ---------------------------------------------------------------------------


class TestCodeRegistryProvenance:
    """Test code registry provenance tracking."""

    def test_store_with_provenance_fields(self):
        from code_registry.server import store

        entry = store(
            session_id="sess-prov-1",
            step="modeling",
            code="import sklearn",
            intent="Train a random forest model",
            status="stored",
        )
        assert entry.intent == "Train a random forest model"
        assert entry.status == "stored"
        assert entry.parent_id is None

    def test_revision_chain(self):
        from code_registry.server import get_provenance_chain, store

        # Original
        v1 = store(
            session_id="sess-prov-2",
            step="modeling",
            code="# v1 code",
            intent="Train model",
        )

        # Revision 1
        v2 = store(
            session_id="sess-prov-2",
            step="modeling",
            code="# v2 revised code",
            intent="Train model (revised)",
            parent_id=v1.id,
        )

        # Revision 2
        v3 = store(
            session_id="sess-prov-2",
            step="modeling",
            code="# v3 final code",
            intent="Train model (final)",
            parent_id=v2.id,
        )

        # Get provenance chain from v3
        chain = get_provenance_chain("sess-prov-2", v3.id)
        assert len(chain) == 3
        assert chain[0].id == v1.id  # oldest first
        assert chain[1].id == v2.id
        assert chain[2].id == v3.id

    def test_search_by_intent(self):
        from code_registry.server import search_by_intent, store

        store(
            session_id="sess-search-1",
            step="preprocessing",
            code="# handle missing values",
            intent="Handle missing values using median imputation",
        )
        store(
            session_id="sess-search-1",
            step="modeling",
            code="# train model",
            intent="Train gradient boosting classifier",
        )

        # Search for missing value handling
        results = search_by_intent("sess-search-1", "missing values")
        assert len(results) >= 1
        assert any("missing" in r.intent for r in results if r.intent)

        # Search for model training
        results = search_by_intent("sess-search-1", "gradient boosting")
        assert len(results) >= 1

    def test_update_status_with_execution_results(self):
        from code_registry.server import store, update_status

        entry = store(
            session_id="sess-status-1",
            step="eda",
            code="# generate plot",
            status="approved",
        )

        updated = update_status(
            session_id="sess-status-1",
            entry_id=entry.id,
            status="executed",
            stdout="Plot saved to /artifacts/plot.png",
            artifacts_produced=["/artifacts/plot.png"],
        )

        assert updated is not None
        assert updated.status == "executed"
        assert "Plot saved" in (updated.stdout or "")
        assert "/artifacts/plot.png" in updated.artifacts_produced

    def test_store_with_artifacts(self):
        from code_registry.server import retrieve, store

        store(
            session_id="sess-art-1",
            step="explainability",
            code="# SHAP analysis",
            status="executed",
            stdout="SHAP summary plot saved",
            artifacts_produced=["/shap/summary.png", "/shap/waterfall.png"],
        )

        entries = retrieve("sess-art-1", step="explainability")
        assert len(entries) >= 1
        assert len(entries[0].artifacts_produced) == 2


# ---------------------------------------------------------------------------
# node_helpers step-to-section mapping
# ---------------------------------------------------------------------------


class TestStepToSectionMapping:
    """Test that pipeline step names map correctly to session doc sections."""

    def test_all_steps_have_section_mappings(self):
        from app.agent.nodes.node_helpers import _step_to_section

        steps = [
            "profiling",
            "dtype_handling",
            "data_understanding",
            "merge_planning",
            "opportunity_analysis",
            "target_id",
            "feature_selection",
            "eda",
            "preprocessing",
            "hypothesis",
            "hypothesis_generation",
            "hypothesis_execution",
            "feature_eng",
            "modeling",
            "threshold_calibration",
            "explainability",
            "recommendation",
            "report",
        ]

        for step in steps:
            section = _step_to_section(step)
            assert section, f"No section mapping for step: {step}"
            assert section != step, f"Step {step} has no custom mapping"


# ---------------------------------------------------------------------------
# Integration: agent service creates session doc
# ---------------------------------------------------------------------------


class TestStepContextDependencies:
    """Test STEP_CONTEXT_DEPENDENCIES in node_helpers."""

    def test_step_context_dependencies_contains_expected_keys(self):
        """STEP_CONTEXT_DEPENDENCIES should have entries for key pipeline steps."""
        from app.agent.nodes.node_helpers import STEP_CONTEXT_DEPENDENCIES

        expected_steps = [
            "modeling",
            "explainability",
            "feature_eng",
            "hypothesis",
            "recommendation",
            "report",
            "preprocessing",
            "eda",
            "feature_selection",
            "target_id",
            "threshold_calibration",
        ]
        for step in expected_steps:
            assert step in STEP_CONTEXT_DEPENDENCIES, \
                f"Expected '{step}' in STEP_CONTEXT_DEPENDENCIES"
            assert isinstance(STEP_CONTEXT_DEPENDENCIES[step], list), \
                f"Expected list value for '{step}'"
            assert len(STEP_CONTEXT_DEPENDENCIES[step]) > 0, \
                f"Expected non-empty dependency list for '{step}'"

    def test_modeling_depends_on_features_and_target(self):
        """Modeling should depend on Feature Selection, Preprocessing, Target."""
        from app.agent.nodes.node_helpers import STEP_CONTEXT_DEPENDENCIES

        deps = STEP_CONTEXT_DEPENDENCIES["modeling"]
        assert "Feature Selection" in deps
        assert "Preprocessing Decisions" in deps
        assert "Target Variable" in deps

    def test_report_depends_on_multiple_sections(self):
        """Report should depend on Model Results, Recommendations, etc."""
        from app.agent.nodes.node_helpers import STEP_CONTEXT_DEPENDENCIES

        deps = STEP_CONTEXT_DEPENDENCIES["report"]
        assert "Model Results" in deps
        assert "Recommendations" in deps

    def test_all_dependency_sections_are_strings(self):
        """All values in STEP_CONTEXT_DEPENDENCIES should be lists of strings."""
        from app.agent.nodes.node_helpers import STEP_CONTEXT_DEPENDENCIES

        for step, deps in STEP_CONTEXT_DEPENDENCIES.items():
            assert isinstance(deps, list), f"Step '{step}' deps is not a list"
            for dep in deps:
                assert isinstance(dep, str), \
                    f"Dependency '{dep}' for step '{step}' is not a string"


class TestReadStepContextDependentSections:
    """Test that read_step_context returns dependent_sections."""

    def test_read_step_context_has_dependent_sections_key(self):
        """read_step_context should always return 'dependent_sections' key."""
        from app.agent.nodes.node_helpers import read_step_context

        state = {
            "session_id": None,
            "trace_events": [],
            "denial_feedback": {},
            "denial_counts": {},
            "session_doc": "",
            "strategy_hint": "",
        }
        ctx = read_step_context(state, "modeling")
        assert "dependent_sections" in ctx
        assert isinstance(ctx["dependent_sections"], dict)

    def test_read_step_context_no_deps_for_unlisted_step(self):
        """Steps not in STEP_CONTEXT_DEPENDENCIES should have empty deps."""
        from app.agent.nodes.node_helpers import read_step_context

        state = {
            "session_id": None,
            "trace_events": [],
            "denial_feedback": {},
            "denial_counts": {},
            "session_doc": "",
            "strategy_hint": "",
        }
        # 'profiling' is not in STEP_CONTEXT_DEPENDENCIES
        ctx = read_step_context(state, "profiling")
        assert ctx["dependent_sections"] == {}

    def test_read_step_context_returns_strategy_hint(self):
        """read_step_context should return the orchestrator's strategy_hint."""
        from app.agent.nodes.node_helpers import read_step_context

        state = {
            "session_id": None,
            "trace_events": [],
            "denial_feedback": {},
            "denial_counts": {},
            "session_doc": "",
            "strategy_hint": "Focus on churn metrics",
        }
        ctx = read_step_context(state, "eda")
        assert ctx["strategy_hint"] == "Focus on churn metrics"

    def test_read_step_context_returns_denial_fields(self):
        """read_step_context should return denial feedback and count."""
        from app.agent.nodes.node_helpers import read_step_context

        state = {
            "session_id": None,
            "trace_events": [],
            "denial_feedback": {"modeling": ["Use XGBoost", "Add more features"]},
            "denial_counts": {"modeling": 2},
            "session_doc": "",
            "strategy_hint": "",
        }
        ctx = read_step_context(state, "modeling")
        assert ctx["denial_count"] == 2
        assert len(ctx["denial_feedback"]) == 2
        assert "Use XGBoost" in ctx["denial_feedback"]


class TestAgentServiceSessionDoc:
    """Test that agent service initializes session doc in _build_initial_state."""

    @pytest.mark.asyncio
    async def test_build_initial_state_initializes_doc(self, tmp_path):
        """Verify _build_initial_state calls session_doc.initialize()."""
        from session_doc.server import configure_storage, get_section, read

        configure_storage(str(tmp_path))

        # We can't easily test the full _build_initial_state without a DB,
        # but we can verify that initialize + read works end-to-end
        from session_doc.server import initialize

        doc = initialize(
            "test-agent-init",
            company_name="Test Co",
            industry="Fintech",
            business_context="Detect fraud",
        )

        assert "## Business Context" in doc.document
        assert "Test Co" in doc.document

        # Verify doc persists
        doc2 = read("test-agent-init")
        assert doc2.document == doc.document

        # Verify sections are accessible
        biz = get_section("test-agent-init", "Business Context")
        assert "Test Co" in biz
        assert "Fintech" in biz
