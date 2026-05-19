"""Plotting utilities for baseball-trajectory.

Pure matplotlib (no seaborn). Inputs are Polars DataFrames, converted to
NumPy arrays just before being handed to matplotlib.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import polars as pl
from matplotlib.figure import Figure

from baseball_trajectory.model import predict_curve


def plot_trajectory(
    df: pl.DataFrame,
    fit: dict,
    y_col: str,
    weight_col: str,
    player_name: str,
    lower_better: bool = False,
) -> Figure:
    ages = df["Age"].to_numpy().astype(float)
    ys = df[y_col].to_numpy().astype(float)
    weights = df[weight_col].to_numpy().astype(float)

    max_w = float(np.nanmax(weights)) if weights.size else 1.0
    scale = max_w / 200.0 if max_w > 0 else 1.0
    sizes = weights / scale

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.scatter(ages, ys, s=sizes, alpha=0.6, edgecolor="white", linewidth=0.5)

    age_grid = np.linspace(ages.min(), ages.max(), 100)
    pred = predict_curve(fit, age_grid)
    pred_ages = pred["Age"].to_numpy()
    predicted = pred["predicted"].to_numpy()
    ci_low = pred["ci_low"].to_numpy()
    ci_high = pred["ci_high"].to_numpy()

    ax.plot(pred_ages, predicted, "-", color="C0", linewidth=2)
    ax.fill_between(pred_ages, ci_low, ci_high, alpha=0.2, color="C0")

    peak = fit.get("peak_age")
    if peak is not None:
        ax.axvline(
            peak,
            linestyle="--",
            color="gray",
            linewidth=1.2,
            label=f"Peak: {peak:.1f}",
        )
        ax.legend(loc="best", frameon=False)

    ax.set_title(f"{player_name} — {y_col} by Age")
    ax.set_xlabel("Age")
    ax.set_ylabel(y_col)
    ax.grid(alpha=0.3)

    if lower_better:
        ax.invert_yaxis()

    fig.tight_layout()
    return fig


def plot_empty(message: str) -> Figure:
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.text(
        0.5,
        0.5,
        message,
        ha="center",
        va="center",
        transform=ax.transAxes,
        fontsize=12,
        color="gray",
    )
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    fig.tight_layout()
    return fig


def plot_trajectories_facet(
    careers_by_name: dict[str, pl.DataFrame],
    y_col: str,
    age_col: str = "Age",
    ncol: int = 2,
    lower_better: bool = False,
) -> Figure:
    """Small-multiples plot of multiple players' aging curves.

    ``careers_by_name`` maps a display name to that player's per-season
    Polars frame (must contain ``age_col`` and ``y_col``). Each player
    gets its own panel with raw seasons (scatter) and a quadratic fit
    (solid line). Panels with fewer than three valid seasons render a
    "Not enough seasons" placeholder.
    """
    if not careers_by_name:
        return plot_empty("No players to plot")

    n = len(careers_by_name)
    ncol = max(1, ncol)
    nrow = (n + ncol - 1) // ncol
    fig, axes = plt.subplots(
        nrow, ncol, figsize=(ncol * 4.0, nrow * 3.0), squeeze=False
    )

    for ax, (name, df) in zip(axes.flatten(), careers_by_name.items()):
        clean = df.drop_nulls(subset=[age_col, y_col])
        if clean.height < 3:
            ax.text(
                0.5,
                0.5,
                "Not enough seasons",
                ha="center",
                va="center",
                transform=ax.transAxes,
                fontsize=9,
                color="gray",
            )
            ax.set_title(name, fontsize=10)
            ax.set_xticks([])
            ax.set_yticks([])
            continue

        age = clean[age_col].to_numpy().astype(float)
        y = clean[y_col].to_numpy().astype(float)
        ax.scatter(age, y, s=30, alpha=0.6, edgecolor="white", linewidth=0.5)

        # Quadratic fit: y = a + b*Age + c*Age**2
        coefs = np.polyfit(age, y, 2)
        age_grid = np.linspace(age.min(), age.max(), 60)
        ax.plot(age_grid, np.polyval(coefs, age_grid), color="C0", linewidth=1.8)

        ax.set_title(name, fontsize=10)
        ax.set_xlabel(age_col)
        ax.set_ylabel(y_col)
        ax.grid(alpha=0.3)
        if lower_better:
            ax.invert_yaxis()

    for ax in axes.flatten()[n:]:
        ax.set_visible(False)

    fig.tight_layout()
    return fig


def plot_peak_vs_curvature(
    fits_by_name: dict[str, dict],
) -> Figure:
    """Scatter of fitted peak age vs curvature, with player labels.

    ``fits_by_name`` maps a display name to a fit dict from
    ``model.fit_aging_curve`` (uses ``peak_age`` and ``C``) or
    ``model.fit_player_curve`` (uses ``peak_age`` and ``curvature``).
    Players whose peak couldn't be computed (non-concave fit) are skipped.
    """
    rows: list[tuple[str, float, float]] = []
    for name, fit in fits_by_name.items():
        if not fit:
            continue
        peak = fit.get("peak_age")
        curv = fit.get("C", fit.get("curvature"))
        if peak is None or curv is None:
            continue
        rows.append((name, float(peak), float(curv)))

    if not rows:
        return plot_empty("No fits with a defined peak")

    fig, ax = plt.subplots(figsize=(8, 6))
    for name, peak, curv in rows:
        ax.scatter([peak], [curv], s=60, color="C0")
        ax.annotate(
            name,
            (peak, curv),
            xytext=(6, 4),
            textcoords="offset points",
            fontsize=9,
        )

    ax.set_xlabel("Peak age")
    ax.set_ylabel("Curvature (C)")
    ax.set_title("Peak age and curvature")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    return fig
