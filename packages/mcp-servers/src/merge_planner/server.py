"""Merge planner — detect join keys across tables, generate merge code, execute merges."""

from __future__ import annotations

from itertools import combinations
from pathlib import Path

import pandas as pd
from pydantic import BaseModel, Field

from shared.python.schemas import MergePlan

# ---------------------------------------------------------------------------
# Helpers
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


class TableInput(BaseModel):
    file_path: str
    alias: str | None = None


class MergeResult(BaseModel):
    success: bool
    output_path: str
    row_count: int
    column_count: int
    columns: list[str]
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Key detection heuristics
# ---------------------------------------------------------------------------


def _name_similarity(a: str, b: str) -> float:
    """Simple normalised name similarity based on lower-cased tokens."""
    a_norm = a.lower().replace("_", " ").replace("-", " ")
    b_norm = b.lower().replace("_", " ").replace("-", " ")
    if a_norm == b_norm:
        return 1.0
    # Check suffix/prefix matches (e.g. customer_id vs id)
    a_parts = set(a_norm.split())
    b_parts = set(b_norm.split())
    if a_parts & b_parts:
        return len(a_parts & b_parts) / max(len(a_parts | b_parts), 1)
    return 0.0


def _value_overlap(s1: pd.Series, s2: pd.Series) -> float:
    """Fraction of values in the smaller set that appear in the larger set."""
    u1 = set(s1.dropna().unique())
    u2 = set(s2.dropna().unique())
    if not u1 or not u2:
        return 0.0
    smaller, larger = (u1, u2) if len(u1) <= len(u2) else (u2, u1)
    overlap = len(smaller & larger)
    return overlap / len(smaller)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_keys(tables: list[TableInput]) -> list[MergePlan]:
    """Analyse multiple tables and find potential join keys.

    Returns ranked merge plans with confidence scores.
    """
    loaded: list[tuple[str, pd.DataFrame]] = []
    for t in tables:
        path = _validate_path(t.file_path)
        df = _read_df(path)
        label = t.alias or path.stem
        loaded.append((label, df))

    plans: list[MergePlan] = []

    for (label_a, df_a), (label_b, df_b) in combinations(loaded, 2):
        for col_a in df_a.columns:
            for col_b in df_b.columns:
                name_sim = _name_similarity(str(col_a), str(col_b))
                if name_sim < 0.3:
                    continue

                # Check dtype compatibility
                if df_a[col_a].dtype.kind != df_b[col_b].dtype.kind:
                    # Try coercing both to string for comparison
                    s_a = df_a[col_a].astype(str)
                    s_b = df_b[col_b].astype(str)
                else:
                    s_a = df_a[col_a]
                    s_b = df_b[col_b]

                overlap = _value_overlap(s_a, s_b)
                if overlap < 0.1:
                    continue

                # Uniqueness of key in each table
                uniq_a = df_a[col_a].nunique() / max(len(df_a), 1)
                uniq_b = df_b[col_b].nunique() / max(len(df_b), 1)

                # Higher uniqueness + higher overlap + higher name sim → higher confidence
                confidence = round(
                    0.3 * name_sim + 0.5 * overlap + 0.2 * max(uniq_a, uniq_b), 3
                )

                merge_type = "left"
                if uniq_a > 0.9 and uniq_b > 0.9:
                    merge_type = "inner"

                rationale_parts = [
                    f"Name similarity: {name_sim:.0%}",
                    f"Value overlap: {overlap:.0%}",
                    f"Uniqueness L: {uniq_a:.0%}, R: {uniq_b:.0%}",
                ]

                plans.append(
                    MergePlan(
                        left_table=label_a,
                        right_table=label_b,
                        left_key=str(col_a),
                        right_key=str(col_b),
                        merge_type=merge_type,
                        confidence=confidence,
                        rationale="; ".join(rationale_parts),
                    )
                )

    plans.sort(key=lambda p: p.confidence, reverse=True)
    return plans


def generate_merge_code(plan: MergePlan) -> str:
    """Generate pandas merge code from a merge plan."""
    return (
        f"import pandas as pd\n\n"
        f'left_df = pd.read_csv("{plan.left_table}")\n'
        f'right_df = pd.read_csv("{plan.right_table}")\n\n'
        f"merged = pd.merge(\n"
        f"    left_df,\n"
        f"    right_df,\n"
        f'    left_on="{plan.left_key}",\n'
        f'    right_on="{plan.right_key}",\n'
        f'    how="{plan.merge_type}",\n'
        f")\n\n"
        f'print(f"Merged shape: {{merged.shape}}")\n'
        f"print(merged.head())\n"
    )


def execute_merge(plan: MergePlan, output_path: str) -> MergeResult:
    """Execute a merge plan and save the result."""
    warnings: list[str] = []
    try:
        left_path = _validate_path(plan.left_table)
        right_path = _validate_path(plan.right_table)
        out_path = Path(output_path).resolve()

        left_df = _read_df(left_path)
        right_df = _read_df(right_path)

        if plan.left_key not in left_df.columns:
            return MergeResult(
                success=False,
                output_path=output_path,
                row_count=0,
                column_count=0,
                columns=[],
                errors=[f"Key '{plan.left_key}' not found in left table"],
            )
        if plan.right_key not in right_df.columns:
            return MergeResult(
                success=False,
                output_path=output_path,
                row_count=0,
                column_count=0,
                columns=[],
                errors=[f"Key '{plan.right_key}' not found in right table"],
            )

        # Many-to-many join explosion detection
        left_dups = left_df[plan.left_key].duplicated().any()
        right_dups = right_df[plan.right_key].duplicated().any()
        if left_dups and right_dups:
            left_dup_count = int(left_df[plan.left_key].duplicated().sum())
            right_dup_count = int(right_df[plan.right_key].duplicated().sum())
            est_max = len(left_df) * len(right_df)
            warnings.append(
                f"Many-to-many join detected: left key '{plan.left_key}' has "
                f"{left_dup_count} duplicate(s), right key '{plan.right_key}' has "
                f"{right_dup_count} duplicate(s). Output may contain up to "
                f"{est_max:,} rows (row explosion risk)."
            )

        merged = pd.merge(
            left_df,
            right_df,
            left_on=plan.left_key,
            right_on=plan.right_key,
            how=plan.merge_type,
        )

        # Post-merge explosion check
        expected_max = max(len(left_df), len(right_df)) * 2
        if len(merged) > expected_max:
            warnings.append(
                f"Row explosion occurred: input had {len(left_df)} + {len(right_df)} "
                f"rows, output has {len(merged)} rows."
            )

        out_path.parent.mkdir(parents=True, exist_ok=True)
        _save_df(merged, out_path)

        return MergeResult(
            success=True,
            output_path=str(out_path),
            row_count=len(merged),
            column_count=len(merged.columns),
            columns=[str(c) for c in merged.columns],
            warnings=warnings,
        )
    except Exception as exc:
        return MergeResult(
            success=False,
            output_path=output_path,
            row_count=0,
            column_count=0,
            columns=[],
            errors=[str(exc)],
        )
