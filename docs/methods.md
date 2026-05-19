# Methods

This page walks through the analytical methods that back the app, in the
order they're typically used: fit a player's aging curve, interpret its
coefficients, find similar players, and overlay their trajectories.

All snippets use `polars` and the package's own helpers. They run in a
notebook or REPL after `pip install -e .`. None of the snippets import
`pandas`.

## A worked example: Mickey Mantle

The book *Analyzing Baseball Data with R* (Marchi, Albert, Baumer) uses
Mickey Mantle as its walking example for aging curves. We'll do the same
— but with Mantle's player ID and modern MLB Stats API data.

```python
from baseball_trajectory.data import search_player, get_batting_career

matches = search_player("Mantle", seasons_back=29)
mantle_id = matches.filter(matches["fullName"] == "Mickey Mantle")["playerID"][0]
mantle = get_batting_career(mantle_id)
mantle.select(["Season", "Age", "PA", "AB", "OPS"]).head()
```

`get_batting_career` already handles the bookkeeping the R walkthrough
does manually: zero-filling `SF` and `HBP` for old seasons, recomputing
`SLG`, `OBP`, `OPS` from the underlying counting stats, and aggregating
multi-stint seasons. Age is computed with the standard mid-season rule
(July 1) — see [Data sources](data.md#age-computation) for details.

## The quadratic aging curve

For a given metric `y` (OPS, AVG, ERA, …) we fit a weighted least-squares
quadratic across the player's seasons:

```
y = β₀ + β₁·Age + β₂·Age² + ε
```

Weights are PA for batting metrics and IP for pitching metrics, so
full-season campaigns pull harder than 30-PA cups of coffee.

`fit_player_curve` returns the fitted coefficients along with the
closed-form peak age and the predicted value at that peak:

```python
from baseball_trajectory.model import fit_player_curve

fit = fit_player_curve(mantle, y_col="OPS", weight_col="PA")
print(fit["peak_age"], fit["max_value"], fit["curvature"])
```

### Centered form (R-style interpretation)

A non-centered fit hides the intuition behind the coefficients: `β₀`
(the predicted value at Age = 0) and `β₁` (the slope at Age = 0) aren't
interesting numbers. Re-fitting with `(Age − center)` as the predictor
gives each coefficient a direct meaning.

`fit_aging_curve` re-parameterizes as:

```
y = A + B·(Age − center) + C·(Age − center)² + ε
```

with `center=30.0` by default. The coefficients are interpretable:

| Coefficient | Interpretation                                                           |
| ----------- | ------------------------------------------------------------------------ |
| `A`         | Predicted `y` at `Age = center` (default age 30).                        |
| `B`         | Slope at `Age = center`. Positive ⇒ still rising at 30; negative ⇒ already declining. |
| `C`         | Curvature. For a true peak `C < 0`; more negative ⇒ sharper peak. One simple reading: `C` is the *change in y from peak to one year past peak*. |

With `C < 0`, the peak age and the value at the peak are closed-form:

```
peak_age = center − B / (2·C)
max_value = A − B² / (4·C)
```

In Python:

```python
from baseball_trajectory.model import fit_aging_curve

fit = fit_aging_curve(mantle, y_col="OPS", weight_col="PA", center=30.0)
fit["A"], fit["B"], fit["C"], fit["peak_age"], fit["max_value"]
```

The R walkthrough reports Mantle's fitted curve as roughly
`1.043 − 0.023·(Age − 30) − 0.0039·(Age − 30)²`, with a peak at age 27
and a peak OPS of 1.077. The Python fit reproduces those numbers (modulo
small differences from the API's per-season data vs. the Lahman bundle).

`fit_aging_curve` and `fit_player_curve` describe the *same parabola* —
the centered form just shifts which coordinates the coefficients
correspond to. `peak_age` and `max_value` are translation-invariant and
agree exactly between the two functions.

### Plotting Mantle's curve

The app's `plot_trajectory` overlays the fit, the 95% confidence ribbon,
and a marked peak age. From a notebook:

```python
from baseball_trajectory.plots import plot_trajectory

fig = plot_trajectory(
    mantle, fit_player_curve(mantle, "OPS", "PA"),
    y_col="OPS", weight_col="PA",
    player_name="Mickey Mantle",
)
fig.savefig("mantle-ops.png", dpi=150)
```

The plot mirrors the R version: scatter of OPS-by-age (point size
proportional to PA), a fitted curve, a vertical dashed line at the peak,
and an annotation showing the peak's location.

## Comparing players: Bill James similarity scores

To pick a meaningful comparison group, the app uses Bill James's
similarity-scoring algorithm, the same one Baseball-Reference's
*Similarity Scores* page uses.

Start at 1000 points and subtract:

| Stat        | One point per…                                |
| ----------- | --------------------------------------------- |
| `G`         | 20 games                                      |
| `AB`        | 75 at-bats                                    |
| `R`         | 10 runs scored                                |
| `H`         | 15 hits                                       |
| `2B`        | 5 doubles                                     |
| `3B`        | 4 triples                                     |
| `HR`        | 2 home runs                                   |
| `RBI`       | 10 RBI                                        |
| `BB`        | 25 walks                                      |
| `SO`        | 150 strikeouts                                |
| `SB`        | 20 stolen bases                               |
| `AVG`       | 0.001 batting average                         |
| `SLG`       | 0.002 slugging                                |

…then subtract the absolute difference in **position values** (Bill
James's table):

| Position | Value |
| -------- | ----- |
| C        | 240   |
| SS       | 168   |
| 2B       | 132   |
| 3B       | 84    |
| OF       | 48    |
| 1B       | 12    |
| P / DH   | 0     |

### In Python

```python
from baseball_trajectory.data import get_player_career_totals
from baseball_trajectory.similarity import similarity_score

mantle_totals = get_player_career_totals(mantle_id)
schmidt_totals = get_player_career_totals("121246")  # Mike Schmidt
similarity_score(mantle_totals, schmidt_totals)
```

`get_player_career_totals(player_id)` returns a dict with the career
counting/rate stats plus the player's primary position — the exact
shape `similarity_score` expects.

### Finding the *N* most similar players

`find_similar_players(target, candidates, n)` ranks a pool of
candidates against a target's career totals. The pool is the caller's
responsibility: the function performs no network I/O. A typical
notebook pattern:

```python
import polars as pl
from baseball_trajectory.data import get_player_career_totals
from baseball_trajectory.similarity import find_similar_players

target = get_player_career_totals(mantle_id)
candidate_ids = ["121246", "117540", "120903", "..."]  # known sluggers
candidates = pl.DataFrame([get_player_career_totals(pid) for pid in candidate_ids])
top = find_similar_players(target, candidates, n=5)
top.select(["fullName", "POS", "HR", "AVG", "sim_score"])
```

**Why caller-supplied candidates?** Walking the entire MLB-Stats-API
roster history is thousands of HTTP calls and seconds-to-minutes of
latency. Limiting the pool to ~50 hand-picked candidates (e.g., the
all-time HR leaderboard) gives meaningful comparisons in 30 seconds or
so on first run, then is instant from cache.

If you want an automated candidate pool, two patterns work:

1. **Seasonal pool** — pull a season's roster via
   `_load_roster(year)` and feed those IDs through
   `get_player_career_totals`. Good for "comparable to *this* era".
2. **Position-filtered pool** — fetch career totals for a small list
   of known players at the target's position. Good for "comparable
   types of player".

## Comparing trajectories side-by-side

Once you have a player + comparison group, the small-multiples plot
shows their curves on a shared axis grid:

```python
from baseball_trajectory.data import get_batting_career
from baseball_trajectory.plots import plot_trajectories_facet

players = {
    "Mickey Mantle":  get_batting_career(mantle_id),
    "Frank Thomas":   get_batting_career("113194"),
    "Eddie Mathews":  get_batting_career("118258"),
    "Mike Schmidt":   get_batting_career("121246"),
    "Sammy Sosa":     get_batting_career("123790"),
}

fig = plot_trajectories_facet(players, y_col="OPS", ncol=2)
fig.savefig("comparison.png", dpi=150)
```

Each panel contains the player's per-season scatter (sized by season,
fixed scale across panels) and a quadratic fit. Reading across panels:

- Players whose fit is steep and concave-down peaked early (or briefly).
- Flat fits — small `|C|` — describe steady careers (the Paul Molitor
  archetype).
- Symmetric, deep parabolas describe classic *rise to peak, fall to
  retirement* careers (the Mike Schmidt archetype).

For pitching metrics, pass `lower_better=True` to invert each panel's
y-axis so the peak is at the top.

## Peak age and curvature, summarized

Once you've fit curves for a group, the two most informative summary
numbers per player are the **peak age** and the **curvature** `C`. A
scatter of (peak_age, C) places each player on a simple map: early-vs-
late peakers along the x-axis, sharp-vs-flat declines along the y-axis.

```python
from baseball_trajectory.model import fit_aging_curve
from baseball_trajectory.plots import plot_peak_vs_curvature

fits = {
    name: fit_aging_curve(df, y_col="OPS", weight_col="PA")
    for name, df in players.items()
}
fig = plot_peak_vs_curvature(fits)
```

Players in the bottom-left peaked early and declined sharply; players
in the top-right peaked late with shallow falloff.

## Historical scans

The R walkthrough closes with three sweeping questions that require
career fits for *every* player in the database:

1. How has the average peak age changed over baseball history?
2. Do longer careers peak later?
3. Does peak age vary by fielding position?

The shape of the answer is the same in Python — fit one model per
player, summarize the coefficients, plot the trend — but the data
plumbing is heavier here. The MLB Stats API doesn't expose a single
"give me every player's career totals" endpoint, so a full scan means
walking ~30 seasons of rosters and fetching career stats per player
(thousands of HTTP calls).

### Recipe

Pseudocode for the general scan, given an in-process cache:

```python
from baseball_trajectory.data import _load_roster, get_batting_career
from baseball_trajectory.model import fit_aging_curve

# 1. Build the candidate pool: every player who appeared in seasons N..N-29.
pool = set()
for year in range(2026, 1996, -1):
    pool.update(_load_roster(year)["playerID"].to_list())

# 2. Pull each player's career; fit; keep peak_age and midcareer.
records = []
for pid in pool:
    career = get_batting_career(pid)            # cached
    if career.height < 5:                       # skip very short careers
        continue
    fit = fit_aging_curve(career, "OPS", "PA")
    if fit is None or fit["peak_age"] is None:
        continue
    records.append({
        "playerID": pid,
        "peak_age": fit["peak_age"],
        "midcareer": (career["Season"].min() + career["Season"].max()) / 2,
        "career_AB": career["AB"].sum(),
    })

# 3. Plot peak_age against midcareer (a LOESS or rolling-mean trend works
# well — matplotlib alone doesn't ship LOESS, but `statsmodels.nonparametric.
# smoothers_lowess.lowess` does).
```

This is intentionally not wrapped in a single helper: the run takes long
enough to warrant explicit batching, error handling, and persistence to
disk between runs. For sustained analytical use, persist the
career-totals frame as a Parquet/CSV after the first scan and load it
on subsequent runs.

### What the R walkthrough finds

For reference, the *Analyzing Baseball Data with R* book reports the
following from a Lahman-bundle scan:

- **Peak age over time** — gradual rise from ~27 (1880s) to ~28 (2010s).
- **Peak age vs. career length** — players with ≥9000 career AB tend to
  peak closer to 30; players with the minimum 2000 AB peak closer to
  27.
- **Peak age by position** — most positions cluster between 27 and 32;
  outliers (peak after 37) are concentrated at corner-OF and
  utility-IF spots, often players whose careers were extended by
  position changes.

These shouldn't change much when sourced from the MLB Stats API. If you
run the scan and want to make the findings part of the app, the
recommended path is to compute offline and ship the resulting Polars
DataFrame as a static parquet file alongside the package — not to
re-fetch on every app start.

## Reference

| Symbol     | Where defined                                       |
| ---------- | --------------------------------------------------- |
| `A`, `B`, `C` | `fit_aging_curve` return dict (centered form)    |
| `peak_age` | `fit_player_curve` and `fit_aging_curve` return dict |
| `max_value` | `fit_player_curve` and `fit_aging_curve` return dict |
| `curvature` (= `C`) | `fit_player_curve` return dict             |
| `POSITION_VALUE` table | `baseball_trajectory.similarity`        |
| `similarity_score`, `find_similar_players` | `baseball_trajectory.similarity` |
| `get_player_career_totals` | `baseball_trajectory.data`          |
| `plot_trajectories_facet`, `plot_peak_vs_curvature` | `baseball_trajectory.plots` |
