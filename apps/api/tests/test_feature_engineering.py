"""Tests for polynomial and interaction feature engineering."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

# Make MCP servers and shared package importable
_mcp_root = str(Path(__file__).resolve().parents[3] / "packages" / "mcp-servers")
_shared_root = str(Path(__file__).resolve().parents[3] / "packages")
if _mcp_root not in sys.path:
    sys.path.insert(0, _mcp_root)
if _shared_root not in sys.path:
    sys.path.insert(0, _shared_root)

from src.preprocessing.server import (
    create_interaction_features,
    create_polynomial_features,
)


@pytest.fixture()
def numeric_csv(tmp_path: Path) -> str:
    df = pd.DataFrame({
        "a": [1.0, 2.0, 3.0, 4.0],
        "b": [10.0, 20.0, 30.0, 40.0],
        "c": [100.0, 200.0, 300.0, 400.0],
        "label": ["x", "y", "x", "y"],
    })
    path = str(tmp_path / "numeric.csv")
    df.to_csv(path, index=False)
    return path


class TestPolynomialFeatures:
    """Test create_polynomial_features()."""

    def test_basic_polynomial(self, numeric_csv: str, tmp_path: Path):
        output = str(tmp_path / "poly.csv")
        result = create_polynomial_features(
            file_path=numeric_csv,
            columns=["a", "b"],
            degree=2,
            output_path=output,
        )
        assert result.success is True
        df = pd.read_csv(output)
        # Original columns + new polynomial columns
        assert len(df.columns) > 4  # a, b, c, label + polynomial terms

    def test_polynomial_degree_3(self, numeric_csv: str, tmp_path: Path):
        output = str(tmp_path / "poly3.csv")
        result = create_polynomial_features(
            file_path=numeric_csv,
            columns=["a"],
            degree=3,
            output_path=output,
        )
        assert result.success is True
        df = pd.read_csv(output)
        # a, a^2, a^3 should be added (2 new columns)
        assert "a^2" in df.columns or len(df.columns) > 4

    def test_polynomial_interaction_only(self, numeric_csv: str, tmp_path: Path):
        output = str(tmp_path / "inter.csv")
        result = create_polynomial_features(
            file_path=numeric_csv,
            columns=["a", "b"],
            degree=2,
            output_path=output,
            interaction_only=True,
        )
        assert result.success is True
        df = pd.read_csv(output)
        # Only interaction terms (a*b), no a^2 or b^2
        assert len(df.columns) >= 5  # a, b, c, label + a*b

    def test_polynomial_missing_column(self, numeric_csv: str, tmp_path: Path):
        output = str(tmp_path / "poly.csv")
        result = create_polynomial_features(
            file_path=numeric_csv,
            columns=["a", "nonexistent"],
            degree=2,
            output_path=output,
        )
        # Should still succeed with available columns
        assert result.success is True
        assert len(result.errors) > 0

    def test_polynomial_non_numeric_skipped(self, numeric_csv: str, tmp_path: Path):
        output = str(tmp_path / "poly.csv")
        result = create_polynomial_features(
            file_path=numeric_csv,
            columns=["label"],  # non-numeric
            degree=2,
            output_path=output,
        )
        assert result.success is False
        assert len(result.errors) > 0


class TestInteractionFeatures:
    """Test create_interaction_features()."""

    def test_basic_interaction(self, numeric_csv: str, tmp_path: Path):
        output = str(tmp_path / "interact.csv")
        result = create_interaction_features(
            file_path=numeric_csv,
            column_pairs=[("a", "b")],
            output_path=output,
        )
        assert result.success is True
        df = pd.read_csv(output)
        assert "a_x_b" in df.columns
        assert df["a_x_b"].iloc[0] == 10.0  # 1 * 10

    def test_multiple_interactions(self, numeric_csv: str, tmp_path: Path):
        output = str(tmp_path / "interact.csv")
        result = create_interaction_features(
            file_path=numeric_csv,
            column_pairs=[("a", "b"), ("a", "c"), ("b", "c")],
            output_path=output,
        )
        assert result.success is True
        df = pd.read_csv(output)
        assert "a_x_b" in df.columns
        assert "a_x_c" in df.columns
        assert "b_x_c" in df.columns

    def test_interaction_missing_column(self, numeric_csv: str, tmp_path: Path):
        output = str(tmp_path / "interact.csv")
        result = create_interaction_features(
            file_path=numeric_csv,
            column_pairs=[("a", "nonexistent")],
            output_path=output,
        )
        assert result.success is False
        assert len(result.errors) > 0

    def test_interaction_non_numeric(self, numeric_csv: str, tmp_path: Path):
        output = str(tmp_path / "interact.csv")
        result = create_interaction_features(
            file_path=numeric_csv,
            column_pairs=[("a", "label")],
            output_path=output,
        )
        assert result.success is False
        assert len(result.errors) > 0
