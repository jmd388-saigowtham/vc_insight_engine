"""Tests for the modeling_explain MCP server — tuning, 3-way split, diagnostics, leakage."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Make MCP servers and shared package importable
_mcp_root = str(Path(__file__).resolve().parents[3] / "packages" / "mcp-servers")
_shared_root = str(Path(__file__).resolve().parents[3] / "packages")
if _mcp_root not in sys.path:
    sys.path.insert(0, _mcp_root)
if _shared_root not in sys.path:
    sys.path.insert(0, _shared_root)

from src.modeling_explain.server import (
    ModelResult,
    detect_leakage,
    train,
)


@pytest.fixture()
def binary_csv(tmp_path: Path) -> str:
    """Create a simple binary classification CSV."""
    rng = np.random.default_rng(42)
    n = 200
    df = pd.DataFrame({
        "feat_a": rng.normal(0, 1, n),
        "feat_b": rng.normal(5, 2, n),
        "feat_c": rng.normal(-1, 0.5, n),
        "target": rng.choice([0, 1], size=n),
    })
    path = str(tmp_path / "binary.csv")
    df.to_csv(path, index=False)
    return path


@pytest.fixture()
def imbalanced_csv(tmp_path: Path) -> str:
    """CSV with heavy class imbalance (5% minority)."""
    rng = np.random.default_rng(42)
    n = 400
    target = np.concatenate([np.zeros(380), np.ones(20)])
    rng.shuffle(target)
    df = pd.DataFrame({
        "feat_a": rng.normal(0, 1, n),
        "feat_b": rng.normal(5, 2, n),
        "target": target.astype(int),
    })
    path = str(tmp_path / "imbalanced.csv")
    df.to_csv(path, index=False)
    return path


@pytest.fixture()
def leaky_csv(tmp_path: Path) -> str:
    """CSV with a feature that perfectly correlates with target."""
    rng = np.random.default_rng(42)
    n = 100
    target = rng.choice([0, 1], size=n)
    df = pd.DataFrame({
        "clean_feat": rng.normal(0, 1, n),
        "leaky_feat": target + rng.normal(0, 0.01, n),  # near-perfect correlation
        "target": target,
    })
    path = str(tmp_path / "leaky.csv")
    df.to_csv(path, index=False)
    return path


class TestTrain:
    """Test the train() function."""

    def test_train_returns_model_results(self, binary_csv: str, tmp_path: Path):
        results = train(
            data_path=binary_csv,
            target_col="target",
            model_types=["logistic_regression"],
            output_dir=str(tmp_path / "models"),
            tune_hyperparams=False,
        )
        assert len(results) == 1
        assert isinstance(results[0], ModelResult)
        assert results[0].best is True
        assert results[0].model_name == "logistic_regression"

    def test_train_multiple_models(self, binary_csv: str, tmp_path: Path):
        results = train(
            data_path=binary_csv,
            target_col="target",
            model_types=["logistic_regression", "random_forest"],
            output_dir=str(tmp_path / "models"),
            tune_hyperparams=False,
        )
        assert len(results) == 2
        best_count = sum(1 for r in results if r.best)
        assert best_count == 1

    def test_train_metrics_keys(self, binary_csv: str, tmp_path: Path):
        results = train(
            data_path=binary_csv,
            target_col="target",
            model_types=["logistic_regression"],
            output_dir=str(tmp_path / "models"),
            tune_hyperparams=False,
        )
        r = results[0]
        # Test metrics (main metrics dict)
        assert "accuracy" in r.metrics
        assert "f1" in r.metrics
        assert "precision" in r.metrics
        assert "recall" in r.metrics

    def test_train_metrics_have_train_val_test(self, binary_csv: str, tmp_path: Path):
        """3-way split produces train, val, and test metrics."""
        results = train(
            data_path=binary_csv,
            target_col="target",
            model_types=["logistic_regression"],
            output_dir=str(tmp_path / "models"),
            tune_hyperparams=False,
        )
        r = results[0]
        assert r.train_metrics, "train_metrics should be populated"
        assert r.val_metrics, "val_metrics should be populated"
        assert "accuracy" in r.train_metrics
        assert "accuracy" in r.val_metrics

    def test_train_diagnostics_populated(self, binary_csv: str, tmp_path: Path):
        results = train(
            data_path=binary_csv,
            target_col="target",
            model_types=["logistic_regression"],
            output_dir=str(tmp_path / "models"),
            tune_hyperparams=False,
        )
        r = results[0]
        assert r.diagnostics, "diagnostics should be populated"
        assert r.diagnostics["status"] in ("good_fit", "overfitting", "underfitting")
        assert "message" in r.diagnostics
        assert "train_test_gap" in r.diagnostics

    def test_train_with_tuning(self, binary_csv: str, tmp_path: Path):
        """Hyperparameter tuning via RandomizedSearchCV should not crash."""
        results = train(
            data_path=binary_csv,
            target_col="target",
            model_types=["logistic_regression"],
            output_dir=str(tmp_path / "models"),
            tune_hyperparams=True,
        )
        assert len(results) == 1
        assert results[0].metrics.get("accuracy", 0) > 0

    def test_train_with_selected_features(self, binary_csv: str, tmp_path: Path):
        results = train(
            data_path=binary_csv,
            target_col="target",
            model_types=["logistic_regression"],
            output_dir=str(tmp_path / "models"),
            selected_features=["feat_a"],
            tune_hyperparams=False,
        )
        assert len(results) == 1

    def test_train_saves_model_file(self, binary_csv: str, tmp_path: Path):
        models_dir = tmp_path / "models"
        results = train(
            data_path=binary_csv,
            target_col="target",
            model_types=["logistic_regression"],
            output_dir=str(models_dir),
            tune_hyperparams=False,
        )
        assert results[0].model_path
        assert Path(results[0].model_path).exists()

    def test_train_invalid_target_raises(self, binary_csv: str, tmp_path: Path):
        with pytest.raises(ValueError, match="not found"):
            train(
                data_path=binary_csv,
                target_col="nonexistent",
                model_types=["logistic_regression"],
                output_dir=str(tmp_path / "models"),
            )

    def test_train_unknown_model_type(self, binary_csv: str, tmp_path: Path):
        results = train(
            data_path=binary_csv,
            target_col="target",
            model_types=["unknown_model"],
            output_dir=str(tmp_path / "models"),
        )
        assert len(results) == 1
        assert results[0].metrics.get("error") == -1.0

    def test_train_class_imbalance_handling(self, imbalanced_csv: str, tmp_path: Path):
        """Imbalanced dataset should use balanced class weights."""
        results = train(
            data_path=imbalanced_csv,
            target_col="target",
            model_types=["logistic_regression", "random_forest"],
            output_dir=str(tmp_path / "models"),
            tune_hyperparams=False,
        )
        # Should not crash with imbalanced data
        assert len(results) == 2
        for r in results:
            assert r.metrics.get("accuracy", 0) >= 0


class TestThresholdSelection:
    """Test classification threshold selection."""

    def test_optimal_threshold_computed(self, binary_csv: str, tmp_path: Path):
        """When no threshold is specified, optimal is computed via PR curve."""
        results = train(
            data_path=binary_csv,
            target_col="target",
            model_types=["logistic_regression"],
            output_dir=str(tmp_path / "models"),
            tune_hyperparams=False,
        )
        r = results[0]
        assert r.diagnostics is not None
        assert "threshold_info" in r.diagnostics
        info = r.diagnostics["threshold_info"]
        assert 0.0 < info["threshold"] <= 1.0
        assert info["method"] in ("precision_recall_curve", "default")

    def test_user_specified_threshold(self, binary_csv: str, tmp_path: Path):
        """When threshold is explicitly set, it should be used."""
        results = train(
            data_path=binary_csv,
            target_col="target",
            model_types=["logistic_regression"],
            output_dir=str(tmp_path / "models"),
            tune_hyperparams=False,
            threshold=0.3,
        )
        r = results[0]
        assert r.diagnostics is not None
        info = r.diagnostics["threshold_info"]
        assert info["threshold"] == 0.3
        assert info["method"] == "user_specified"

    def test_threshold_saved_to_disk(self, binary_csv: str, tmp_path: Path):
        """Threshold info should be saved alongside model."""
        import joblib

        models_dir = tmp_path / "models"
        train(
            data_path=binary_csv,
            target_col="target",
            model_types=["logistic_regression"],
            output_dir=str(models_dir),
            tune_hyperparams=False,
        )
        threshold_path = models_dir / "logistic_regression_threshold.joblib"
        assert threshold_path.exists()
        info = joblib.load(str(threshold_path))
        assert "threshold" in info
        assert "method" in info


class TestDetectLeakage:
    """Test the detect_leakage() function."""

    def test_leakage_detected(self, leaky_csv: str):
        leaky = detect_leakage(leaky_csv, "target", threshold=0.95)
        assert len(leaky) >= 1
        leaky_names = [item["feature"] for item in leaky]
        assert "leaky_feat" in leaky_names

    def test_no_leakage_clean_data(self, binary_csv: str):
        leaky = detect_leakage(binary_csv, "target", threshold=0.95)
        assert len(leaky) == 0

    def test_leakage_missing_target_returns_empty(self, binary_csv: str):
        leaky = detect_leakage(binary_csv, "nonexistent_col")
        assert leaky == []

    def test_leakage_threshold(self, leaky_csv: str):
        # With a very low threshold, more features flagged
        leaky_low = detect_leakage(leaky_csv, "target", threshold=0.1)
        leaky_high = detect_leakage(leaky_csv, "target", threshold=0.99)
        assert len(leaky_low) >= len(leaky_high)


class TestTemporalSplit:
    """Test time-aware splitting."""

    def test_temporal_split_with_date_column(self, tmp_path: Path):
        rng = np.random.default_rng(42)
        n = 200
        dates = pd.date_range("2020-01-01", periods=n, freq="D")
        df = pd.DataFrame({
            "date": dates,
            "feat_a": rng.normal(0, 1, n),
            "feat_b": rng.normal(5, 2, n),
            "target": rng.choice([0, 1], size=n),
        })
        path = str(tmp_path / "temporal.csv")
        df.to_csv(path, index=False)

        results = train(
            data_path=path,
            target_col="target",
            model_types=["logistic_regression"],
            output_dir=str(tmp_path / "models"),
            tune_hyperparams=False,
            split_strategy="temporal",
        )
        assert len(results) == 1
        assert results[0].metrics.get("accuracy", 0) >= 0

    def test_auto_split_without_date_uses_random(self, binary_csv: str, tmp_path: Path):
        """When no date column exists, auto falls back to random split."""
        results = train(
            data_path=binary_csv,
            target_col="target",
            model_types=["logistic_regression"],
            output_dir=str(tmp_path / "models"),
            tune_hyperparams=False,
            split_strategy="auto",
        )
        assert len(results) == 1
        assert results[0].metrics.get("accuracy", 0) > 0

    def test_random_split_ignores_date(self, tmp_path: Path):
        rng = np.random.default_rng(42)
        n = 100
        df = pd.DataFrame({
            "date": pd.date_range("2020-01-01", periods=n, freq="D"),
            "feat": rng.normal(0, 1, n),
            "target": rng.choice([0, 1], size=n),
        })
        path = str(tmp_path / "with_date.csv")
        df.to_csv(path, index=False)

        results = train(
            data_path=path,
            target_col="target",
            model_types=["logistic_regression"],
            output_dir=str(tmp_path / "models"),
            tune_hyperparams=False,
            split_strategy="random",
        )
        assert len(results) == 1


class TestOverfitDetection:
    """Test overfit/underfit detection logic."""

    def test_overfitting_detection(self, tmp_path: Path):
        """Create data that will likely overfit (RF on tiny dataset)."""
        rng = np.random.default_rng(42)
        n = 50
        # Many features, few samples → likely to overfit
        df = pd.DataFrame({
            f"feat_{i}": rng.normal(0, 1, n)
            for i in range(20)
        })
        df["target"] = rng.choice([0, 1], size=n)
        path = str(tmp_path / "overfit.csv")
        df.to_csv(path, index=False)

        results = train(
            data_path=path,
            target_col="target",
            model_types=["random_forest"],
            output_dir=str(tmp_path / "models"),
            tune_hyperparams=False,
        )
        r = results[0]
        # Whether or not it actually overfits, diagnostics should be present
        assert r.diagnostics is not None
        assert r.diagnostics["status"] in ("good_fit", "overfitting", "underfitting")
        assert isinstance(r.diagnostics["train_test_gap"], float)
