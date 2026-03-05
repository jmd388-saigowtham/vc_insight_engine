"""EDA plots — distribution, correlation, scatter, box, and target analysis charts."""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend — must be set before pyplot import
import matplotlib.pyplot as plt
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


def _ensure_dir(path: str) -> Path:
    p = Path(path).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class PlotResult(BaseModel):
    success: bool
    plot_path: str
    plot_type: str
    description: str
    errors: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def distribution_plot(
    file_path: str,
    column: str,
    output_path: str,
) -> PlotResult:
    """Histogram + KDE for numeric columns, bar chart for categorical."""
    try:
        path = _validate_path(file_path)
        out = _ensure_dir(output_path)
        df = _read_df(path)

        if column not in df.columns:
            return PlotResult(
                success=False,
                plot_path=output_path,
                plot_type="distribution",
                description="",
                errors=[f"Column '{column}' not found"],
            )

        fig, ax = plt.subplots(figsize=(10, 6))
        series = df[column].dropna()

        if pd.api.types.is_numeric_dtype(series):
            ax.hist(series, bins=50, density=True, alpha=0.7, color="steelblue", edgecolor="white")
            # KDE overlay
            try:
                from scipy.stats import gaussian_kde

                xs = np.linspace(series.min(), series.max(), 300)
                kde = gaussian_kde(series)
                ax.plot(xs, kde(xs), color="darkorange", linewidth=2, label="KDE")
                ax.legend()
            except Exception:
                pass
            ax.set_ylabel("Density")
            desc = f"Distribution of {column} (n={len(series)}, mean={series.mean():.2f}, std={series.std():.2f})"
        else:
            counts = series.value_counts().head(30)
            counts.plot(kind="bar", ax=ax, color="steelblue", edgecolor="white")
            ax.set_ylabel("Count")
            desc = f"Value counts for {column} (top {min(30, len(counts))} of {series.nunique()} categories)"

        ax.set_title(f"Distribution: {column}")
        ax.set_xlabel(column)
        fig.tight_layout()
        fig.savefig(str(out), dpi=150)
        plt.close(fig)

        return PlotResult(
            success=True,
            plot_path=str(out),
            plot_type="distribution",
            description=desc,
        )
    except Exception as exc:
        plt.close("all")
        return PlotResult(
            success=False,
            plot_path=output_path,
            plot_type="distribution",
            description="",
            errors=[str(exc)],
        )


def correlation_matrix(
    file_path: str,
    columns: list[str] | None,
    output_path: str,
) -> PlotResult:
    """Heatmap of the Pearson correlation matrix."""
    try:
        path = _validate_path(file_path)
        out = _ensure_dir(output_path)
        df = _read_df(path)

        if columns:
            missing = [c for c in columns if c not in df.columns]
            if missing:
                return PlotResult(
                    success=False,
                    plot_path=output_path,
                    plot_type="correlation",
                    description="",
                    errors=[f"Columns not found: {missing}"],
                )
            numeric_df = df[columns].select_dtypes(include="number")
        else:
            numeric_df = df.select_dtypes(include="number")

        if numeric_df.shape[1] < 2:
            return PlotResult(
                success=False,
                plot_path=output_path,
                plot_type="correlation",
                description="",
                errors=["Need at least 2 numeric columns for a correlation matrix"],
            )

        corr = numeric_df.corr()
        n = len(corr)
        fig_size = max(8, n * 0.6)
        fig, ax = plt.subplots(figsize=(fig_size, fig_size))

        cmap = plt.cm.RdBu_r
        im = ax.imshow(corr.values, cmap=cmap, vmin=-1, vmax=1, aspect="auto")
        fig.colorbar(im, ax=ax, shrink=0.8)

        ax.set_xticks(range(n))
        ax.set_yticks(range(n))
        ax.set_xticklabels(corr.columns, rotation=45, ha="right", fontsize=8)
        ax.set_yticklabels(corr.columns, fontsize=8)

        # Annotate cells
        if n <= 20:
            for i in range(n):
                for j in range(n):
                    val = corr.values[i, j]
                    color = "white" if abs(val) > 0.6 else "black"
                    ax.text(j, i, f"{val:.2f}", ha="center", va="center", fontsize=7, color=color)

        ax.set_title("Correlation Matrix")
        fig.tight_layout()
        fig.savefig(str(out), dpi=150)
        plt.close(fig)

        return PlotResult(
            success=True,
            plot_path=str(out),
            plot_type="correlation",
            description=f"Correlation matrix for {n} numeric columns",
        )
    except Exception as exc:
        plt.close("all")
        return PlotResult(
            success=False,
            plot_path=output_path,
            plot_type="correlation",
            description="",
            errors=[str(exc)],
        )


