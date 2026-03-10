"""Shared Pydantic models used across VC Engine MCP tool servers."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TableInfo(BaseModel):
    file_id: str
    filename: str
    row_count: int
    column_count: int
    columns: list[str]


class ColumnProfile(BaseModel):
    column_name: str
    dtype: str
    null_count: int
    null_pct: float
    unique_count: int
    min_value: str | None = None
    max_value: str | None = None
    mean_value: float | None = None
    sample_values: list[Any] = Field(default_factory=list)


class MergePlan(BaseModel):
    left_table: str
    right_table: str
    left_key: str
    right_key: str
    merge_type: str = "left"
    confidence: float = 0.0
    rationale: str = ""


class Recommendation(BaseModel):
    opportunity_type: str  # churn, expansion, cross_sell, upsell
    title: str
    description: str
    confidence: float
    key_metrics: list[str] = Field(default_factory=list)
    required_columns: list[str] = Field(default_factory=list)


class TargetInfo(BaseModel):
    column_name: str
    target_type: str  # binary, multiclass, regression
    positive_label: str | None = None
    class_distribution: dict[str, int] = Field(default_factory=dict)


class Hypothesis(BaseModel):
    id: str
    statement: str
    test_type: str  # t_test, chi_square, correlation, anova
    variables: list[str]
    expected_outcome: str


class HypothesisResult(BaseModel):
    hypothesis_id: str
    test_statistic: float
    p_value: float
    conclusion: str  # supported, rejected, inconclusive
    details: dict[str, Any] = Field(default_factory=dict)


class Feature(BaseModel):
    name: str
    original_column: str | None = None
    transform: str | None = None  # log, square, interaction, binned, encoded
    importance: float = 0.0


class ModelResult(BaseModel):
    model_name: str
    model_type: str  # logistic_regression, random_forest, gradient_boosting, xgboost
    metrics: dict[str, float]  # test set: accuracy, precision, recall, f1, auc
    train_metrics: dict[str, float] = Field(default_factory=dict)
    val_metrics: dict[str, float] = Field(default_factory=dict)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    best: bool = False
    model_path: str | None = None


class ShapResult(BaseModel):
    summary_plot_path: str
    feature_importance: list[dict[str, Any]]
    waterfall_plots: list[str] = Field(default_factory=list)


class Report(BaseModel):
    title: str
    executive_summary: str
    key_findings: list[str]
    recommendations: list[str]
    report_path: str | None = None


class CalibrationResult(BaseModel):
    brier_score: float
    is_well_calibrated: bool
    reliability_plot_path: str | None = None


class LearningCurveResult(BaseModel):
    train_sizes: list[int]
    train_scores_mean: list[float]
    test_scores_mean: list[float]
    plot_path: str | None = None
    diagnosis: str = ""


class ModelCard(BaseModel):
    model_name: str
    architecture: str
    hyperparameters: dict[str, Any] = Field(default_factory=dict)
    performance: dict[str, float] = Field(default_factory=dict)
    top_features: list[dict[str, Any]] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    intended_use: str = ""
    training_data_summary: str = ""


class CodeExecutionResult(BaseModel):
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    execution_time: float = 0.0
    files_created: list[str] = Field(default_factory=list)
