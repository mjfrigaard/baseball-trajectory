"""Tests for baseball_trajectory.model."""

import polars as pl

from baseball_trajectory.model import fit_aging_curve, fit_player_curve


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


def test_fit_player_curve_exposes_max_and_curvature():
    df = _peaked_career(peak=28.0)
    fit = fit_player_curve(df, y_col="OPS", weight_col="PA")
    assert fit is not None
    # Synthetic curve has its true max at 0.9 (y = -((a-28)^2)/100 + 0.9).
    assert fit["max_value"] is not None
    assert abs(fit["max_value"] - 0.9) < 0.01
    # Curvature is the same as coefficients["age2"] in the non-centered form.
    assert fit["curvature"] == fit["coefficients"]["age2"]


def test_fit_aging_curve_centered_interpretation():
    df = _peaked_career(peak=28.0)
    fit = fit_aging_curve(df, y_col="OPS", weight_col="PA", center=30.0)
    assert fit is not None
    # Peak age must recover the true peak.
    assert abs(fit["peak_age"] - 28.0) < 0.5
    # A is the predicted value at the centering age (30). True curve at 30
    # is -((30-28)^2)/100 + 0.9 = 0.86.
    assert abs(fit["A"] - 0.86) < 0.01
    # Max value of the true parabola is 0.9.
    assert abs(fit["max_value"] - 0.9) < 0.01
    # Curvature is negative for a true peak.
    assert fit["C"] < 0


def test_fit_aging_curve_peak_age_matches_player_curve():
    df = _peaked_career(peak=28.0)
    centered = fit_aging_curve(df, y_col="OPS", weight_col="PA", center=30.0)
    non_centered = fit_player_curve(df, y_col="OPS", weight_col="PA")
    # The two parameterizations describe the same parabola.
    assert centered is not None and non_centered is not None
    assert abs(centered["peak_age"] - non_centered["peak_age"]) < 1e-6
    assert abs(centered["max_value"] - non_centered["max_value"]) < 1e-6
