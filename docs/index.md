# baseball-trajectory

A small Shiny for Python app that fits and visualizes a single-metric
career aging curve for any major-league player.

Type a name in the sidebar, pick a stat (OPS, ERA, WHIP, …), and the
app fits a weighted quadratic to the per-season values and renders the
trajectory with a 95% confidence band and a marked peak age.

## What you can do

- See when a player peaked, how steeply they declined, and how well a
  smooth curve fits across seasons.
- Compare batter metrics (OPS, OBP, SLG, AVG, HR, ISO) or pitcher
  metrics (ERA, WHIP, K/9, BB/9, HR/9).
- Look up active players via fast typeahead, or recently-retired
  players via a deeper search.
- Filter out cups-of-coffee seasons with the *Min PA / IP* knob.

## When you might use it

- Quick exploration: *did Trout peak earlier than I thought?*
- Teaching: a worked example of weighted quadratic regression with a
  closed-form interpretation.
- A starting point for your own aging-curve work — the Polars career
  frames are usable from a notebook with
  `from baseball_trajectory.data import get_batting_career`.

## Where to go next

- [Getting started](getting-started.md) — install and run.
- [User guide](user-guide.md) — the full sidebar workflow.
- [Modeling approach](modeling.md) — what the curve means.
- [Deployment](deployment.md) — Posit Connect Cloud and other hosts.
- [API reference](reference.md) — programmatic usage.
