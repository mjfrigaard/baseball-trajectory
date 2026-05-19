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

## Search windows

`search_player(query, seasons_back=N)` walks rosters from the current
season back through `N` prior seasons, returning on the first season
that yields matches. The app picks `N` based on the **Player type**
toggle and on whether the user clicked **Search** explicitly:

| Mode                          | Typeahead (auto, on each keystroke) | Search button (explicit deep lookup) |
| ----------------------------- | ----------------------------------- | ------------------------------------ |
| **Active players**            | `seasons_back=3`                    | `seasons_back=29`                    |
| **Retired players**           | `seasons_back=50`                   | `seasons_back=80`                    |

Active mode keeps typeahead fast (one season's roster is enough for
the current MLB roster). Retired mode widens both windows so older
retirees (Griffey Jr. 2010, Pedro Martínez 2009, Nolan Ryan 1993,
Stan Musial 1963, …) come up — at the cost of a one-time
roster-download burst when the user toggles into Retired and types
their first keystroke (~15–25 seconds on a cold cache, instant
afterwards).

The Search button is also the *deep-search* fallback. If
auto-typeahead returns nothing (e.g. typing a name in Active mode
that only appears in older rosters), clicking Search runs the wider
lookup and refreshes the dropdown — without committing or loading
stats.

## Position in the roster cache

Each cached roster row carries the player's primary fielding position
(`primaryPosition.abbreviation` from the MLB Stats API — e.g. `CF`,
`P`, `SS`). `search_player` returns it as a `position` column, and
the app uses it in two ways:

1. **Dropdown labels** include the position next to the player's
   name — *Mike Trout — CF (2011–Active)* — so users can spot a
   mismatch before committing.
2. **The dropdown is filtered by the Position toggle**, so users
   never see candidates whose primary position can't yield the
   requested kind of career data.

### Position-filter rules

The filter is applied in the app layer (`_filter_by_position` in
`app.py`) right after every `data.search_player` call, before
`search_results` is published to the dropdown:

| Position toggle | Primary-position codes kept                                   |
| --------------- | ------------------------------------------------------------- |
| **Pitcher**     | `P` (pure pitcher), `TWP` (two-way player, e.g. Ohtani)       |
| **Batter**      | Everything *except* `P` — `C`, `1B`, `2B`, `3B`, `SS`, `LF`, `CF`, `RF`, `OF`, `DH`, `TWP`, … |

Rows whose primary position is `null` are excluded in both modes —
we can't confirm the player has enough data either way.

The filter is intentionally **static**: it uses the
`primaryPosition` field that comes with the roster response, not a
per-player career-stats lookup. That keeps the dropdown fast (no
extra HTTP calls), at the cost of a slightly conservative
definition of "has enough data" — a position player who once threw
a knuckleball in a blowout game will be filtered out, but that's
the right call for an aging-curve fit.

When a search returns matches but the filter drops them all, the
picker shows a position-aware empty state (*"No matching pitchers
found. Try switching Position to Batter."*) instead of an empty
dropdown.

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
