# Data sources

All stats come from the **MLB Stats API** (`statsapi.mlb.com`), the
official source of record for Major League Baseball. The app calls
the API directly via `requests` — no Python wrapper.

## Endpoints

| Endpoint                                                                   | Used by                                |
| -------------------------------------------------------------------------- | -------------------------------------- |
| `GET /api/v1/sports/1/players?season={year}`                               | `_load_roster()` (typeahead + deep)    |
| `GET /api/v1/people/{id}`                                                  | `get_*_career` (biographical data)     |
| `GET /api/v1/people/{id}/stats?stats=yearByYear&group={group}&sportId=1`   | `get_*_career` (per-season splits)     |

## Caching

Three layers, all in-process:

- **Roster cache** (`_CACHE`, dict keyed by `roster_<year>`). One
  network round-trip per season per process. After the first fetch,
  every keystroke filters the cached Polars DataFrame locally —
  sub-millisecond per call.
- **Career cache** (`@lru_cache(256)` on `get_batting_career` and
  `get_pitching_career`). Two HTTP calls per first lookup of a
  player; zero on subsequent lookups within the same process.
- **Manual refresh** — `data.refresh_cache()` clears all of the
  above. The *Refresh data cache* sidebar button calls it.

## Two-tier search

`search_player(query, seasons_back=N)` walks rosters from the current
season back through `N` prior seasons, returning on the first season
that yields matches:

| Path                              | `seasons_back` | Use case                                  |
| --------------------------------- | -------------- | ----------------------------------------- |
| Typeahead (auto, on each keystroke) | `3`          | Active and very-recently-retired players  |
| Deep search (Search button when typeahead is empty) | `29` | Modern retirees back ~30 years   |

Why two tiers: a wide window on every keystroke would trigger many
roster downloads for typo-y queries (each non-matching season
iterates fully before the loop returns empty). The narrow typeahead
path stays fast; the deep path is opt-in via the Search click.

## Multi-team season aggregation

`yearByYear` splits return one row per team-season stint when a player
was traded mid-season. The career loaders aggregate these:

- **Counting stats** — summed across stints.
- **Rate stats** — recomputed from the summed totals (so a traded
  batter's AVG is total H ÷ total AB, not the average of his
  per-team averages).

This gives mathematically correct season-level rates regardless of
trades.

## `inningsPitched` parsing

The MLB API returns IP in **official notation**: `"180.2"` means
180⅔ innings, not 180.2 decimal. The tenths digit is *outs*, not
real tenths. `_parse_ip()` converts to decimal innings, and the
career loader stores `IPouts = round(decimal_ip * 3)` as the
integer-aggregation form before recomputing IP.

## Age computation

Age is taken as of **July 1** of each season — the standard
mid-season rule that Baseball-Reference and FanGraphs use:

```
Age = season - birth_year - (1 if birth_month >= 7 else 0)
```

Players born July or later are counted as one year younger for that
season. Birth date comes from the player's `/api/v1/people/{id}`
response, parsed by `_parse_birth_date()`.

## No pandas

API responses arrive as Python `dict`s and `list`s. They're built into
Polars DataFrames directly via `pl.DataFrame(rows)` — no pandas
intermediary. The one place pandas appears is `pl.from_pandas(...)`
on the output of `statsmodels.get_prediction().summary_frame()`,
which is converted on the same line and never used as pandas.
