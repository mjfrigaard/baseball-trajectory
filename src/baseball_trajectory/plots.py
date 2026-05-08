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
