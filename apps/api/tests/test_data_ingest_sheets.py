"""Tests for data_ingest MCP server — list_sheets and sheet_name parameter."""

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

from src.data_ingest.server import (
    ListSheetsInput,
    ProfileInput,
    SampleInput,
    list_sheets,
    profile,
    sample,
)


@pytest.fixture()
def csv_file(tmp_path: Path) -> str:
    df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
    path = str(tmp_path / "test.csv")
    df.to_csv(path, index=False)
    return path


@pytest.fixture()
def single_sheet_xlsx(tmp_path: Path) -> str:
    df = pd.DataFrame({"x": [10, 20], "y": [30, 40]})
    path = str(tmp_path / "single.xlsx")
    df.to_excel(path, index=False, sheet_name="Data", engine="openpyxl")
    return path


@pytest.fixture()
def multi_sheet_xlsx(tmp_path: Path) -> str:
    path = str(tmp_path / "multi.xlsx")
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame({"a": [1, 2], "b": [3, 4]}).to_excel(
            writer, sheet_name="Customers", index=False
        )
        pd.DataFrame({"x": [10, 20, 30], "y": [40, 50, 60]}).to_excel(
            writer, sheet_name="Orders", index=False
        )
        pd.DataFrame({"p": [100], "q": [200]}).to_excel(
            writer, sheet_name="Products", index=False
        )
    return path


class TestListSheets:
    """Test the list_sheets() function."""

    def test_csv_returns_single_sheet(self, csv_file: str):
        result = list_sheets(ListSheetsInput(file_path=csv_file))
        assert result.is_multi_sheet is False
        assert len(result.sheets) == 1
        assert result.sheets[0].name == "Sheet1"
        assert result.sheets[0].index == 0

    def test_single_sheet_xlsx(self, single_sheet_xlsx: str):
        result = list_sheets(ListSheetsInput(file_path=single_sheet_xlsx))
        assert result.is_multi_sheet is False
        assert len(result.sheets) == 1
        assert result.sheets[0].name == "Data"

    def test_multi_sheet_xlsx(self, multi_sheet_xlsx: str):
        result = list_sheets(ListSheetsInput(file_path=multi_sheet_xlsx))
        assert result.is_multi_sheet is True
        assert len(result.sheets) == 3
        names = [s.name for s in result.sheets]
        assert names == ["Customers", "Orders", "Products"]
        indices = [s.index for s in result.sheets]
        assert indices == [0, 1, 2]

    def test_nonexistent_file_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            list_sheets(ListSheetsInput(file_path=str(tmp_path / "nope.xlsx")))


class TestProfileWithSheet:
    """Test profiling with sheet_name parameter."""

    def test_profile_default_sheet(self, multi_sheet_xlsx: str):
        result = profile(ProfileInput(file_path=multi_sheet_xlsx))
        # Default sheet (index 0) is "Customers" with columns a, b
        col_names = [c.column_name for c in result.columns]
        assert "a" in col_names
        assert "b" in col_names
        assert result.row_count == 2

    def test_profile_second_sheet_by_name(self, multi_sheet_xlsx: str):
        result = profile(ProfileInput(
            file_path=multi_sheet_xlsx,
            sheet_name="Orders",
        ))
        col_names = [c.column_name for c in result.columns]
        assert "x" in col_names
        assert "y" in col_names
        assert result.row_count == 3

    def test_profile_sheet_by_index(self, multi_sheet_xlsx: str):
        result = profile(ProfileInput(
            file_path=multi_sheet_xlsx,
            sheet_name=2,  # Products
        ))
        col_names = [c.column_name for c in result.columns]
        assert "p" in col_names
        assert "q" in col_names
        assert result.row_count == 1


class TestSampleWithSheet:
    """Test sampling with sheet_name parameter."""

    def test_sample_default_sheet(self, multi_sheet_xlsx: str):
        result = sample(SampleInput(file_path=multi_sheet_xlsx, n=10))
        assert "a" in result.columns
        assert len(result.rows) == 2

    def test_sample_named_sheet(self, multi_sheet_xlsx: str):
        result = sample(SampleInput(
            file_path=multi_sheet_xlsx,
            n=10,
            sheet_name="Orders",
        ))
        assert "x" in result.columns
        assert len(result.rows) == 3


class TestMixedDateFormats:
    """Test profiling with mixed date formats in CSV files."""

    def test_mixed_iso_dates(self, tmp_path: Path):
        """Profile a CSV with ISO-format dates."""
        df = pd.DataFrame({
            "date": ["2024-01-15", "2024-02-20", "2024-03-25"],
            "value": [10, 20, 30],
        })
        path = str(tmp_path / "iso_dates.csv")
        df.to_csv(path, index=False)

        result = profile(ProfileInput(file_path=path))
        col_names = [c.column_name for c in result.columns]
        assert "date" in col_names
        assert result.row_count == 3

    def test_mixed_us_dates(self, tmp_path: Path):
        """Profile a CSV with US-format dates (MM/DD/YYYY)."""
        df = pd.DataFrame({
            "date": ["01/15/2024", "02/20/2024", "12/31/2024"],
            "value": [10, 20, 30],
        })
        path = str(tmp_path / "us_dates.csv")
        df.to_csv(path, index=False)

        result = profile(ProfileInput(file_path=path))
        col_names = [c.column_name for c in result.columns]
        assert "date" in col_names
        assert result.row_count == 3

    def test_mixed_european_dates(self, tmp_path: Path):
        """Profile a CSV with European-format dates (DD.MM.YYYY)."""
        df = pd.DataFrame({
            "date": ["15.01.2024", "20.02.2024", "25.03.2024"],
            "amount": [100, 200, 300],
        })
        path = str(tmp_path / "eu_dates.csv")
        df.to_csv(path, index=False)

        result = profile(ProfileInput(file_path=path))
        assert result.row_count == 3
        date_col = next(c for c in result.columns if c.column_name == "date")
        # Date column should be profiled (may be detected as object, str, or datetime)
        assert date_col.dtype in ("object", "str", "datetime64[ns]")

    def test_mixed_datetime_with_timestamps(self, tmp_path: Path):
        """Profile a CSV with datetime timestamps."""
        df = pd.DataFrame({
            "timestamp": pd.to_datetime([
                "2024-01-15 10:30:00",
                "2024-02-20 14:45:00",
                "2024-03-25 08:15:00",
            ]),
            "score": [0.5, 0.8, 0.3],
        })
        path = str(tmp_path / "timestamps.csv")
        df.to_csv(path, index=False)

        result = profile(ProfileInput(file_path=path))
        assert result.row_count == 3
        col_names = [c.column_name for c in result.columns]
        assert "timestamp" in col_names
