"""Data preprocessing — missing values, encoding, scaling, and pipeline generation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

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
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".csv":
        df.to_csv(path, index=False)
    else:
        df.to_excel(path, index=False, engine="openpyxl")


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class PreprocessResult(BaseModel):
    success: bool
    output_path: str
    rows: int
    columns: int
    changes_summary: str
    errors: list[str] = Field(default_factory=list)


class PreprocessStep(BaseModel):
    step_type: str  # missing, encode, scale
    columns: list[str]
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def handle_missing(
    file_path: str,
    strategy: dict[str, str],
    output_path: str,
) -> PreprocessResult:
    """Handle missing values using per-column strategies.

    Supported strategies: drop, mean, median, mode, constant, forward_fill, backward_fill.
    For 'constant', pass ``strategy={"col": "constant:VALUE"}``.
    """
    path = _validate_path(file_path)
    out = Path(output_path).resolve()
    df = _read_df(path)
    errors: list[str] = []
    changes: list[str] = []

    for col, method in strategy.items():
        if col not in df.columns:
            errors.append(f"Column '{col}' not found — skipped")
            continue

        before_nulls = int(df[col].isna().sum())
        if before_nulls == 0:
            continue

        if method == "drop":
            df = df.dropna(subset=[col])
            changes.append(f"{col}: dropped {before_nulls} rows with nulls")
        elif method == "mean":
            if pd.api.types.is_numeric_dtype(df[col]):
                df[col] = df[col].fillna(df[col].mean())
                changes.append(f"{col}: filled {before_nulls} nulls with mean")
            else:
                errors.append(f"{col}: mean not applicable to non-numeric column")
        elif method == "median":
            if pd.api.types.is_numeric_dtype(df[col]):
                df[col] = df[col].fillna(df[col].median())
                changes.append(f"{col}: filled {before_nulls} nulls with median")
            else:
                errors.append(f"{col}: median not applicable to non-numeric column")
        elif method == "mode":
            mode_val = df[col].mode()
            if len(mode_val) > 0:
                df[col] = df[col].fillna(mode_val.iloc[0])
                changes.append(f"{col}: filled {before_nulls} nulls with mode")
            else:
                errors.append(f"{col}: no mode found")
        elif method.startswith("constant:"):
            fill_val = method.split(":", 1)[1]
            df[col] = df[col].fillna(fill_val)
            changes.append(f"{col}: filled {before_nulls} nulls with '{fill_val}'")
        elif method == "forward_fill":
            df[col] = df[col].ffill()
            changes.append(f"{col}: forward-filled {before_nulls} nulls")
        elif method == "backward_fill":
            df[col] = df[col].bfill()
            changes.append(f"{col}: backward-filled {before_nulls} nulls")
        else:
            errors.append(f"{col}: unknown strategy '{method}'")

    _save_df(df, out)

    return PreprocessResult(
        success=len(errors) == 0,
        output_path=str(out),
        rows=len(df),
        columns=len(df.columns),
        changes_summary="; ".join(changes) if changes else "No changes applied",
        errors=errors,
    )


def encode_categorical(
    file_path: str,
    columns: list[str],
    method: str,
    output_path: str,
) -> PreprocessResult:
    """Encode categorical columns. Methods: one_hot, label, ordinal, target.

    For ``target`` encoding, pass ``target_col`` in the file as the last column
    (this is a simplification; in production you'd pass it explicitly).
    """
    path = _validate_path(file_path)
    out = Path(output_path).resolve()
    df = _read_df(path)
    errors: list[str] = []
    changes: list[str] = []

    missing = [c for c in columns if c not in df.columns]
    if missing:
        errors.append(f"Columns not found: {missing}")
        columns = [c for c in columns if c in df.columns]

    if method == "one_hot":
        df = pd.get_dummies(df, columns=columns, drop_first=False, dtype=int)
        changes.append(f"One-hot encoded: {columns}")
    elif method == "label":
        from sklearn.preprocessing import LabelEncoder

        for col in columns:
            le = LabelEncoder()
            non_null = df[col].dropna()
            df.loc[non_null.index, col] = le.fit_transform(non_null.astype(str))
            changes.append(f"Label-encoded {col} ({len(le.classes_)} classes)")
    elif method == "ordinal":
        from sklearn.preprocessing import OrdinalEncoder

        enc = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)
        df[columns] = enc.fit_transform(df[columns].astype(str))
        changes.append(f"Ordinal-encoded: {columns}")
    elif method == "target":
        # Simple target encoding: replace each category with mean of target
        # Assumes last column is target
        target_col = df.columns[-1]
        if not pd.api.types.is_numeric_dtype(df[target_col]):
            errors.append("Target encoding requires a numeric target column (last column)")
        else:
            for col in columns:
                means = df.groupby(col)[target_col].mean()
                df[col] = df[col].map(means)
                changes.append(f"Target-encoded {col} using '{target_col}'")
    else:
        errors.append(f"Unknown encoding method: {method}")

    _save_df(df, out)

    return PreprocessResult(
        success=len(errors) == 0,
        output_path=str(out),
        rows=len(df),
        columns=len(df.columns),
        changes_summary="; ".join(changes) if changes else "No changes applied",
        errors=errors,
    )


def scale_numeric(
    file_path: str,
    columns: list[str],
    method: str,
    output_path: str,
) -> PreprocessResult:
    """Scale numeric columns. Methods: standard, minmax, robust, log."""
    path = _validate_path(file_path)
    out = Path(output_path).resolve()
    df = _read_df(path)
    errors: list[str] = []
    changes: list[str] = []

    missing = [c for c in columns if c not in df.columns]
    if missing:
        errors.append(f"Columns not found: {missing}")
        columns = [c for c in columns if c in df.columns]

    non_numeric = [c for c in columns if not pd.api.types.is_numeric_dtype(df[c])]
    if non_numeric:
        errors.append(f"Non-numeric columns cannot be scaled: {non_numeric}")
        columns = [c for c in columns if c not in non_numeric]

    if method == "standard":
        from sklearn.preprocessing import StandardScaler

        scaler = StandardScaler()
        df[columns] = scaler.fit_transform(df[columns])
        changes.append(f"Standard-scaled: {columns}")
    elif method == "minmax":
        from sklearn.preprocessing import MinMaxScaler

        scaler = MinMaxScaler()
        df[columns] = scaler.fit_transform(df[columns])
        changes.append(f"MinMax-scaled: {columns}")
    elif method == "robust":
        from sklearn.preprocessing import RobustScaler

        scaler = RobustScaler()
        df[columns] = scaler.fit_transform(df[columns])
        changes.append(f"Robust-scaled: {columns}")
    elif method == "log":
        for col in columns:
            min_val = df[col].min()
            if min_val <= 0:
                # Shift to make all values positive
                shift = abs(min_val) + 1
                df[col] = np.log1p(df[col] + shift)
                changes.append(f"Log-transformed {col} (shifted by {shift})")
            else:
                df[col] = np.log1p(df[col])
                changes.append(f"Log-transformed {col}")
    else:
        errors.append(f"Unknown scaling method: {method}")

    _save_df(df, out)

    return PreprocessResult(
        success=len(errors) == 0,
        output_path=str(out),
        rows=len(df),
        columns=len(df.columns),
        changes_summary="; ".join(changes) if changes else "No changes applied",
        errors=errors,
    )


def create_pipeline(steps: list[PreprocessStep]) -> str:
    """Generate sklearn Pipeline code from a list of preprocessing steps."""
    lines = [
        "from sklearn.pipeline import Pipeline",
        "from sklearn.compose import ColumnTransformer",
        "from sklearn.preprocessing import (",
        "    StandardScaler, MinMaxScaler, RobustScaler,",
        "    OneHotEncoder, OrdinalEncoder, LabelEncoder,",
        ")",
        "from sklearn.impute import SimpleImputer",
        "import numpy as np",
        "",
        "# Build preprocessing pipeline",
        "transformers = []",
        "",
    ]

    for i, step in enumerate(steps):
        step_name = f"step_{i}_{step.step_type}"
        cols = step.columns

        if step.step_type == "missing":
            strategy_map = {
                "mean": "mean",
                "median": "median",
                "mode": "most_frequent",
                "constant": "constant",
            }
            sklearn_strategy = strategy_map.get(step.method, "mean")
            fill_value = step.params.get("fill_value", None)
            if fill_value:
                lines.append(
                    f'transformers.append(("{step_name}", '
                    f'SimpleImputer(strategy="{sklearn_strategy}", fill_value="{fill_value}"), '
                    f"{cols}))"
                )
            else:
                lines.append(
                    f'transformers.append(("{step_name}", '
                    f'SimpleImputer(strategy="{sklearn_strategy}"), '
                    f"{cols}))"
                )

        elif step.step_type == "encode":
            if step.method == "one_hot":
                lines.append(
                    f'transformers.append(("{step_name}", '
                    f"OneHotEncoder(handle_unknown='ignore', sparse_output=False), "
                    f"{cols}))"
                )
            elif step.method in ("ordinal", "label"):
                lines.append(
                    f'transformers.append(("{step_name}", '
                    f"OrdinalEncoder(handle_unknown='use_encoded_value', unknown_value=-1), "
                    f"{cols}))"
                )

        elif step.step_type == "scale":
            scaler_map = {
                "standard": "StandardScaler()",
                "minmax": "MinMaxScaler()",
                "robust": "RobustScaler()",
            }
            scaler = scaler_map.get(step.method, "StandardScaler()")
            lines.append(
                f'transformers.append(("{step_name}", {scaler}, {cols}))'
            )

        lines.append("")

    lines.extend([
        "preprocessor = ColumnTransformer(",
        "    transformers=transformers,",
        "    remainder='passthrough',",
        ")",
        "",
        "pipeline = Pipeline([",
        "    ('preprocessor', preprocessor),",
        "])",
        "",
        "# Usage:",
        "# X_transformed = pipeline.fit_transform(X)",
    ])

    return "\n".join(lines)
