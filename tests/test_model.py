"""Tests for baseball_trajectory.model."""

import polars as pl

from baseball_trajectory.model import fit_player_curve


def _peaked_career(peak: float = 28.0) -> pl.DataFrame:
    """Synthetic career that peaks at the given age."""
    ages = list(range(22, 36))
    ops = [-((a - peak) ** 2) / 100.0 + 0.9 for a in ages]
    pa = [600] * len(ages)
    return pl.DataFrame({"Age": ages, "OPS": ops, "PA": pa})


def test_fit_recovers_negative_quadratic_for_peaked_curve():
    fit = fit_player_curve(_peaked_career(), y_col="OPS", weight_col="PA")
    assert fit is not None
    assert fit["coefficients"]["age2"] < 0
    assert fit["r_squared"] > 0.99


def test_peak_age_within_input_range():
    df = _peaked_career(peak=28.0)
    fit = fit_player_curve(df, y_col="OPS", weight_col="PA")
    assert fit is not None
    assert fit["peak_age"] is not None
    age_min = float(df["Age"].min())
    age_max = float(df["Age"].max())
    assert age_min <= fit["peak_age"] <= age_max
    assert abs(fit["peak_age"] - 28.0) < 0.5


def test_fit_returns_none_for_too_few_rows():
    df = pl.DataFrame({"Age": [25, 26], "OPS": [0.80, 0.85], "PA": [500, 550]})
    assert fit_player_curve(df, y_col="OPS", weight_col="PA") is None
