"""ML modeling and SHAP explainability — train, explain, predict."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pydantic import BaseModel

from shared.python.schemas import (
    CalibrationResult,
    LearningCurveResult,
    ModelCard,
    ModelResult,
    ShapResult,
)

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


def _compute_metrics(
    y_true: pd.Series,
    y_pred: np.ndarray,
    is_clf: bool,
    y_full: pd.Series,
    y_proba: np.ndarray | None = None,
) -> dict[str, float]:
    """Compute evaluation metrics for a given split."""
    from sklearn.metrics import (
        accuracy_score, f1_score, precision_score, recall_score,
        roc_auc_score, mean_squared_error, r2_score,
    )

    metrics: dict[str, float] = {}
    if is_clf:
        avg = "binary" if y_full.nunique() == 2 else "weighted"
        metrics["accuracy"] = round(float(accuracy_score(y_true, y_pred)), 4)
        metrics["precision"] = round(float(precision_score(
            y_true, y_pred, average=avg, zero_division=0,
        )), 4)
        metrics["recall"] = round(float(recall_score(
            y_true, y_pred, average=avg, zero_division=0,
        )), 4)
        metrics["f1"] = round(float(f1_score(
            y_true, y_pred, average=avg, zero_division=0,
        )), 4)
        if y_proba is not None:
            try:
                if y_full.nunique() == 2:
                    metrics["roc_auc"] = round(float(
                        roc_auc_score(y_true, y_proba[:, 1]),
                    ), 4)
                else:
                    metrics["roc_auc"] = round(float(
                        roc_auc_score(y_true, y_proba, multi_class="ovr"),
                    ), 4)
            except Exception:
                pass
    else:
        metrics["r2"] = round(float(r2_score(y_true, y_pred)), 4)
        metrics["rmse"] = round(float(np.sqrt(mean_squared_error(y_true, y_pred))), 4)
    return metrics


def _detect_fit_issues(
    train_metrics: dict[str, float],
    test_metrics: dict[str, float],
    is_clf: bool,
) -> dict[str, Any]:
    """Detect overfitting or underfitting by comparing train vs test metrics."""
    primary = "f1" if is_clf else "r2"
    train_score = train_metrics.get(primary, 0.0)
    test_score = test_metrics.get(primary, 0.0)
    gap = train_score - test_score

    diagnostics: dict[str, Any] = {
        "train_test_gap": round(gap, 4),
        "primary_metric": primary,
    }

    if gap > 0.10:
        diagnostics["status"] = "overfitting"
        diagnostics["message"] = (
            f"Model is overfitting: train {primary}={train_score:.4f}, "
            f"test {primary}={test_score:.4f} (gap={gap:.4f})"
        )
    elif is_clf and train_score < 0.60 and test_score < 0.60:
        diagnostics["status"] = "underfitting"
        diagnostics["message"] = (
            f"Model may be underfitting: train {primary}={train_score:.4f}, "
            f"test {primary}={test_score:.4f}"
        )
    elif not is_clf and train_score < 0.0 and test_score < 0.0:
        diagnostics["status"] = "underfitting"
        diagnostics["message"] = "Model is underfitting: negative R² on both sets"
    else:
        diagnostics["status"] = "good_fit"
        diagnostics["message"] = (
            f"Good fit: train {primary}={train_score:.4f}, "
            f"test {primary}={test_score:.4f}"
        )

    return diagnostics


def _param_combinations(grid: dict) -> int:
    """Estimate the number of parameter combinations in a grid."""
    n = 1
    for v in grid.values():
        n *= len(v) if isinstance(v, list) else 1
    return n


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


def detect_leakage(
    data_path: str,
    target_col: str,
    threshold: float = 0.95,
) -> list[dict[str, Any]]:
    """Detect potential target leakage by checking feature-target correlations."""
    path = _validate_path(data_path)
    df = _read_df(path)

    if target_col not in df.columns:
        return []

    y = df[target_col]
    X = df.drop(columns=[target_col])
    numeric_cols = X.select_dtypes(include=["number"]).columns
    if len(numeric_cols) == 0:
        return []

    # Encode target if non-numeric for correlation
    if not pd.api.types.is_numeric_dtype(y):
        from sklearn.preprocessing import LabelEncoder
        y_enc = pd.Series(
            LabelEncoder().fit_transform(y.fillna("__missing__")),
            index=y.index,
        )
    else:
        y_enc = y

    leaky: list[dict[str, Any]] = []
    for col in numeric_cols:
        try:
            corr = abs(float(X[col].corr(y_enc)))
            if corr > threshold:
                leaky.append({
                    "feature": str(col),
                    "correlation": round(corr, 4),
                    "reason": f"Very high correlation ({corr:.4f}) with target",
                })
        except Exception:
            continue

    return leaky


def _detect_date_column(df: pd.DataFrame) -> str | None:
    """Find a date/datetime column suitable for temporal splitting."""
    # Check datetime columns first
    dt_cols = df.select_dtypes(include=["datetime64"]).columns.tolist()
    if dt_cols:
        return dt_cols[0]

    # Check object columns that look like dates
    date_keywords = {"date", "timestamp", "time", "datetime", "created", "updated"}
    for col in df.select_dtypes(include=["object"]).columns:
        if any(kw in col.lower() for kw in date_keywords):
            try:
                pd.to_datetime(df[col].dropna().head(20))
                return col
            except Exception:
                continue
    return None


def _find_optimal_threshold(
    y_true: pd.Series,
    y_proba: np.ndarray,
) -> dict[str, Any]:
    """Find optimal classification threshold via precision-recall curve."""
    from sklearn.metrics import precision_recall_curve, f1_score as sk_f1

    if y_proba is None or y_proba.ndim < 2:
        return {"threshold": 0.5, "method": "default"}

    probas = y_proba[:, 1]
    precisions, recalls, thresholds = precision_recall_curve(y_true, probas)

    # Compute F1 for each threshold (safe division)
    denom = precisions[:-1] + recalls[:-1]
    with np.errstate(divide="ignore", invalid="ignore"):
        f1_scores = np.where(
            denom > 0,
            2 * (precisions[:-1] * recalls[:-1]) / denom,
            0.0,
        )

    best_idx = int(np.argmax(f1_scores))
    optimal = float(thresholds[best_idx])

    return {
        "threshold": round(optimal, 4),
        "f1_at_threshold": round(float(f1_scores[best_idx]), 4),
        "precision_at_threshold": round(float(precisions[best_idx]), 4),
        "recall_at_threshold": round(float(recalls[best_idx]), 4),
        "method": "precision_recall_curve",
    }


def train(
    data_path: str,
    target_col: str,
    model_types: list[str],
    output_dir: str,
    selected_features: list[str] | None = None,
    tune_hyperparams: bool = True,
    split_strategy: str = "auto",
    threshold: float | None = None,
) -> list[ModelResult]:
    """Train multiple sklearn models, evaluate, and save the best one.

    Supported model_types: logistic_regression, random_forest, gradient_boosting, svm,
    extra_trees, knn. Optional (if installed): xgboost, lightgbm.
    Uses 3-way split (70/15/15), optional hyperparameter tuning, and overfit detection.

    split_strategy: "auto" (detect date columns, use temporal if found), "random", or "temporal".
    threshold: Classification threshold (0.0-1.0). If None, optimal threshold is computed
               via precision-recall curve. Default 0.5 is used only for non-binary tasks.
    """
    from sklearn.ensemble import (
        ExtraTreesClassifier, ExtraTreesRegressor,
        GradientBoostingClassifier, GradientBoostingRegressor,
        RandomForestClassifier, RandomForestRegressor,
    )
    from sklearn.linear_model import LogisticRegression, LinearRegression
    from sklearn.model_selection import train_test_split
    from sklearn.neighbors import KNeighborsClassifier, KNeighborsRegressor
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

    # Filter to selected features if specified
    if selected_features:
        available = [f for f in selected_features if f in X.columns]
        if available:
            X = X[available]

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

    # 3-way split: 70% train, 15% validation, 15% test
    use_temporal = False
    date_col = None
    if split_strategy in ("auto", "temporal"):
        date_col = _detect_date_column(df)
        if date_col:
            use_temporal = True

    if use_temporal and date_col:
        # Temporal split: sort by date, split chronologically
        date_series = pd.to_datetime(df[date_col], errors="coerce")
        sort_idx = date_series.sort_values().index
        X = X.loc[sort_idx].reset_index(drop=True)
        y = y.loc[sort_idx].reset_index(drop=True)

        n = len(X)
        train_end = int(n * 0.70)
        val_end = int(n * 0.85)

        X_train, y_train = X.iloc[:train_end], y.iloc[:train_end]
        X_val, y_val = X.iloc[train_end:val_end], y.iloc[train_end:val_end]
        X_test, y_test = X.iloc[val_end:], y.iloc[val_end:]
    else:
        # Random stratified split
        strat = y if is_clf and y.nunique() > 1 else None
        X_trainval, X_test, y_trainval, y_test = train_test_split(
            X, y, test_size=0.15, random_state=42, stratify=strat,
        )
        strat_tv = y_trainval if is_clf and y_trainval.nunique() > 1 else None
        X_train, X_val, y_train, y_val = train_test_split(
            X_trainval, y_trainval, test_size=0.176, random_state=42, stratify=strat_tv,
        )

    # Detect class imbalance
    use_balanced = False
    if is_clf:
        class_counts = y_train.value_counts()
        if len(class_counts) >= 2:
            minority_ratio = class_counts.min() / class_counts.max()
            use_balanced = minority_ratio < 0.2

    # Model factories (with class imbalance handling)
    cw = "balanced" if use_balanced else None
    clf_map: dict[str, Any] = {
        "logistic_regression": LogisticRegression(
            max_iter=1000, random_state=42, class_weight=cw,
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=100, random_state=42, n_jobs=-1, class_weight=cw,
        ),
        "gradient_boosting": GradientBoostingClassifier(
            n_estimators=100, random_state=42,
        ),
        "svm": SVC(
            kernel="linear", probability=True, random_state=42,
            max_iter=5000, class_weight=cw,
        ),
        "extra_trees": ExtraTreesClassifier(
            n_estimators=100, random_state=42, n_jobs=-1, class_weight=cw,
        ),
        "knn": KNeighborsClassifier(n_neighbors=5, n_jobs=-1),
    }
    reg_map: dict[str, Any] = {
        "logistic_regression": LinearRegression(),
        "random_forest": RandomForestRegressor(
            n_estimators=100, random_state=42, n_jobs=-1,
        ),
        "gradient_boosting": GradientBoostingRegressor(
            n_estimators=100, random_state=42,
        ),
        "svm": SVR(kernel="linear", max_iter=5000),
        "extra_trees": ExtraTreesRegressor(
            n_estimators=100, random_state=42, n_jobs=-1,
        ),
        "knn": KNeighborsRegressor(n_neighbors=5, n_jobs=-1),
    }

    # Optional: XGBoost and LightGBM (if installed)
    try:
        from xgboost import XGBClassifier, XGBRegressor
        clf_map["xgboost"] = XGBClassifier(
            n_estimators=100, random_state=42, use_label_encoder=False,
            eval_metric="logloss", n_jobs=-1,
        )
        reg_map["xgboost"] = XGBRegressor(
            n_estimators=100, random_state=42, n_jobs=-1,
        )
    except ImportError:
        pass

    try:
        from lightgbm import LGBMClassifier, LGBMRegressor
        clf_map["lightgbm"] = LGBMClassifier(
            n_estimators=100, random_state=42, n_jobs=-1,
            class_weight=cw, verbose=-1,
        )
        reg_map["lightgbm"] = LGBMRegressor(
            n_estimators=100, random_state=42, n_jobs=-1, verbose=-1,
        )
    except ImportError:
        pass

    # Hyperparameter grids for tuning
    clf_param_grids: dict[str, dict] = {
        "logistic_regression": {"C": [0.01, 0.1, 1.0, 10.0]},
        "random_forest": {
            "n_estimators": [50, 100, 200],
            "max_depth": [5, 10, 20, None],
            "min_samples_split": [2, 5, 10],
        },
        "gradient_boosting": {
            "n_estimators": [50, 100, 200],
            "max_depth": [3, 5, 7],
            "learning_rate": [0.01, 0.1, 0.2],
        },
        "svm": {"C": [0.1, 1.0, 10.0]},
        "extra_trees": {
            "n_estimators": [100, 200, 300],
            "max_depth": [5, 10, 15, None],
            "min_samples_split": [2, 5],
        },
        "knn": {
            "n_neighbors": [3, 5, 7, 11],
            "weights": ["uniform", "distance"],
            "metric": ["euclidean", "manhattan"],
        },
        "xgboost": {
            "n_estimators": [50, 100, 200],
            "max_depth": [3, 5, 7],
            "learning_rate": [0.01, 0.1, 0.2],
        },
        "lightgbm": {
            "n_estimators": [50, 100, 200],
            "max_depth": [3, 5, 7, -1],
            "learning_rate": [0.01, 0.1, 0.2],
        },
    }
    reg_param_grids: dict[str, dict] = {
        "logistic_regression": {},
        "random_forest": {
            "n_estimators": [50, 100, 200],
            "max_depth": [5, 10, 20, None],
            "min_samples_split": [2, 5, 10],
        },
        "gradient_boosting": {
            "n_estimators": [50, 100, 200],
            "max_depth": [3, 5, 7],
            "learning_rate": [0.01, 0.1, 0.2],
        },
        "svm": {"C": [0.1, 1.0, 10.0]},
        "extra_trees": {
            "n_estimators": [100, 200, 300],
            "max_depth": [5, 10, 15, None],
            "min_samples_split": [2, 5],
        },
        "knn": {
            "n_neighbors": [3, 5, 7, 11],
            "weights": ["uniform", "distance"],
            "metric": ["euclidean", "manhattan"],
        },
        "xgboost": {
            "n_estimators": [50, 100, 200],
            "max_depth": [3, 5, 7],
            "learning_rate": [0.01, 0.1, 0.2],
        },
        "lightgbm": {
            "n_estimators": [50, 100, 200],
            "max_depth": [3, 5, 7, -1],
            "learning_rate": [0.01, 0.1, 0.2],
        },
    }

    model_factory = clf_map if is_clf else reg_map
    param_grids = clf_param_grids if is_clf else reg_param_grids
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

        # Hyperparameter tuning via RandomizedSearchCV
        if tune_hyperparams and param_grids.get(mt):
            from sklearn.model_selection import RandomizedSearchCV
            grid = param_grids[mt]
            n_iter = min(10, max(1, _param_combinations(grid)))
            scoring = "f1_weighted" if is_clf else "r2"
            try:
                search = RandomizedSearchCV(
                    model, grid, n_iter=n_iter, cv=3, scoring=scoring,
                    random_state=42, n_jobs=-1, error_score="raise",
                )
                search.fit(X_train, y_train)
                model = search.best_estimator_
            except Exception:
                try:
                    model.fit(X_train, y_train)
                except Exception:
                    results.append(
                        ModelResult(
                            model_name=mt, model_type=mt,
                            metrics={"error": -1.0}, best=False,
                        )
                    )
                    continue
        else:
            try:
                model.fit(X_train, y_train)
            except Exception:
                results.append(
                    ModelResult(
                        model_name=mt, model_type=mt,
                        metrics={"error": -1.0}, best=False,
                    )
                )
                continue

        # Probabilities for AUC-ROC and threshold selection
        proba_fn = getattr(model, "predict_proba", None)
        y_proba_train = proba_fn(X_train) if proba_fn else None
        y_proba_val = proba_fn(X_val) if proba_fn else None
        y_proba_test = proba_fn(X_test) if proba_fn else None

        # Determine classification threshold
        model_threshold = 0.5
        threshold_info: dict[str, Any] = {"threshold": 0.5, "method": "default"}
        if is_clf and y.nunique() == 2:
            if threshold is not None:
                model_threshold = threshold
                threshold_info = {"threshold": threshold, "method": "user_specified"}
            elif y_proba_val is not None:
                threshold_info = _find_optimal_threshold(y_val, y_proba_val)
                model_threshold = threshold_info["threshold"]

        # Predictions on all splits (using threshold for binary classification)
        if is_clf and y.nunique() == 2 and model_threshold != 0.5 and proba_fn:
            y_pred_train = (y_proba_train[:, 1] >= model_threshold).astype(int)
            y_pred_val = (y_proba_val[:, 1] >= model_threshold).astype(int)
            y_pred_test = (y_proba_test[:, 1] >= model_threshold).astype(int)
        else:
            y_pred_train = model.predict(X_train)
            y_pred_val = model.predict(X_val)
            y_pred_test = model.predict(X_test)

        model_path = str(out_dir / f"{mt}.joblib")
        joblib.dump(model, model_path)

        # Save feature names and threshold for later use
        feature_names_path = str(out_dir / f"{mt}_features.joblib")
        joblib.dump(list(X.columns), feature_names_path)
        threshold_path = str(out_dir / f"{mt}_threshold.joblib")
        joblib.dump(threshold_info, threshold_path)

        # Compute metrics for train, validation, and test sets
        train_m = _compute_metrics(y_train, y_pred_train, is_clf, y, y_proba_train)
        val_m = _compute_metrics(y_val, y_pred_val, is_clf, y, y_proba_val)
        test_m = _compute_metrics(y_test, y_pred_test, is_clf, y, y_proba_test)

        # Overfit/underfit detection
        diagnostics = _detect_fit_issues(train_m, test_m, is_clf)
        diagnostics["threshold_info"] = threshold_info

        # Use validation score for model selection (unbiased)
        score = val_m.get("f1", val_m.get("r2", 0.0))

        if score > best_score:
            best_score = score
            best_idx = len(results)

        results.append(
            ModelResult(
                model_name=mt,
                model_type=mt,
                metrics=test_m,
                train_metrics=train_m,
                val_metrics=val_m,
                diagnostics=diagnostics,
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
    tree_models = ("RandomForest", "GradientBoosting", "ExtraTrees", "XGB", "LGBM", "DecisionTree")
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


def calibration_analysis(
    model_path: str,
    data_path: str,
    target_col: str,
    output_dir: str,
) -> CalibrationResult:
    """Compute calibration metrics and generate a reliability diagram.

    Returns a CalibrationResult with Brier score, calibration status, and plot path.
    """
    import joblib
    from sklearn.calibration import calibration_curve
    from sklearn.metrics import brier_score_loss

    model = joblib.load(model_path)
    data_file = _validate_path(data_path)
    df = _read_df(data_file)
    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    X = df.drop(columns=[target_col], errors="ignore")
    y = df[target_col]

    # Auto-encode categorical features (same as training)
    cat_cols = X.select_dtypes(include=["object", "category"]).columns.tolist()
    if cat_cols:
        X = pd.get_dummies(X, columns=cat_cols, drop_first=True, dtype=float)
    X = X.fillna(X.median(numeric_only=True))

    # Encode target if non-numeric
    if not pd.api.types.is_numeric_dtype(y):
        from sklearn.preprocessing import LabelEncoder
        y = pd.Series(LabelEncoder().fit_transform(y.fillna("__missing__")), index=y.index)

    # Align features with training
    features_path = model_path.replace(".joblib", "_features.joblib")
    if Path(features_path).exists():
        saved_features = joblib.load(features_path)
        for col in saved_features:
            if col not in X.columns:
                X[col] = 0
        X = X[saved_features]

    # Get predicted probabilities
    if not hasattr(model, "predict_proba"):
        return CalibrationResult(
            brier_score=1.0,
            is_well_calibrated=False,
            reliability_plot_path=None,
        )

    y_proba = model.predict_proba(X)[:, 1]

    # Compute Brier score
    brier = float(brier_score_loss(y, y_proba))

    # Generate reliability diagram
    fraction_of_positives, mean_predicted_value = calibration_curve(
        y, y_proba, n_bins=10, strategy="uniform",
    )

    plot_path = str(out_dir / "calibration_reliability.png")
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 10), gridspec_kw={"height_ratios": [3, 1]})

    # Reliability curve
    ax1.plot([0, 1], [0, 1], "k--", label="Perfectly calibrated")
    ax1.plot(mean_predicted_value, fraction_of_positives, "s-", label="Model")
    ax1.set_xlabel("Mean predicted probability")
    ax1.set_ylabel("Fraction of positives")
    ax1.set_title(f"Reliability Diagram (Brier={brier:.4f})")
    ax1.legend(loc="lower right")
    ax1.set_xlim([0, 1])
    ax1.set_ylim([0, 1])

    # Histogram of predictions
    ax2.hist(y_proba, bins=20, range=(0, 1), edgecolor="black", alpha=0.7)
    ax2.set_xlabel("Predicted probability")
    ax2.set_ylabel("Count")
    ax2.set_title("Prediction Distribution")

    plt.tight_layout()
    plt.savefig(plot_path, dpi=150, bbox_inches="tight")
    plt.close("all")

    return CalibrationResult(
        brier_score=round(brier, 6),
        is_well_calibrated=brier < 0.1,
        reliability_plot_path=plot_path,
    )


def learning_curve_analysis(
    model_path: str,
    data_path: str,
    target_col: str,
    output_dir: str,
) -> LearningCurveResult:
    """Generate learning curves to diagnose bias/variance issues.

    Returns a LearningCurveResult with train/test scores across training sizes and a diagnosis.
    """
    import joblib
    from sklearn.model_selection import learning_curve as sk_learning_curve

    model = joblib.load(model_path)
    data_file = _validate_path(data_path)
    df = _read_df(data_file)
    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    X = df.drop(columns=[target_col], errors="ignore")
    y = df[target_col]

    # Auto-encode categorical features (same as training)
    cat_cols = X.select_dtypes(include=["object", "category"]).columns.tolist()
    if cat_cols:
        X = pd.get_dummies(X, columns=cat_cols, drop_first=True, dtype=float)
    X = X.fillna(X.median(numeric_only=True))

    # Encode target if non-numeric
    if not pd.api.types.is_numeric_dtype(y):
        from sklearn.preprocessing import LabelEncoder
        y = pd.Series(LabelEncoder().fit_transform(y.fillna("__missing__")), index=y.index)

    # Align features with training
    features_path = model_path.replace(".joblib", "_features.joblib")
    if Path(features_path).exists():
        saved_features = joblib.load(features_path)
        for col in saved_features:
            if col not in X.columns:
                X[col] = 0
        X = X[saved_features]

    is_clf = _is_classification(y)
    scoring = "f1_weighted" if is_clf else "r2"

    # Compute learning curves with 5 training sizes
    train_sizes_frac = np.linspace(0.2, 1.0, 5)
    train_sizes_abs, train_scores, test_scores = sk_learning_curve(
        model, X, y,
        train_sizes=train_sizes_frac,
        cv=5,
        scoring=scoring,
        n_jobs=-1,
        random_state=42,
    )

    train_mean = train_scores.mean(axis=1)
    train_std = train_scores.std(axis=1)
    test_mean = test_scores.mean(axis=1)
    test_std = test_scores.std(axis=1)

    # Generate plot
    plot_path = str(out_dir / "learning_curve.png")
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.fill_between(
        train_sizes_abs, train_mean - train_std, train_mean + train_std, alpha=0.1, color="blue",
    )
    ax.fill_between(
        train_sizes_abs, test_mean - test_std, test_mean + test_std, alpha=0.1, color="orange",
    )
    ax.plot(train_sizes_abs, train_mean, "o-", color="blue", label="Training score")
    ax.plot(train_sizes_abs, test_mean, "o-", color="orange", label="Cross-validation score")
    ax.set_xlabel("Training Set Size")
    ax.set_ylabel(scoring.replace("_", " ").title())
    ax.set_title("Learning Curve")
    ax.legend(loc="best")
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(plot_path, dpi=150, bbox_inches="tight")
    plt.close("all")

    # Diagnose bias/variance
    final_gap = float(train_mean[-1] - test_mean[-1])
    final_test = float(test_mean[-1])
    if final_gap > 0.10:
        diagnosis = (
            f"High variance (overfitting): train-test gap={final_gap:.4f}. "
            "Consider more training data, regularization, or simpler model."
        )
    elif final_test < 0.60:
        diagnosis = (
            f"High bias (underfitting): test score={final_test:.4f}. "
            "Consider more features, less regularization, or a more complex model."
        )
    else:
        diagnosis = (
            f"Good fit: test score={final_test:.4f}, gap={final_gap:.4f}. "
            "Model generalizes well."
        )

    return LearningCurveResult(
        train_sizes=[int(s) for s in train_sizes_abs],
        train_scores_mean=[round(float(s), 4) for s in train_mean],
        test_scores_mean=[round(float(s), 4) for s in test_mean],
        plot_path=plot_path,
        diagnosis=diagnosis,
    )


def generate_model_card(
    model_path: str,
    data_path: str,
    target_col: str,
    model_result: ModelResult,
) -> ModelCard:
    """Generate a model card summarizing architecture, performance, and usage guidance.

    Returns a ModelCard with key metadata for model documentation and governance.
    """
    import joblib

    model = joblib.load(model_path)
    data_file = _validate_path(data_path)
    df = _read_df(data_file)

    # Extract architecture info
    architecture = type(model).__name__

    # Extract hyperparameters
    hyperparams: dict[str, Any] = {}
    if hasattr(model, "get_params"):
        raw_params = model.get_params(deep=False)
        # Filter to serializable values only
        for k, v in raw_params.items():
            if isinstance(v, (str, int, float, bool, type(None))):
                hyperparams[k] = v

    # Performance metrics (from model_result)
    performance = dict(model_result.metrics)

    # Top features from feature importance
    top_features: list[dict[str, Any]] = []
    features_path = model_path.replace(".joblib", "_features.joblib")
    if Path(features_path).exists():
        saved_features = joblib.load(features_path)
        fi = feature_importance(model_path, saved_features)
        top_features = fi[:10]  # top 10 features

    # Limitations
    limitations: list[str] = []
    n_rows, n_cols = df.shape
    if n_rows < 1000:
        limitations.append(f"Small training set ({n_rows} rows) — results may not generalize.")
    if n_cols > 100:
        limitations.append(
            f"High dimensionality ({n_cols} features) — risk of spurious correlations."
        )

    diagnostics = model_result.diagnostics
    if diagnostics.get("status") == "overfitting":
        limitations.append(
            f"Overfitting detected: {diagnostics.get('message', 'train-test gap > 0.10')}."
        )
    elif diagnostics.get("status") == "underfitting":
        limitations.append(
            f"Underfitting detected: {diagnostics.get('message', 'low scores on both sets')}."
        )

    # Check for class imbalance
    y = df[target_col] if target_col in df.columns else pd.Series(dtype=object)
    if _is_classification(y) and y.nunique() >= 2:
        counts = y.value_counts()
        minority_ratio = counts.min() / counts.max()
        if minority_ratio < 0.2:
            limitations.append(
                f"Class imbalance: minority ratio={minority_ratio:.2f}. "
                "Metrics may be inflated for majority class."
            )

    # Intended use
    is_clf = _is_classification(y) if len(y) > 0 else True
    task_type = "classification" if is_clf else "regression"
    intended_use = (
        f"Binary {task_type} for predicting '{target_col}'. "
        "Designed for VC portfolio company analysis including churn, expansion, "
        "cross-sell, and upsell opportunities."
    )

    # Training data summary
    training_data_summary = (
        f"{n_rows} rows, {n_cols} columns. "
        f"Target: '{target_col}' ({y.nunique()} unique values). "
        f"File: {data_file.name}."
    )

    return ModelCard(
        model_name=model_result.model_name,
        architecture=architecture,
        hyperparameters=hyperparams,
        performance=performance,
        top_features=top_features,
        limitations=limitations,
        intended_use=intended_use,
        training_data_summary=training_data_summary,
    )
