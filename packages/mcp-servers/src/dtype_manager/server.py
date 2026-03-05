"""Data type management — cast, validate, and suggest optimal dtypes for columns."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Path / IO helpers
# ---------------------------------------------------------------------------

_ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}


def _validate_path(file_path: str) -> Path:
    p = Path(file_path).resolve()
    if not p.exists():
        raise FileNotFoundError(f"File not found: {p}")
    if p.suffix.lower() not in _ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {p.suffix}")
    return p


def _read_df(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    return pd.read_excel(path, engine="openpyxl")


def _save_df(df: pd.DataFrame, path: Path) -> None:
    if path.suffix.lower() == ".csv":
        df.to_csv(path, index=False)
    else:
        df.to_excel(path, index=False, engine="openpyxl")


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class CastResult(BaseModel):
    success: bool
    column: str
    original_dtype: str
    new_dtype: str
    rows_affected: int
    errors: list[str] = Field(default_factory=list)


class ValidationResult(BaseModel):
    valid: bool
    mismatches: list[dict[str, str]] = Field(default_factory=list)


class TypeSuggestion(BaseModel):
    column: str
    current_dtype: str
    suggested_dtype: str
    reason: str
    confidence: float


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_DTYPE_MAP: dict[str, Any] = {
    "int": "int64",
    "float": "float64",
    "str": "object",
    "string": "object",
    "datetime": "datetime64[ns]",
    "category": "category",
    "bool": "bool",
    "boolean": "bool",
}


def cast_column(file_path: str, column: str, target_dtype: str) -> CastResult:
    """Cast a single column to the specified type, save the file, and report results."""
    path = _validate_path(file_path)
    df = _read_df(path)

    if column not in df.columns:
        return CastResult(
            success=False,
            column=column,
            original_dtype="unknown",
            new_dtype=target_dtype,
            rows_affected=0,
            errors=[f"Column '{column}' not found in file"],
        )

    original_dtype = str(df[column].dtype)
    resolved = _DTYPE_MAP.get(target_dtype, target_dtype)
    errors: list[str] = []

    try:
        if resolved == "datetime64[ns]":
            df[column] = pd.to_datetime(df[column], errors="coerce")
        elif resolved == "category":
            df[column] = df[column].astype("category")
        elif resolved == "bool":
            df[column] = df[column].astype(bool)
        elif resolved in ("int64", "float64"):
            df[column] = pd.to_numeric(df[column], errors="coerce")
            if resolved == "int64":
                if df[column].isna().any():
                    df[column] = df[column].astype("Int64")  # nullable int
                else:
                    df[column] = df[column].astype("int64")
        else:
            df[column] = df[column].astype(resolved)
    except Exception as exc:
        return CastResult(
            success=False,
            column=column,
            original_dtype=original_dtype,
            new_dtype=target_dtype,
            rows_affected=0,
            errors=[str(exc)],
        )

    _save_df(df, path)

    return CastResult(
        success=True,
        column=column,
        original_dtype=original_dtype,
        new_dtype=str(df[column].dtype),
        rows_affected=len(df),
        errors=errors,
    )


def validate_types(file_path: str, expected: dict[str, str]) -> ValidationResult:
    """Check whether columns match the expected dtypes."""
    path = _validate_path(file_path)
    df = _read_df(path)

    mismatches: list[dict[str, str]] = []
    for col, exp_dtype in expected.items():
        if col not in df.columns:
            mismatches.append(
                {"column": col, "expected": exp_dtype, "actual": "MISSING"}
            )
            continue
        actual = str(df[col].dtype)
        resolved = _DTYPE_MAP.get(exp_dtype, exp_dtype)
        if actual != str(resolved) and actual != exp_dtype:
            mismatches.append(
                {"column": col, "expected": exp_dtype, "actual": actual}
            )

    return ValidationResult(valid=len(mismatches) == 0, mismatches=mismatches)


def suggest_types(file_path: str) -> list[TypeSuggestion]:
    """Analyse columns and suggest optimal dtypes."""
    path = _validate_path(file_path)
    df = _read_df(path)

    suggestions: list[TypeSuggestion] = []

    for col in df.columns:
        series = df[col]
        current = str(series.dtype)

        # Object columns that could be numeric
        if current == "object":
            numeric = pd.to_numeric(series.dropna(), errors="coerce")
            pct_numeric = numeric.notna().sum() / max(series.dropna().shape[0], 1)
            if pct_numeric > 0.9:
                if (numeric.dropna() == numeric.dropna().astype(int)).all():
                    suggestions.append(
                        TypeSuggestion(
                            column=str(col),
                            current_dtype=current,
                            suggested_dtype="int",
                            reason="Column values are predominantly integers stored as strings",
                            confidence=round(pct_numeric, 3),
                        )
                    )
                else:
                    suggestions.append(
                        TypeSuggestion(
                            column=str(col),
                            current_dtype=current,
                            suggested_dtype="float",
                            reason="Column values are predominantly floats stored as strings",
                            confidence=round(pct_numeric, 3),
                        )
                    )
                continue

            # Object columns that look like dates
            try:
                parsed = pd.to_datetime(series.dropna(), errors="coerce", infer_datetime_format=True)
                pct_date = parsed.notna().sum() / max(series.dropna().shape[0], 1)
                if pct_date > 0.8:
                    suggestions.append(
                        TypeSuggestion(
                            column=str(col),
                            current_dtype=current,
                            suggested_dtype="datetime",
                            reason="Column values appear to be date/time strings",
                            confidence=round(pct_date, 3),
                        )
                    )
                    continue
            except Exception:
                pass

            # Object columns with low cardinality -> category
            nunique = series.nunique()
            ratio = nunique / max(len(series), 1)
            if nunique <= 50 and ratio < 0.05:
                suggestions.append(
                    TypeSuggestion(
                        column=str(col),
                        current_dtype=current,
                        suggested_dtype="category",
                        reason=f"Low cardinality ({nunique} unique values) — category is more memory efficient",
                        confidence=round(1 - ratio, 3),
                    )
                )

        # Float columns that are actually ints
        elif current.startswith("float"):
            non_null = series.dropna()
            if len(non_null) > 0 and (non_null == non_null.astype(int)).all():
                suggestions.append(
                    TypeSuggestion(
                        column=str(col),
                        current_dtype=current,
                        suggested_dtype="int",
                        reason="All non-null values are whole numbers",
                        confidence=0.95,
                    )
                )

    return suggestions
