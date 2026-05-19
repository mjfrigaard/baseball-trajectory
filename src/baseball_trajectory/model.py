"""Aging-curve modeling for baseball-trajectory.

Fits weighted least-squares quadratic curves of the form
``y = a + b*Age + c*Age**2`` to per-season player metrics, with weights
proportional to playing time (PA for batting, IP for pitching). Inputs are
Polars DataFrames; statsmodels operates on NumPy arrays under the hood.
"""

from __future__ import annotations

import numpy as np
import polars as pl
import statsmodels.api as sm

BATTING_METRICS: dict[str, str] = {
    "OPS": "PA",
    "OBP": "PA",
    "SLG": "PA",
    "AVG": "PA",
    "HR": "PA",
    "ISO": "PA",
}

PITCHING_METRICS: dict[str, str] = {
    "ERA": "IP",
    "WHIP": "IP",
    "K/9": "IP",
    "BB/9": "IP",
    "HR/9": "IP",
}

_LOWER_BETTER = frozenset({"ERA", "WHIP", "BB/9", "HR/9"})


def is_lower_better(metric: str) -> bool:
    return metric in _LOWER_BETTER


def fit_player_curve(
    df: pl.DataFrame,
    y_col: str,
    weight_col: str,
    age_col: str = "Age",
) -> dict | None:
    clean = df.drop_nulls(subset=[age_col, y_col, weight_col])
    if clean.height < 3:
        return None

    age = clean[age_col].to_numpy().astype(float)
    y = clean[y_col].to_numpy().astype(float)
    w = clean[weight_col].to_numpy().astype(float)
    X = np.column_stack([np.ones_like(age), age, age**2])

    model = sm.WLS(y, X, weights=w).fit()
    a, b, c = (float(p) for p in model.params)
    peak_age = -b / (2 * c) if c < 0 else None
    # The y-value at the peak is a translation-invariant property of the
    # parabola: y_max = a - b²/(4c). Holds in centered or non-centered form.
    max_value = a - b**2 / (4 * c) if c < 0 else None

    return {
        "model": model,
        "coefficients": {"intercept": a, "age": b, "age2": c},
        "peak_age": peak_age,
        "max_value": max_value,
        "curvature": c,
        "r_squared": float(model.rsquared),
        "n_seasons": int(clean.height),
    }


def fit_aging_curve(
    df: pl.DataFrame,
    y_col: str,
    weight_col: str,
    age_col: str = "Age",
    center: float = 30.0,
) -> dict | None:
    """Fit a weighted quadratic in centered form.

    Model: ``y = A + B·(Age − center) + C·(Age − center)² + ε``

    The centered parameterization gives each coefficient an interpretable
    meaning at ``Age = center``:

    - ``A`` — predicted ``y_col`` at the centering age (default 30).
    - ``B`` — slope at the centering age.
    - ``C`` — curvature (negative for a true peak; the more negative, the
      sharper the peak and the steeper the post-peak decline).

    With ``C < 0`` the closed-form peak and max are:

    - ``peak_age = center − B / (2·C)``
    - ``max_value = A − B² / (4·C)``

    Returns ``None`` when fewer than 3 non-null rows are available.
    """
    clean = df.drop_nulls(subset=[age_col, y_col, weight_col])
    if clean.height < 3:
        return None

    age = clean[age_col].to_numpy().astype(float)
    y = clean[y_col].to_numpy().astype(float)
    w = clean[weight_col].to_numpy().astype(float)
    age_c = age - center
    X = np.column_stack([np.ones_like(age_c), age_c, age_c**2])

    model = sm.WLS(y, X, weights=w).fit()
    A, B, C = (float(p) for p in model.params)
    peak_age = center - B / (2 * C) if C < 0 else None
    max_value = A - B**2 / (4 * C) if C < 0 else None

    return {
        "model": model,
        "A": A,
        "B": B,
        "C": C,
        "center": center,
        "peak_age": peak_age,
        "max_value": max_value,
        "r_squared": float(model.rsquared),
        "n_seasons": int(clean.height),
    }


def predict_curve(fit: dict, ages: np.ndarray) -> pl.DataFrame:
    ages_arr = np.asarray(ages, dtype=float)
    X = np.column_stack([np.ones_like(ages_arr), ages_arr, ages_arr**2])
    pred = fit["model"].get_prediction(X).summary_frame(alpha=0.05)
    pl_pred = pl.from_pandas(pred)
    return pl.DataFrame(
        {
            "Age": ages_arr,
            "predicted": pl_pred["mean"],
            "ci_low": pl_pred["mean_ci_lower"],
            "ci_high": pl_pred["mean_ci_upper"],
        }
    )


def summarize_career(
    df: pl.DataFrame,
    y_col: str,
    weight_col: str,
) -> dict:
    clean = df.drop_nulls(subset=[y_col, weight_col])
    if clean.height == 0:
        return {
            "weighted_mean": None,
            "best_season": None,
            "peak_age": None,
            "total_weight": 0.0,
        }

    summary = clean.select(
        [
            (
                (pl.col(y_col) * pl.col(weight_col)).sum() / pl.col(weight_col).sum()
            ).alias("weighted_mean"),
            pl.col(weight_col).sum().alias("total_weight"),
        ]
    )

    best_idx = clean[y_col].arg_max()
    best_row = clean.row(best_idx, named=True)

    fit = fit_player_curve(df, y_col, weight_col)

    return {
        "weighted_mean": summary.item(0, "weighted_mean"),
        "best_season": {
            "Season": best_row.get("Season"),
            "Age": best_row.get("Age"),
            y_col: best_row.get(y_col),
        },
        "peak_age": fit["peak_age"] if fit else None,
        "total_weight": summary.item(0, "total_weight"),
    }