def scatter_plot(
    file_path: str,
    x: str,
    y: str,
    hue: str | None,
    output_path: str,
) -> PlotResult:
    """Scatter plot with optional colour grouping."""
    try:
        path = _validate_path(file_path)
        out = _ensure_dir(output_path)
        df = _read_df(path)

        for col in [x, y] + ([hue] if hue else []):
            if col not in df.columns:
                return PlotResult(
                    success=False,
                    plot_path=output_path,
                    plot_type="scatter",
                    description="",
                    errors=[f"Column '{col}' not found"],
                )

        fig, ax = plt.subplots(figsize=(10, 7))

        if hue and hue in df.columns:
            groups = df[hue].unique()
            colors = plt.cm.tab10(np.linspace(0, 1, min(len(groups), 10)))
            for i, group in enumerate(groups[:10]):
                mask = df[hue] == group
                ax.scatter(
                    df.loc[mask, x],
                    df.loc[mask, y],
                    alpha=0.6,
                    s=20,
                    color=colors[i],
                    label=str(group),
                )
            ax.legend(title=hue, fontsize=8, loc="best")
            desc = f"Scatter plot: {x} vs {y}, coloured by {hue}"
        else:
            ax.scatter(df[x], df[y], alpha=0.6, s=20, color="steelblue")
            desc = f"Scatter plot: {x} vs {y}"

        ax.set_xlabel(x)
        ax.set_ylabel(y)
        ax.set_title(f"{x} vs {y}")
        fig.tight_layout()
        fig.savefig(str(out), dpi=150)
        plt.close(fig)

        return PlotResult(
            success=True,
            plot_path=str(out),
            plot_type="scatter",
            description=desc,
        )
    except Exception as exc:
        plt.close("all")
        return PlotResult(
            success=False,
            plot_path=output_path,
            plot_type="scatter",
            description="",
            errors=[str(exc)],
        )


def box_plot(
    file_path: str,
    column: str,
    group_by: str | None,
    output_path: str,
) -> PlotResult:
    """Box plot, optionally grouped by a categorical column."""
    try:
        path = _validate_path(file_path)
        out = _ensure_dir(output_path)
        df = _read_df(path)

        for col in [column] + ([group_by] if group_by else []):
            if col not in df.columns:
                return PlotResult(
                    success=False,
                    plot_path=output_path,
                    plot_type="box",
                    description="",
                    errors=[f"Column '{col}' not found"],
                )

        fig, ax = plt.subplots(figsize=(10, 6))

        if group_by:
            groups = df[group_by].dropna().unique()
            data = [df.loc[df[group_by] == g, column].dropna().values for g in groups]
            bp = ax.boxplot(data, labels=[str(g) for g in groups], patch_artist=True)
            for patch in bp["boxes"]:
                patch.set_facecolor("steelblue")
                patch.set_alpha(0.7)
            ax.set_xlabel(group_by)
            if len(groups) > 10:
                plt.xticks(rotation=45, ha="right")
            desc = f"Box plot of {column} grouped by {group_by} ({len(groups)} groups)"
        else:
            bp = ax.boxplot([df[column].dropna().values], labels=[column], patch_artist=True)
            bp["boxes"][0].set_facecolor("steelblue")
            bp["boxes"][0].set_alpha(0.7)
            desc = f"Box plot of {column}"

        ax.set_ylabel(column)
        ax.set_title(f"Box Plot: {column}")
        fig.tight_layout()
        fig.savefig(str(out), dpi=150)
        plt.close(fig)

        return PlotResult(
            success=True,
            plot_path=str(out),
            plot_type="box",
            description=desc,
        )
    except Exception as exc:
        plt.close("all")
        return PlotResult(
            success=False,
            plot_path=output_path,
            plot_type="box",
            description="",
            errors=[str(exc)],
        )


def target_analysis(
    file_path: str,
    target: str,
    features: list[str],
    output_dir: str,
) -> list[PlotResult]:
    """Generate a suite of plots analysing features vs the target variable."""
    try:
        path = _validate_path(file_path)
        df = _read_df(path)
        out_dir = Path(output_dir).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)

        if target not in df.columns:
            return [
                PlotResult(
                    success=False,
                    plot_path="",
                    plot_type="target_analysis",
                    description="",
                    errors=[f"Target column '{target}' not found"],
                )
            ]

        results: list[PlotResult] = []
        target_is_numeric = pd.api.types.is_numeric_dtype(df[target])

        for feat in features:
            if feat not in df.columns:
                results.append(
                    PlotResult(
                        success=False,
                        plot_path="",
                        plot_type="target_analysis",
                        description="",
                        errors=[f"Feature '{feat}' not found"],
                    )
                )
                continue

            feat_is_numeric = pd.api.types.is_numeric_dtype(df[feat])
            plot_path = str(out_dir / f"target_{target}_vs_{feat}.png")

            if feat_is_numeric and target_is_numeric:
                # Scatter
                results.append(
                    scatter_plot(file_path, feat, target, None, plot_path)
                )
            elif feat_is_numeric and not target_is_numeric:
                # Box plot of feature grouped by target
                results.append(
                    box_plot(file_path, feat, target, plot_path)
                )
            elif not feat_is_numeric and target_is_numeric:
                # Box plot of target grouped by feature
                results.append(
                    box_plot(file_path, target, feat, plot_path)
                )
            else:
                # Both categorical — stacked bar
                try:
                    fig, ax = plt.subplots(figsize=(10, 6))
                    ct = pd.crosstab(df[feat], df[target], normalize="index")
                    ct.head(20).plot(kind="bar", stacked=True, ax=ax, colormap="tab10")
                    ax.set_title(f"{feat} vs {target}")
                    ax.set_ylabel("Proportion")
                    ax.legend(title=target, fontsize=8)
                    fig.tight_layout()
                    fig.savefig(plot_path, dpi=150)
                    plt.close(fig)
                    results.append(
                        PlotResult(
                            success=True,
                            plot_path=plot_path,
                            plot_type="stacked_bar",
                            description=f"Stacked bar: {feat} vs {target}",
                        )
                    )
                except Exception as exc:
                    plt.close("all")
                    results.append(
                        PlotResult(
                            success=False,
                            plot_path=plot_path,
                            plot_type="stacked_bar",
                            description="",
                            errors=[str(exc)],
                        )
                    )

        return results
    except Exception as exc:
        plt.close("all")
        return [
            PlotResult(
                success=False,
                plot_path="",
                plot_type="target_analysis",
                description="",
                errors=[str(exc)],
            )
        ]
