"""Statistical hypothesis testing — generate, execute, and summarise tests."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from pydantic import BaseModel

from shared.python.schemas import (
    Hypothesis,
    HypothesisResult,
    TableInfo,
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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_hypotheses(
    table_info: TableInfo,
    target: str,
    context: str,
) -> list[Hypothesis]:
    """Generate statistical hypotheses based on column types and target variable.

    Uses heuristics to propose tests:
    - Numeric feature vs binary target -> t-test
    - Categorical feature vs categorical target -> chi-square
    - Numeric feature vs numeric target -> correlation
    - Numeric feature vs multi-class target -> ANOVA
    """
    hypotheses: list[Hypothesis] = []

    # We need to infer column types from name patterns since TableInfo
    # only carries column names.  We make educated guesses.
    numeric_keywords = {
        "amount", "revenue", "count", "total", "price", "cost", "value",
        "score", "rate", "ratio", "age", "salary", "income", "quantity",
        "balance", "payment", "duration", "size", "weight", "height",
        "usage", "spend", "volume", "margin", "profit", "loss", "fee",
    }
    binary_keywords = {
        "churn", "churned", "active", "is_", "has_", "flag", "status",
        "converted", "cancelled", "default", "fraud",
    }

    target_lower = target.lower()
    target_is_binary = any(kw in target_lower for kw in binary_keywords)
    target_is_numeric = any(kw in target_lower for kw in numeric_keywords)

    for col in table_info.columns:
        if col == target:
            continue

        col_lower = col.lower()
        col_is_numeric = any(kw in col_lower for kw in numeric_keywords)
        col_is_categorical = not col_is_numeric

        if col_is_numeric and target_is_binary:
            hypotheses.append(
                Hypothesis(
                    id=uuid.uuid4().hex[:8],
                    statement=f"There is a significant difference in {col} between {target} groups",
                    test_type="t_test",
                    variables=[col, target],
                    expected_outcome=f"Higher {col} is associated with positive {target}",
                )
            )
        elif col_is_categorical and (target_is_binary or not target_is_numeric):
            hypotheses.append(
                Hypothesis(
                    id=uuid.uuid4().hex[:8],
                    statement=f"{col} and {target} are not independent",
                    test_type="chi_square",
                    variables=[col, target],
                    expected_outcome=f"Certain {col} categories are associated with {target} outcomes",
                )
            )
        elif col_is_numeric and target_is_numeric:
            hypotheses.append(
                Hypothesis(
                    id=uuid.uuid4().hex[:8],
                    statement=f"There is a significant correlation between {col} and {target}",
                    test_type="correlation",
                    variables=[col, target],
                    expected_outcome=f"{col} and {target} are positively correlated",
                )
            )
        elif col_is_numeric and not target_is_binary and not target_is_numeric:
            hypotheses.append(
                Hypothesis(
                    id=uuid.uuid4().hex[:8],
                    statement=f"{col} differs significantly across {target} groups",
                    test_type="anova",
                    variables=[col, target],
                    expected_outcome=f"At least one {target} group has a different mean {col}",
                )
            )

    # Add context-aware hypotheses if context mentions specific patterns
    context_lower = context.lower()
    if "churn" in context_lower:
        for col in table_info.columns:
            if col == target:
                continue
            if any(kw in col.lower() for kw in ("usage", "activity", "engagement", "login", "session")):
                hypotheses.append(
                    Hypothesis(
                        id=uuid.uuid4().hex[:8],
                        statement=f"Lower {col} is associated with higher churn probability",
                        test_type="t_test",
                        variables=[col, target],
                        expected_outcome=f"Churned customers have significantly lower {col}",
                    )
                )

    return hypotheses


def run_test(file_path: str, hypothesis: Hypothesis) -> HypothesisResult:
    """Execute the specified statistical test using scipy.stats."""
    from scipy import stats

    path = _validate_path(file_path)
    df = _read_df(path)

    if len(hypothesis.variables) < 2:
        return HypothesisResult(
            hypothesis_id=hypothesis.id,
            test_statistic=0.0,
            p_value=1.0,
            conclusion="inconclusive",
            details={"error": "Need at least 2 variables"},
        )

    var1, var2 = hypothesis.variables[0], hypothesis.variables[1]
    for v in [var1, var2]:
        if v not in df.columns:
            return HypothesisResult(
                hypothesis_id=hypothesis.id,
                test_statistic=0.0,
                p_value=1.0,
                conclusion="inconclusive",
                details={"error": f"Column '{v}' not found"},
            )

    alpha = 0.05
    details: dict[str, Any] = {"test_type": hypothesis.test_type, "alpha": alpha}

    try:
        if hypothesis.test_type == "t_test":
            # Split numeric variable by binary groups
            groups = df[var2].dropna().unique()
            if len(groups) < 2:
                return HypothesisResult(
                    hypothesis_id=hypothesis.id,
                    test_statistic=0.0,
                    p_value=1.0,
                    conclusion="inconclusive",
                    details={"error": f"Need at least 2 groups in '{var2}', found {len(groups)}"},
                )
            group_a = df.loc[df[var2] == groups[0], var1].dropna()
            group_b = df.loc[df[var2] == groups[1], var1].dropna()
            stat, p_value = stats.ttest_ind(group_a, group_b, equal_var=False)
            details["group_a_label"] = str(groups[0])
            details["group_b_label"] = str(groups[1])
            details["group_a_mean"] = float(group_a.mean())
            details["group_b_mean"] = float(group_b.mean())
            details["group_a_n"] = len(group_a)
            details["group_b_n"] = len(group_b)

        elif hypothesis.test_type == "chi_square":
            ct = pd.crosstab(df[var1], df[var2])
            stat, p_value, dof, expected = stats.chi2_contingency(ct)
            details["degrees_of_freedom"] = int(dof)
            details["contingency_table_shape"] = list(ct.shape)

        elif hypothesis.test_type == "correlation":
            clean = df[[var1, var2]].dropna()
            if len(clean) < 3:
                return HypothesisResult(
                    hypothesis_id=hypothesis.id,
                    test_statistic=0.0,
                    p_value=1.0,
                    conclusion="inconclusive",
                    details={"error": "Too few observations for correlation test"},
                )
            # Try Pearson first, fall back to Spearman
            try:
                stat, p_value = stats.pearsonr(clean[var1], clean[var2])
                details["method"] = "pearson"
            except Exception:
                stat, p_value = stats.spearmanr(clean[var1], clean[var2])
                details["method"] = "spearman"
            details["n"] = len(clean)

        elif hypothesis.test_type == "anova":
            groups = df[var2].dropna().unique()
            group_data = [
                df.loc[df[var2] == g, var1].dropna().values
                for g in groups
                if len(df.loc[df[var2] == g, var1].dropna()) > 0
            ]
            if len(group_data) < 2:
                return HypothesisResult(
                    hypothesis_id=hypothesis.id,
                    test_statistic=0.0,
                    p_value=1.0,
                    conclusion="inconclusive",
                    details={"error": "Need at least 2 non-empty groups for ANOVA"},
                )
            stat, p_value = stats.f_oneway(*group_data)
            details["n_groups"] = len(group_data)
        else:
            return HypothesisResult(
                hypothesis_id=hypothesis.id,
                test_statistic=0.0,
                p_value=1.0,
                conclusion="inconclusive",
                details={"error": f"Unknown test type: {hypothesis.test_type}"},
            )

        # Determine conclusion
        if np.isnan(stat) or np.isnan(p_value):
            conclusion = "inconclusive"
        elif p_value < alpha:
            conclusion = "supported"
        else:
            conclusion = "rejected"

        return HypothesisResult(
            hypothesis_id=hypothesis.id,
            test_statistic=round(float(stat), 6),
            p_value=round(float(p_value), 6),
            conclusion=conclusion,
            details=details,
        )

    except Exception as exc:
        return HypothesisResult(
            hypothesis_id=hypothesis.id,
            test_statistic=0.0,
            p_value=1.0,
            conclusion="inconclusive",
            details={"error": str(exc)},
        )


def summarize_results(results: list[HypothesisResult]) -> str:
    """Generate a markdown summary of all hypothesis test results."""
    lines = [
        "# Hypothesis Test Results",
        "",
        f"**Total tests:** {len(results)}",
        f"**Supported:** {sum(1 for r in results if r.conclusion == 'supported')}",
        f"**Rejected:** {sum(1 for r in results if r.conclusion == 'rejected')}",
        f"**Inconclusive:** {sum(1 for r in results if r.conclusion == 'inconclusive')}",
        "",
        "---",
        "",
    ]

    for r in results:
        icon = {"supported": "[SUPPORTED]", "rejected": "[REJECTED]", "inconclusive": "[INCONCLUSIVE]"}
        lines.append(f"### {icon.get(r.conclusion, '')} Hypothesis {r.hypothesis_id}")
        lines.append("")
        lines.append(f"- **Test type:** {r.details.get('test_type', 'N/A')}")
        lines.append(f"- **Test statistic:** {r.test_statistic:.4f}")
        lines.append(f"- **p-value:** {r.p_value:.6f}")
        lines.append(f"- **Conclusion:** {r.conclusion}")

        # Add test-specific details
        if "group_a_mean" in r.details:
            lines.append(
                f"- **Group means:** {r.details['group_a_label']}={r.details['group_a_mean']:.4f}, "
                f"{r.details['group_b_label']}={r.details['group_b_mean']:.4f}"
            )
        if "method" in r.details:
            lines.append(f"- **Method:** {r.details['method']}")
        if "n_groups" in r.details:
            lines.append(f"- **Groups:** {r.details['n_groups']}")
        if "error" in r.details:
            lines.append(f"- **Error:** {r.details['error']}")

        lines.append("")

    return "\n".join(lines)
