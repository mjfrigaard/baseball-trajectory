# API reference

The package's public surface is small enough to read at a glance.
Everything below is importable from `baseball_trajectory`.

## `baseball_trajectory.data`

Player search and per-player career queries.

### Functions

| Function                                       | Returns         | Description                                                                                                      |
| ---------------------------------------------- | --------------- | ---------------------------------------------------------------------------------------------------------------- |
| `search_player(query, seasons_back=3)`         | `pl.DataFrame`  | Substring-match player names against cached MLB rosters. Walks `seasons_back+1` rosters from the current season backward, returning on the first season with matches. Up to 50 rows. |
| `get_batting_career(player_id)`                | `pl.DataFrame`  | Per-season batting career: `Season`, `Age`, `PA`, `AB`, `H`, `HR`, `AVG`, `OBP`, `SLG`, `OPS`, `ISO`, `BB%`, `K%`. Multi-team seasons aggregated. |
| `get_pitching_career(player_id)`               | `pl.DataFrame`  | Per-season pitching career: `Season`, `Age`, `IP`, `ERA`, `WHIP`, `K/9`, `BB/9`, `HR/9`, `W`, `L`, `SO`, `BB`. |
| `refresh_cache()`                              | `None`          | Clear the in-memory roster and career caches.                                                                    |

`player_id` is the MLB integer player ID stored as a string (e.g.
`"545361"` for Mike Trout).

### Example

```python
import polars as pl
from baseball_trajectory.data import search_player, get_batting_career

matches = search_player("Trout")
trout_id = matches.filter(pl.col("fullName") == "Mike Trout")["playerID"][0]
career = get_batting_career(trout_id)
print(career.head())
```

## `baseball_trajectory.model`

Aging-curve fit and summaries.

### Functions

| Function                                                | Returns          | Description                                                                                                       |
| ------------------------------------------------------- | ---------------- | ----------------------------------------------------------------------------------------------------------------- |
| `fit_player_curve(df, y_col, weight_col, age_col="Age")` | `dict \| None`   | Weighted quadratic fit. Returns `None` if fewer than 3 valid rows. The dict has `model`, `coefficients` (`intercept`, `age`, `age2`), `peak_age`, `r_squared`, `n_seasons`. |
| `predict_curve(fit, ages)`                              | `pl.DataFrame`   | Predictions over an age grid with 95% CI: columns `Age`, `predicted`, `ci_low`, `ci_high`.                       |
| `summarize_career(df, y_col, weight_col)`               | `dict`           | Career summary: `weighted_mean`, `best_season`, `peak_age`, `total_weight`. Native Python types (no Polars scalars). |
| `is_lower_better(metric)`                               | `bool`           | `True` for ERA, WHIP, BB/9, HR/9.                                                                                |

### Constants

| Name                | Type                | Description                                                            |
| ------------------- | ------------------- | ---------------------------------------------------------------------- |
| `BATTING_METRICS`   | `dict[str, str]`    | Metric → weight column. `OPS`, `OBP`, `SLG`, `AVG`, `HR`, `ISO` → `PA`. |
| `PITCHING_METRICS`  | `dict[str, str]`    | `ERA`, `WHIP`, `K/9`, `BB/9`, `HR/9` → `IP`.                            |

### Example

```python
import numpy as np
from baseball_trajectory.data import get_batting_career
from baseball_trajectory.model import fit_player_curve, predict_curve

career = get_batting_career("545361")  # Mike Trout
fit = fit_player_curve(career, y_col="OPS", weight_col="PA")
print(f"Peak age: {fit['peak_age']:.1f}, R² = {fit['r_squared']:.3f}")

ages = np.linspace(career["Age"].min(), career["Age"].max(), 100)
predictions = predict_curve(fit, ages)
```

## `baseball_trajectory.plots`

Matplotlib trajectory chart.

### Functions

| Function                                                                          | Returns                       | Description                                                                                                |
| --------------------------------------------------------------------------------- | ----------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `plot_trajectory(df, fit, y_col, weight_col, player_name, lower_better=False)`    | `matplotlib.figure.Figure`    | Scatter of seasons (sized by weight) plus the fitted curve, 95% CI ribbon, and peak-age line.              |
| `plot_empty(message)`                                                             | `matplotlib.figure.Figure`    | Blank figure with a centered placeholder message.                                                          |

### Example

```python
from baseball_trajectory.data import get_batting_career
from baseball_trajectory.model import fit_player_curve
from baseball_trajectory.plots import plot_trajectory

career = get_batting_career("545361")
fit = fit_player_curve(career, y_col="OPS", weight_col="PA")
fig = plot_trajectory(
    career, fit,
    y_col="OPS", weight_col="PA",
    player_name="Mike Trout",
)
fig.savefig("trout-ops.png", dpi=150)
```
