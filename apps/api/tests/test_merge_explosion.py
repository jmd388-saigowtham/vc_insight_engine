"""Tests for merge planner — many-to-many join explosion warning generation."""

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

from shared.python.schemas import MergePlan
from src.merge_planner.server import MergeResult, TableInput, detect_keys, execute_merge


@pytest.fixture()
def one_to_many_files(tmp_path: Path) -> tuple[str, str]:
    """Create tables with a one-to-many relationship (no explosion)."""
    customers = pd.DataFrame({
        "customer_id": [1, 2, 3],
        "name": ["Alice", "Bob", "Carol"],
    })
    orders = pd.DataFrame({
        "order_id": [10, 11, 12, 13],
        "customer_id": [1, 1, 2, 3],
        "amount": [100, 200, 150, 300],
    })
    left = str(tmp_path / "customers.csv")
    right = str(tmp_path / "orders.csv")
    customers.to_csv(left, index=False)
    orders.to_csv(right, index=False)
    return left, right


@pytest.fixture()
def many_to_many_files(tmp_path: Path) -> tuple[str, str]:
    """Create tables with many-to-many duplicate keys (causes explosion)."""
    left_df = pd.DataFrame({
        "key": ["A", "A", "B", "B", "C"],
        "left_val": [1, 2, 3, 4, 5],
    })
    right_df = pd.DataFrame({
        "key": ["A", "A", "B", "B", "D"],
        "right_val": [10, 20, 30, 40, 50],
    })
    left = str(tmp_path / "left.csv")
    right = str(tmp_path / "right.csv")
    left_df.to_csv(left, index=False)
    right_df.to_csv(right, index=False)
    return left, right


class TestDetectKeys:
    """Test join key detection across tables."""

    def test_detect_matching_keys(self, one_to_many_files: tuple[str, str]):
        left, right = one_to_many_files
        plans = detect_keys([
            TableInput(file_path=left, alias="customers"),
            TableInput(file_path=right, alias="orders"),
        ])
        assert len(plans) > 0
        # Should find customer_id as a key
        key_pairs = [(p.left_key, p.right_key) for p in plans]
        assert ("customer_id", "customer_id") in key_pairs

    def test_confidence_ranked(self, one_to_many_files: tuple[str, str]):
        left, right = one_to_many_files
        plans = detect_keys([
            TableInput(file_path=left, alias="customers"),
            TableInput(file_path=right, alias="orders"),
        ])
        if len(plans) > 1:
            # Plans should be sorted by confidence descending
            for i in range(len(plans) - 1):
                assert plans[i].confidence >= plans[i + 1].confidence


class TestMergeExplosion:
    """Test many-to-many join explosion warnings."""

    def test_one_to_many_no_warning(self, one_to_many_files: tuple[str, str], tmp_path: Path):
        left, right = one_to_many_files
        plan = MergePlan(
            left_table=left,
            right_table=right,
            left_key="customer_id",
            right_key="customer_id",
            merge_type="left",
        )
        result = execute_merge(plan, str(tmp_path / "merged.csv"))
        assert result.success is True
        assert len(result.warnings) == 0
        assert result.row_count == 4  # one-to-many gives 4 rows

    def test_many_to_many_warning(self, many_to_many_files: tuple[str, str], tmp_path: Path):
        left, right = many_to_many_files
        plan = MergePlan(
            left_table=left,
            right_table=right,
            left_key="key",
            right_key="key",
            merge_type="left",
        )
        result = execute_merge(plan, str(tmp_path / "merged.csv"))
        assert result.success is True
        # Should have warning about many-to-many
        assert len(result.warnings) >= 1
        assert any("many-to-many" in w.lower() for w in result.warnings)

    def test_many_to_many_row_explosion(self, many_to_many_files: tuple[str, str], tmp_path: Path):
        left, right = many_to_many_files
        plan = MergePlan(
            left_table=left,
            right_table=right,
            left_key="key",
            right_key="key",
            merge_type="inner",
        )
        result = execute_merge(plan, str(tmp_path / "merged.csv"))
        assert result.success is True
        # A×A=2×2=4, B×B=2×2=4 → 8 rows (explosion from 5+5)
        assert result.row_count == 8

    def test_missing_key_returns_error(self, one_to_many_files: tuple[str, str], tmp_path: Path):
        left, right = one_to_many_files
        plan = MergePlan(
            left_table=left,
            right_table=right,
            left_key="nonexistent",
            right_key="customer_id",
            merge_type="left",
        )
        result = execute_merge(plan, str(tmp_path / "merged.csv"))
        assert result.success is False
        assert len(result.errors) > 0

    def test_merge_output_saved(self, one_to_many_files: tuple[str, str], tmp_path: Path):
        left, right = one_to_many_files
        output = str(tmp_path / "output.csv")
        plan = MergePlan(
            left_table=left,
            right_table=right,
            left_key="customer_id",
            right_key="customer_id",
            merge_type="left",
        )
        result = execute_merge(plan, output)
        assert result.success is True
        assert Path(output).exists()
        df = pd.read_csv(output)
        assert len(df) == result.row_count
