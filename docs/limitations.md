# Limitations

Known behaviours of this app and where they come from.

## Search coverage

The MLB Stats API endpoint we use
(`/api/v1/sports/1/players?season=Y`) returns only players who
appeared in season `Y`. The app stitches together rosters across
recent seasons:

- **Typeahead** covers the current season + 3 prior seasons.
- **Deep search** (Search-button fallback) covers ~30 prior seasons.

Players who retired before the deep-search window aren't reachable
through the UI. The MLB Stats API has older records; adding the
all-time `/api/v1/people/search` endpoint would extend coverage if
needed.

## Single-shape model

The curve assumes one quadratic describes the entire career. This is
a poor fit for:

- **Injury-recovery careers** — a dip mid-career, a recovery, then
  decline.
- **Position changes** that move a player's offensive baseline (e.g.
  catcher → first base).
- **Knuckleballers** and other pitchers with unusual aging patterns.

The output isn't lying when this happens; it's just averaging.

## Aggregation across stints

Multi-team seasons (when a player is traded mid-year) are aggregated
into a single season row by **summing counting stats**. Rate stats
are **recomputed from the summed totals** — so a traded batter's AVG
is total H ÷ total AB, not the mean of his per-team averages.

This is the right thing in almost every case, but if you're pulling
data programmatically and need stint-level granularity, you'll need
to call the MLB Stats API directly.

## No adjustments

Raw counting and rate stats only:

- **No park factors** — Coors Field hitters look better than they
  should.
- **No era adjustments** — a 1908 OPS is treated the same as a 2019
  OPS.
- **No DH/non-DH splits** — pitchers' bat-side stats from before the
  universal DH are mixed in.
- **No league-strength weighting**.

## Age cutoff

Age is computed as of July 1 — the standard mid-season rule. Players
born July or later are counted as one year younger for that season.
Borderline cases (a player born June 28 vs. July 2) appear in
adjacent age buckets even though they're days apart.

## "Active" / "final season" labels

In the search dropdown, the trailing label is one of:

- `Active` — the player has the `active=True` flag on the most recent
  roster they appear on.
- A four-digit year — the most recent season the player appears on a
  searched roster.

This is a proxy for *final season*, not an authoritative answer.
Players in the deep-search range who played in a season *outside* our
30-year window will show a year inside the window.
