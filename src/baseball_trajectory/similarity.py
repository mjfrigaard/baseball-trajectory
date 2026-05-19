"""Bill James similarity scores for comparing career batting statistics.

Two careers are compared by starting at 1000 and subtracting "penalty" points
based on absolute differences in counting stats, rate stats, and fielding
position. The full scoring rules — including the position-value table — are
the ones documented on Baseball-Reference's Similarity Scores page.

This module is a pure-Polars implementation of the algorithm. It does not
hit the network; callers are responsible for providing career-totals dicts
(see ``baseball_trajectory.data.get_player_career_totals``).
"""

from __future__ import annotations

import math
from typing import Mapping

import polars as pl

# Bill James position values. Pitchers (P) and the designated hitter (DH)
# are assigned 0 in the original formulation and are typically excluded
# from position-aware similarity comparisons.
POSITION_VALUE: dict[str, int] = {
    "C": 240,
    "SS": 168,
    "2B": 132,
    "3B": 84,
    "OF": 48,
    "LF": 48,
    "CF": 48,
    "RF": 48,
    "1B": 12,
}


def position_value(pos: str | None) -> int:
    """Return the Bill James position value for an MLB position abbreviation."""
    if not pos:
        return 0
    return POSITION_VALUE.get(pos, 0)


# (stat_key, divisor) — one point is deducted per unit of (|a − b| / divisor).
_COUNTING_DEDUCTIONS: list[tuple[str, float]] = [
    ("G", 20),
    ("AB", 75),
    ("R", 10),
    ("H", 15),
    ("2B", 5),
    ("3B", 4),
    ("HR", 2),
    ("RBI", 10),
    ("BB", 25),
    ("SO", 150),
    ("SB", 20),
]
_RATE_DEDUCTIONS: list[tuple[str, float]] = [
    ("AVG", 0.001),
    ("SLG", 0.002),
]


def _get(d: Mapping, key: str, default: float = 0.0) -> float:
    value = d.get(key, default)
    return float(value) if value is not None else default


def similarity_score(
    player: Mapping,
    other: Mapping,
    use_position: bool = True,
) -> int:
    """Bill James similarity score between two career-totals dicts.

    Both inputs are mappings (dicts or Polars row dicts) with keys for the
    counting stats listed in ``_COUNTING_DEDUCTIONS`` and the rate stats in
    ``_RATE_DEDUCTIONS``. Optionally a ``POS`` key for primary position.

    Returns an integer score; 1000 means identical careers.
    """
    score = 1000
    for col, divisor in _COUNTING_DEDUCTIONS:
        score -= math.floor(abs(_get(player, col) - _get(other, col)) / divisor)
    for col, divisor in _RATE_DEDUCTIONS:
        score -= math.floor(abs(_get(player, col) - _get(other, col)) / divisor)
    if use_position:
        score -= abs(
            position_value(player.get("POS")) - position_value(other.get("POS"))
        )
    return score


def find_similar_players(
    target: Mapping,
    candidates: pl.DataFrame,
    n: int = 10,
    use_position: bool = True,
) -> pl.DataFrame:
    """Rank candidate players by similarity to ``target``.

    ``target`` is a dict of career totals (see ``similarity_score``).
    ``candidates`` is a Polars DataFrame with the same career-totals columns,
    plus a ``playerID`` and (optionally) ``fullName``.

    Returns the top ``n`` candidates sorted by descending similarity score,
    with an added ``sim_score`` column.
    """
    if candidates.is_empty():
        return candidates.with_columns(pl.lit(None, dtype=pl.Int64).alias("sim_score"))
    scores = [
        similarity_score(target, row, use_position=use_position)
        for row in candidates.iter_rows(named=True)
    ]
    return (
        candidates.with_columns(pl.Series("sim_score", scores))
        .sort("sim_score", descending=True)
        .head(n)
    )
