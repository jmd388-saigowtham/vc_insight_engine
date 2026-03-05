"""ML modeling and SHAP explainability — train, explain, predict."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from shared.python.schemas import ModelResult, ShapResult

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


def _is_classification(y: pd.Series) -> bool:
    """Heuristic: classification if <=20 unique values or non-numeric."""
    if not pd.api.types.is_numeric_dtype(y):
        return True
    return y.nunique() <= 20


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class PredictionResult(BaseModel):
    predictions: list[Any]
    probabilities: list[list[float]] | None = None
    row_count: int


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def train(
    data_path: str,
    target_col: str,
    model_types: list[str],
    output_dir: str,
) -> list[ModelResult]:
    """Train multiple sklearn models, evaluate, and save the best one.

    Supported model_types: logistic_regression, random_forest, gradient_boosting, svm.
    """
    from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor
    from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
    from sklearn.linear_model import LogisticRegression, LinearRegression
    from sklearn.metrics import (
        accuracy_score,
        f1_score,
        precision_score,
        recall_score,
        roc_auc_score,
        mean_squared_error,
        r2_score,
    )
    from sklearn.model_selection import train_test_split
    from sklearn.svm import SVC, SVR
    import joblib

    path = _validate_path(data_path)
    df = _read_df(path)
    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if target_col not in df.columns:
        raise ValueError(f"Target column '{target_col}' not found")

    # Prepare data — drop non-numeric columns except target
    X = df.drop(columns=[target_col])
    y = df[target_col]

    # Auto-encode categorical features
    cat_cols = X.select_dtypes(include=["object", "category"]).columns.tolist()
    if cat_cols:
        X = pd.get_dummies(X, columns=cat_cols, drop_first=True, dtype=float)

    # Handle missing values
    X = X.fillna(X.median(numeric_only=True))
    if y.isna().any():
        mask = y.notna()
        X = X.loc[mask]
        y = y.loc[mask]

    is_clf = _is_classification(y)

    if is_clf:
        from sklearn.preprocessing import LabelEncoder
        if not pd.api.types.is_numeric_dtype(y):
            le = LabelEncoder()
            y = pd.Series(le.fit_transform(y), index=y.index)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y if is_clf and y.nunique() > 1 else None
    )

    # Model factories
    clf_map: dict[str, Any] = {
        "logistic_regression": LogisticRegression(max_iter=1000, random_state=42),
        "random_forest": RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1),
        "gradient_boosting": GradientBoostingClassifier(n_estimators=100, random_state=42),
        "svm": SVC(kernel="linear", probability=True, random_state=42, max_iter=5000),
    }
    reg_map: dict[str, Any] = {
        "logistic_regression": LinearRegression(),
        "random_forest": RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1),
        "gradient_boosting": GradientBoostingRegressor(n_estimators=100, random_state=42),
        "svm": SVR(kernel="linear", max_iter=5000),
    }

    model_factory = clf_map if is_clf else reg_map
    results: list[ModelResult] = []
    best_score = -np.inf
    best_idx = -1

    for mt in model_types:
        if mt not in model_factory:
            results.append(
                ModelResult(
                    model_name=mt,
                    model_type=mt,
                    metrics={"error": -1.0},
                    best=False,
                )
            )
            continue

        model = model_factory[mt]
        try:
            model.fit(X_train, y_train)
        except Exception as exc:
            results.append(
                ModelResult(
                    model_name=mt,
                    model_type=mt,
                    metrics={"error": -1.0},
                    best=False,
                )
            )
            continue

        y_pred = model.predict(X_test)
        model_path = str(out_dir / f"{mt}.joblib")
        joblib.dump(model, model_path)

        # Also save feature names for later use
        feature_names_path = str(out_dir / f"{mt}_features.joblib")
        joblib.dump(list(X.columns), feature_names_path)

        metrics: dict[str, float] = {}
        if is_clf:
            metrics["accuracy"] = round(float(accuracy_score(y_test, y_pred)), 4)
            avg = "binary" if y.nunique() == 2 else "weighted"
            metrics["precision"] = round(float(precision_score(y_test, y_pred, average=avg, zero_division=0)), 4)
            metrics["recall"] = round(float(recall_score(y_test, y_pred, average=avg, zero_division=0)), 4)
            metrics["f1"] = round(float(f1_score(y_test, y_pred, average=avg, zero_division=0)), 4)

            try:
                if hasattr(model, "predict_proba"):
                    y_proba = model.predict_proba(X_test)
                    if y.nunique() == 2:
                        metrics["roc_auc"] = round(float(roc_auc_score(y_test, y_proba[:, 1])), 4)
                    else:
                        metrics["roc_auc"] = round(float(roc_auc_score(y_test, y_proba, multi_class="ovr")), 4)
            except Exception:
                pass

            score = metrics.get("f1", 0.0)
        else:
            metrics["r2"] = round(float(r2_score(y_test, y_pred)), 4)
            metrics["rmse"] = round(float(np.sqrt(mean_squared_error(y_test, y_pred))), 4)
            score = metrics["r2"]

        if score > best_score:
            best_score = score
            best_idx = len(results)

        results.append(
            ModelResult(
                model_name=mt,
                model_type=mt,
                metrics=metrics,
                best=False,
                model_path=model_path,
            )
        )

    # Mark the best
    if 0 <= best_idx < len(results):
        results[best_idx].best = True

    return results


def shap_analysis(
    model_path: str,
    data_path: str,
    target_col: str,
    output_dir: str,
) -> ShapResult:
    """Compute SHAP values and generate explanation plots."""
    import joblib
    import shap

    model = joblib.load(model_path)
    data_file = _validate_path(data_path)
    df = _read_df(data_file)
    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    X = df.drop(columns=[target_col], errors="ignore")

    # Auto-encode categorical features (same as training)
    cat_cols = X.select_dtypes(include=["object", "category"]).columns.tolist()
    if cat_cols:
        X = pd.get_dummies(X, columns=cat_cols, drop_first=True, dtype=float)
    X = X.fillna(X.median(numeric_only=True))

    # Try to load saved feature names to align columns
    features_path = model_path.replace(".joblib", "_features.joblib")
    if Path(features_path).exists():
        saved_features = joblib.load(features_path)
        # Add missing columns as 0, reorder to match training
        for col in saved_features:
            if col not in X.columns:
                X[col] = 0
        X = X[saved_features]

    # Use a sample for speed
    sample_size = min(500, len(X))
    X_sample = X.sample(n=sample_size, random_state=42) if len(X) > sample_size else X

    # Choose appropriate explainer
    tree_models = ("RandomForest", "GradientBoosting", "XGB", "LGBM", "DecisionTree")
    model_name = type(model).__name__
    if any(t in model_name for t in tree_models):
        explainer = shap.TreeExplainer(model)
    else:
        explainer = shap.Explainer(model, X_sample)

    shap_values = explainer(X_sample)

    # Summary bar plot
    summary_path = str(out_dir / "shap_summary.png")
    fig, ax = plt.subplots(figsize=(10, 8))
    shap.plots.bar(shap_values, max_display=20, show=False)
    plt.tight_layout()
    plt.savefig(summary_path, dpi=150, bbox_inches="tight")
    plt.close("all")

    # Feature importance from SHAP
    if hasattr(shap_values, "values"):
        vals = np.abs(shap_values.values)
        if vals.ndim == 3:
            vals = vals.mean(axis=2)
        mean_abs = vals.mean(axis=0)
    else:
        mean_abs = np.abs(shap_values).mean(axis=0)

    feature_names = list(X_sample.columns)
    fi = sorted(
        [{"feature": f, "importance": round(float(v), 6)} for f, v in zip(feature_names, mean_abs)],
        key=lambda x: x["importance"],
        reverse=True,
    )

    # Waterfall plots for first 3 samples
    waterfall_paths: list[str] = []
    for i in range(min(3, len(X_sample))):
        wp = str(out_dir / f"shap_waterfall_{i}.png")
        try:
            fig, ax = plt.subplots(figsize=(10, 8))
            shap.plots.waterfall(shap_values[i], max_display=15, show=False)
            plt.tight_layout()
            plt.savefig(wp, dpi=150, bbox_inches="tight")
            plt.close("all")
            waterfall_paths.append(wp)
        except Exception:
            plt.close("all")

    return ShapResult(
        summary_plot_path=summary_path,
        feature_importance=fi,
        waterfall_plots=waterfall_paths,
    )


def predict(model_path: str, data_path: str) -> PredictionResult:
    """Load a trained model and predict on new data."""
    import joblib

    model = joblib.load(model_path)
    data_file = _validate_path(data_path)
    df = _read_df(data_file)

    # Auto-encode categorical features
    cat_cols = df.select_dtypes(include=["object", "category"]).columns.tolist()
    if cat_cols:
        df = pd.get_dummies(df, columns=cat_cols, drop_first=True, dtype=float)
    df = df.fillna(df.median(numeric_only=True))

    # Align with training features
    features_path = model_path.replace(".joblib", "_features.joblib")
    if Path(features_path).exists():
        saved_features = joblib.load(features_path)
        for col in saved_features:
            if col not in df.columns:
                df[col] = 0
        df = df[saved_features]

    preds = model.predict(df)
    probas = None
    if hasattr(model, "predict_proba"):
        try:
            probas = model.predict_proba(df).tolist()
        except Exception:
            pass

    return PredictionResult(
        predictions=preds.tolist(),
        probabilities=probas,
        row_count=len(df),
    )


def feature_importance(model_path: str, feature_names: list[str]) -> list[dict[str, Any]]:
    """Extract feature importance from a trained model."""
    import joblib

    model = joblib.load(model_path)
    importances: np.ndarray | None = None

    if hasattr(model, "feature_importances_"):
        importances = model.feature_importances_
    elif hasattr(model, "coef_"):
        coef = model.coef_
        if coef.ndim > 1:
            importances = np.abs(coef).mean(axis=0)
        else:
            importances = np.abs(coef)
    else:
        return [{"feature": f, "importance": 0.0} for f in feature_names]

    if len(importances) != len(feature_names):
        # Use loaded feature names if available
        features_path = model_path.replace(".joblib", "_features.joblib")
        if Path(features_path).exists():
            feature_names = joblib.load(features_path)

    result = sorted(
        [
            {"feature": f, "importance": round(float(v), 6)}
            for f, v in zip(feature_names, importances)
        ],
        key=lambda x: x["importance"],
        reverse=True,
    )
    return result
