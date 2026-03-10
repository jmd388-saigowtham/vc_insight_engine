"""Tests for session-centric file storage — Phase 3.

Verifies that:
- Uploads go to <upload_dir>/<session_id>/raw/
- Code artifacts are saved in <session_dir>/code/ with provenance headers
- Session memory markdown is created and appended
- StorageService handles collision by adding uuid prefix
"""

import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.storage import StorageService


class TestStorageServiceSessionDir:
    """StorageService stores in session-centric directories."""

    def test_save_with_session_id(self, tmp_path):
        svc = StorageService(str(tmp_path))
        session_id = str(uuid.uuid4())

        path = svc.save_file(b"hello,world", "data.csv", session_id=session_id)

        result_path = Path(path)
        assert result_path.exists()
        assert session_id in str(result_path)
        assert "/raw/" in str(result_path).replace("\\", "/")
        assert result_path.name == "data.csv"
        assert result_path.read_bytes() == b"hello,world"

    def test_save_without_session_id_flat(self, tmp_path):
        svc = StorageService(str(tmp_path))

        path = svc.save_file(b"flat data", "flat.csv")

        result_path = Path(path)
        assert result_path.exists()
        assert result_path.parent == tmp_path
        assert result_path.read_bytes() == b"flat data"

    def test_collision_adds_uuid_prefix(self, tmp_path):
        svc = StorageService(str(tmp_path))
        session_id = str(uuid.uuid4())

        path1 = svc.save_file(b"first", "data.csv", session_id=session_id)
        path2 = svc.save_file(b"second", "data.csv", session_id=session_id)

        assert Path(path1).exists()
        assert Path(path2).exists()
        assert path1 != path2
        assert Path(path1).read_bytes() == b"first"
        assert Path(path2).read_bytes() == b"second"


class TestCodeArtifact:
    """save_code_artifact stores code files with provenance."""

    def test_saves_code_file(self, tmp_path):
        from app.agent.nodes.node_helpers import save_code_artifact

        session_id = str(uuid.uuid4())
        state = {
            "session_id": session_id,
        }

        with patch("app.agent.nodes.node_helpers.get_session_dir") as mock_dir:
            session_dir = tmp_path / session_id
            session_dir.mkdir(parents=True)
            mock_dir.return_value = session_dir

            path = save_code_artifact(
                state, "target_id", "print('hello')", "Test derivation code"
            )

        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "print('hello')" in content
        assert "# Step: target_id" in content
        assert "# Version: 1" in content
        assert "# Description: Test derivation code" in content

    def test_code_in_correct_directory(self, tmp_path):
        from app.agent.nodes.node_helpers import save_code_artifact

        session_id = str(uuid.uuid4())
        state = {"session_id": session_id}

        with patch("app.agent.nodes.node_helpers.get_session_dir") as mock_dir:
            session_dir = tmp_path / session_id
            session_dir.mkdir(parents=True)
            mock_dir.return_value = session_dir

            path = save_code_artifact(state, "modeling", "model.fit()", "Training")

        assert "code" in str(path).replace("\\", "/")
        assert path.name == "modeling_v1.py"

    def test_versioned_code(self, tmp_path):
        from app.agent.nodes.node_helpers import save_code_artifact

        session_id = str(uuid.uuid4())
        state = {"session_id": session_id}

        with patch("app.agent.nodes.node_helpers.get_session_dir") as mock_dir:
            session_dir = tmp_path / session_id
            session_dir.mkdir(parents=True)
            mock_dir.return_value = session_dir

            path1 = save_code_artifact(state, "target_id", "v1", "desc", version=1)
            path2 = save_code_artifact(state, "target_id", "v2", "desc", version=2)

        assert path1.name == "target_id_v1.py"
        assert path2.name == "target_id_v2.py"
        assert "v1" in path1.read_text()
        assert "v2" in path2.read_text()


class TestSessionMemoryMd:
    """update_session_memory_md creates and appends to session.md."""

    def test_creates_memory_file(self, tmp_path):
        from app.agent.nodes.node_helpers import update_session_memory_md

        session_id = str(uuid.uuid4())
        state = {"session_id": session_id, "company_name": "TestCo"}

        with patch("app.agent.nodes.node_helpers.get_session_dir") as mock_dir:
            session_dir = tmp_path / session_id
            session_dir.mkdir(parents=True)
            mock_dir.return_value = session_dir

            path = update_session_memory_md(
                state, "target_id", "Selected: `Churn` (heuristic match)"
            )

        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "# Session Memory" in content
        assert "Target Id" in content
        assert "Selected: `Churn` (heuristic match)" in content

    def test_appends_multiple_sections(self, tmp_path):
        from app.agent.nodes.node_helpers import update_session_memory_md

        session_id = str(uuid.uuid4())
        state = {"session_id": session_id, "company_name": "TestCo"}

        with patch("app.agent.nodes.node_helpers.get_session_dir") as mock_dir:
            session_dir = tmp_path / session_id
            session_dir.mkdir(parents=True)
            mock_dir.return_value = session_dir

            update_session_memory_md(state, "target_id", "Target: Churn")
            update_session_memory_md(state, "eda", "3 plots generated")

        content = path_result = (session_dir / "memory" / "session.md")
        content_text = path_result.read_text(encoding="utf-8")
        assert "Target Id" in content_text
        assert "Eda" in content_text
        assert "Target: Churn" in content_text
        assert "3 plots generated" in content_text


class TestGetSessionDir:
    """get_session_dir returns the correct path."""

    def test_creates_directory(self, tmp_path):
        from app.agent.nodes.node_helpers import get_session_dir

        session_id = str(uuid.uuid4())
        state = {"session_id": session_id}

        with patch("app.config.settings") as mock_settings:
            mock_settings.upload_dir = str(tmp_path)
            session_dir = get_session_dir(state)

        assert session_dir.exists()
        assert session_dir.is_dir()
        assert session_id in str(session_dir)
