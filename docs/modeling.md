# Modeling approach

The app fits a single-metric **weighted quadratic aging curve** for
each player.

## The model

For seasons indexed by Age, weighted by playing time:

```
y = β₀ + β₁·Age + β₂·Age² + ε
```

Implementation: `statsmodels.api.WLS(y, X, weights=w).fit()`, with
weights equal to PA (batters) or IP (pitchers). Seasons with more
playing time pull the curve harder than partial seasons.

## Why weighted

A 90-PA September call-up and a 700-PA full season carry the same
arithmetic information to ordinary least squares, but they're not
equally informative about the player's true ability. Weighting by PA
pushes the fit toward seasons that contain more signal.

## Peak age

When β₂ < 0 the parabola opens downward and there's a real maximum.
Setting the derivative to zero gives the peak age in closed form:

```
Age* = -β₁ / (2·β₂)
```

That's the value the app marks with a dashed vertical line and labels
*Peak: ##.#*.

When β₂ ≥ 0 the curve is flat or concave-up — usually a sign of an
unfinished or unusual career — and the peak marker is suppressed.

## Confidence band

`get_prediction(X).summary_frame(alpha=0.05)` produces a 95% mean
prediction interval at each input age. The shaded ribbon spans
`mean_ci_lower` to `mean_ci_upper`. It widens at the edges of the
career, where fewer seasons constrain the fit.

## Career summary

`summarize_career()` returns:

| Field            | What it is                                                  |
| ---------------- | ----------------------------------------------------------- |
| `weighted_mean`  | Career rate stat, weighted by the same PA/IP as the fit.    |
| `best_season`    | The season with the highest `y_col` (Season, Age, value).   |
| `peak_age`       | Closed-form peak from the fit (or `None` if non-concave).   |
| `total_weight`   | Career total of PA or IP.                                   |

The one-row summary table in the UI is built from this dict.

## Assumptions and caveats

- **A single quadratic shape** describes the arc. Bimodal arcs
  (injury-recovery careers, mid-career position changes,
  knuckleballers) won't be modeled well.
- **Weights are exogenous.** A manager who benches a struggling player
  reduces their PA, which biases the fit slightly toward years the
  player was healthy and effective.
- **No era adjustments.** A 1908 OPS is treated the same as a 2019
  OPS. See [Limitations](limitations.md) for more.
