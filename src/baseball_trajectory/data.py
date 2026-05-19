"""Data loading via the MLB Stats API.

All endpoints are called directly with ``requests``:

* ``GET /api/v1/sports/1/players?season={year}``
  → full season roster (cached for fast typeahead search).
* ``GET /api/v1/people/{id}``
  → player biographical data (birthDate, fullName, etc.)
* ``GET /api/v1/people/{id}/stats?stats=yearByYear&group={group}&sportId=1``
  → per-season career splits (one row per team-season stint).

Player search loads the current-season roster once per session and then
filters substrings locally in Polars — keystroke-rate updates without
hitting the API after the first fetch. ``search_player`` falls back
through three prior seasons so recently-retired players remain findable.

Other design notes
------------------
* Multi-team seasons are aggregated: counting stats are summed and rate stats
  are recomputed from the totals.
* All data arrives as Python dicts; we convert to Polars DataFrames
  immediately. No pandas anywhere in this module.
* Age = season - birth_year - (1 if born July or later else 0), the standard
  baseball mid-season rule.
* Errors are logged to stderr so they appear in the Uvicorn server log.
* ``@lru_cache`` on the career helpers prevents repeat network calls within a
  single app session. Call ``refresh_cache()`` to force a re-fetch.
"""

from __future__ import annotations

import datetime
import functools
import sys

import polars as pl
import requests as _requests

_MLB_API = "https://statsapi.mlb.com/api/v1"
_TIMEOUT = 15  # seconds

# ---------------------------------------------------------------------------
# In-process cache
# ---------------------------------------------------------------------------
_CACHE: dict[str, pl.DataFrame] = {}


def refresh_cache() -> None:
    """Clear the in-memory cache; the next call re-fetches from MLB Stats API."""
    _CACHE.clear()
    get_batting_career.cache_clear()
    get_pitching_career.cache_clear()
    get_player_career_totals.cache_clear()


# ---------------------------------------------------------------------------
# Low-level MLB Stats API helpers
# ---------------------------------------------------------------------------


def _load_roster(season: int) -> pl.DataFrame:
    """Fetch the full roster for ``season`` and cache it as a Polars frame.

    One network round-trip per season per process; subsequent calls return
    the cached frame so name searches happen entirely in Polars.
    """
    cache_key = f"roster_{season}"
    if cache_key in _CACHE:
        return _CACHE[cache_key]
    resp = _requests.get(
        f"{_MLB_API}/sports/1/players",
        params={"season": season},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    people = resp.json().get("people", [])
    rows = [
        {
            "playerID": str(p["id"]),
            "fullName": p.get("fullName") or "",
            "debutYear": (p.get("mlbDebutDate") or "")[:4] or None,
            "active": bool(p.get("active", False)),
            "position": (p.get("primaryPosition") or {}).get("abbreviation") or None,
        }
        for p in people
        if p.get("id") and p.get("fullName")
    ]
    df = (
        pl.DataFrame(rows)
        if rows
        else pl.DataFrame(
            schema={
                "playerID": pl.Utf8,
                "fullName": pl.Utf8,
                "debutYear": pl.Utf8,
                "active": pl.Boolean,
                "position": pl.Utf8,
            }
        )
    )
    _CACHE[cache_key] = df
    return df


def _get_person(player_id: int) -> dict:
    """Fetch player biographical data from ``/api/v1/people/{id}``."""
    resp = _requests.get(f"{_MLB_API}/people/{player_id}", timeout=_TIMEOUT)
    resp.raise_for_status()
    people = resp.json().get("people", [])
    return people[0] if people else {}


def _get_yearby_year_splits(player_id: int, group: str) -> list[dict]:
    """Fetch yearByYear splits from ``/api/v1/people/{id}/stats``."""
    resp = _requests.get(
        f"{_MLB_API}/people/{player_id}/stats",
        params={"stats": "yearByYear", "group": group, "sportId": 1},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    splits: list[dict] = []
    for sg in resp.json().get("stats", []):
        splits.extend(sg.get("splits", []))
    return splits


def _get_career_split(player_id: int, group: str) -> dict:
    """Fetch a single career-totals split from ``/api/v1/people/{id}/stats``."""
    resp = _requests.get(
        f"{_MLB_API}/people/{player_id}/stats",
        params={"stats": "career", "group": group, "sportId": 1},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    for sg in resp.json().get("stats", []):
        splits = sg.get("splits", [])
        if splits:
            return splits[0].get("stat", {}) or {}
    return {}


@functools.lru_cache(maxsize=256)
def get_player_career_totals(player_id: str) -> dict:
    """Return a career-totals dict for a player, suitable for similarity scoring.

    Keys: ``playerID``, ``fullName``, ``G``, ``AB``, ``R``, ``H``, ``2B``,
    ``3B``, ``HR``, ``RBI``, ``BB``, ``SO``, ``SB``, ``AVG``, ``SLG``,
    ``POS``. Position is the player's ``primaryPosition`` abbreviation from
    the MLB Stats API.

    Two HTTP calls: ``/people/{id}`` for bio + position, and
    ``/people/{id}/stats?stats=career&group=hitting`` for the totals.
    Results are cached in-process via ``lru_cache``; clear with
    ``refresh_cache()``.
    """
    pid = int(player_id)
    try:
        person = _get_person(pid)
    except Exception as exc:
        print(
            f"[baseball-trajectory] _get_person({pid}) raised "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        person = {}
    pos = (person.get("primaryPosition") or {}).get("abbreviation", "") or ""

    try:
        stat = _get_career_split(pid, "hitting")
    except Exception as exc:
        print(
            f"[baseball-trajectory] career stats for {pid} failed: {exc}",
            file=sys.stderr,
        )
        stat = {}

    def _i(key: str) -> int:
        v = stat.get(key)
        try:
            return int(v) if v is not None else 0
        except (TypeError, ValueError):
            return 0

    h = _i("hits")
    ab = _i("atBats")
    d2 = _i("doubles")
    d3 = _i("triples")
    hr = _i("homeRuns")
    avg = h / ab if ab > 0 else 0.0
    slg = (h + d2 + 2 * d3 + 3 * hr) / ab if ab > 0 else 0.0

    return {
        "playerID": str(pid),
        "fullName": person.get("fullName", ""),
        "G": _i("gamesPlayed"),
        "AB": ab,
        "R": _i("runs"),
        "H": h,
        "2B": d2,
        "3B": d3,
        "HR": hr,
        "RBI": _i("rbi"),
        "BB": _i("baseOnBalls"),
        "SO": _i("strikeOuts"),
        "SB": _i("stolenBases"),
        "AVG": avg,
        "SLG": slg,
        "POS": pos,
    }


# ---------------------------------------------------------------------------
# Player search
# ---------------------------------------------------------------------------


def search_player(query: str, seasons_back: int = 3) -> pl.DataFrame:
    """Substring-match player names against cached MLB rosters.

    Returns up to 50 matches with columns ``playerID``, ``fullName``,
    ``debutYear``, ``finalYear``. ``finalYear`` is ``"Active"`` for
    currently-active players, otherwise the most recent season the player
    was found on a roster (a proxy for their final season).

    Walks rosters from the current season back through ``seasons_back``
    prior seasons, returning on the first season that yields matches.
    Default ``seasons_back=3`` gives fast typeahead for active and
    recently-retired players; pass a larger value for a deeper lookup
    (e.g. ``29`` to cover ~30 years of retirees).
    """
    empty = pl.DataFrame(
        schema={
            "playerID": pl.Utf8,
            "fullName": pl.Utf8,
            "debutYear": pl.Utf8,
            "finalYear": pl.Utf8,
            "position": pl.Utf8,
        }
    )
    needle = (query or "").strip().lower()
    if not needle:
        return empty

    current_year = datetime.date.today().year
    for season in range(current_year, current_year - 1 - seasons_back, -1):
        try:
            roster = _load_roster(season)
        except Exception as exc:
            print(
                f"[baseball-trajectory] _load_roster({season}) raised "
                f"{type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            continue
        if roster.is_empty():
            continue
        matches = roster.filter(
            pl.col("fullName").str.to_lowercase().str.contains(needle, literal=True)
        )
        if not matches.is_empty():
            return (
                matches.with_columns(
                    pl.when(pl.col("active"))
                    .then(pl.lit("Active"))
                    .otherwise(pl.lit(str(season)))
                    .alias("finalYear")
                )
                .select(["playerID", "fullName", "debutYear", "finalYear", "position"])
                .head(50)
            )

    print(
        f"[baseball-trajectory] search_player({query!r}): no matches in "
        f"seasons {current_year}–{current_year - seasons_back}",
        file=sys.stderr,
    )
    return empty


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_ip(ip_str: str | None) -> float:
    """Convert an official innings-pitched string to decimal innings.

    Official notation uses tenths to mean *outs*, not real tenths:
    ``"180.2"`` means 180 full innings + 2 outs = 180⅔ IP = 180.667.
    """
    if not ip_str:
        return 0.0
    parts = str(ip_str).split(".")
    full_innings = int(parts[0])
    extra_outs = int(parts[1]) if len(parts) > 1 else 0
    return full_innings + extra_outs / 3.0


def _age(season: int, birth_year: int | None, birth_month: int | None) -> int | None:
    """Age as of July 1 of *season* (the standard baseball mid-season rule)."""
    if birth_year is None:
        return None
    return season - birth_year - (1 if (birth_month or 1) >= 7 else 0)


def _parse_birth_date(birth_date: str) -> tuple[int | None, int | None]:
    """Return (birth_year, birth_month) from a YYYY-MM-DD string."""
    birth_year = int(birth_date[:4]) if len(birth_date) >= 4 else None
    birth_month = int(birth_date[5:7]) if len(birth_date) >= 7 else None
    return birth_year, birth_month


# ---------------------------------------------------------------------------
# Per-player career loaders
# ---------------------------------------------------------------------------


@functools.lru_cache(maxsize=256)
def get_batting_career(player_id: str) -> pl.DataFrame:
    """Return a per-season batting career DataFrame for a MLB player ID string.

    Columns: Season, Age, PA, AB, H, HR, AVG, OBP, SLG, OPS, ISO, BB%, K%.
    Multi-team seasons are aggregated by summing counting stats and
    recomputing all rate stats from the totals.
    """
    _EMPTY = pl.DataFrame(
        schema={
            "Season": pl.Int32,
            "Age": pl.Int32,
            "PA": pl.Int32,
            "AB": pl.Int32,
            "H": pl.Int32,
            "HR": pl.Int32,
            "AVG": pl.Float64,
            "OBP": pl.Float64,
            "SLG": pl.Float64,
            "OPS": pl.Float64,
            "ISO": pl.Float64,
            "BB%": pl.Float64,
            "K%": pl.Float64,
        }
    )
    pid = int(player_id)

    # --- biographical data (birthDate) ------------------------------------
    try:
        person = _get_person(pid)
    except Exception as exc:
        print(
            f"[baseball-trajectory] _get_person({pid}) raised "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        raise

    birth_date = person.get("birthDate") or ""
    birth_year, birth_month = _parse_birth_date(birth_date)
    if birth_year is None:
        print(
            f"[baseball-trajectory] player {pid}: birthDate missing from "
            f"/api/v1/people/{pid} — age column will be null",
            file=sys.stderr,
        )

    # --- yearByYear splits -------------------------------------------------
    try:
        splits = _get_yearby_year_splits(pid, "hitting")
    except Exception as exc:
        print(
            f"[baseball-trajectory] _get_yearby_year_splits({pid}, hitting) raised "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        raise

    rows: list[dict] = []
    for split in splits:
        season_str = split.get("season")
        stat = split.get("stat")
        if not season_str or stat is None:
            continue
        try:
            season = int(season_str)
        except (ValueError, TypeError):
            continue

        ab = int(stat.get("atBats") or 0)
        h = int(stat.get("hits") or 0)
        bb = int(stat.get("baseOnBalls") or 0)
        hbp = int(stat.get("hitByPitch") or 0)
        sf = int(stat.get("sacFlies") or 0)
        d2 = int(stat.get("doubles") or 0)
        d3 = int(stat.get("triples") or 0)
        hr = int(stat.get("homeRuns") or 0)
        so = int(stat.get("strikeOuts") or 0)
        pa = int(stat.get("plateAppearances") or 0)
        rows.append(
            {
                "Season": season,
                "AB": ab,
                "H": h,
                "BB": bb,
                "HBP": hbp,
                "SF": sf,
                "2B": d2,
                "3B": d3,
                "HR": hr,
                "SO": so,
                "PA": pa,
            }
        )

    if not rows:
        print(
            f"[baseball-trajectory] player {pid}: no batting splits returned "
            f"from /api/v1/people/{pid}/stats",
            file=sys.stderr,
        )
        return _EMPTY

    # Aggregate multi-team seasons by summing all counting stats.
    df = (
        pl.DataFrame(rows)
        .group_by("Season")
        .agg(
            pl.col("AB").sum(),
            pl.col("H").sum(),
            pl.col("BB").sum(),
            pl.col("HBP").sum(),
            pl.col("SF").sum(),
            pl.col("2B").sum(),
            pl.col("3B").sum(),
            pl.col("HR").sum(),
            pl.col("SO").sum(),
            pl.col("PA").sum(),
        )
        .sort("Season")
    )

    # Add Age column (computed in Python to handle None birth_year cleanly).
    ages = [_age(s, birth_year, birth_month) for s in df["Season"].to_list()]
    df = df.with_columns(pl.Series("Age", ages, dtype=pl.Int32))

    # Compute derived rate stats from aggregated counting totals.
    singles = pl.col("H") - pl.col("2B") - pl.col("3B") - pl.col("HR")
    tb_expr = singles + 2 * pl.col("2B") + 3 * pl.col("3B") + 4 * pl.col("HR")
    df = df.with_columns(
        (pl.col("H") / pl.col("AB")).alias("AVG"),
        (
            (pl.col("H") + pl.col("BB") + pl.col("HBP"))
            / (pl.col("AB") + pl.col("BB") + pl.col("HBP") + pl.col("SF"))
        ).alias("OBP"),
        (tb_expr / pl.col("AB")).alias("SLG"),
    ).with_columns(
        (pl.col("OBP") + pl.col("SLG")).alias("OPS"),
        (pl.col("SLG") - pl.col("AVG")).alias("ISO"),
        (pl.col("BB") / pl.col("PA")).alias("BB%"),
        (pl.col("SO") / pl.col("PA")).alias("K%"),
    )

    return (
        df.drop_nulls(subset=["Age"])
        .select(
            [
                "Season",
                "Age",
                "PA",
                "AB",
                "H",
                "HR",
                "AVG",
                "OBP",
                "SLG",
                "OPS",
                "ISO",
                "BB%",
                "K%",
            ]
        )
        .sort("Season")
    )


@functools.lru_cache(maxsize=256)
def get_pitching_career(player_id: str) -> pl.DataFrame:
    """Return a per-season pitching career DataFrame for a MLB player ID string.

    Columns: Season, Age, IP, ERA, WHIP, K/9, BB/9, HR/9, W, L, SO, BB.
    Multi-team seasons are aggregated by summing counting stats and IPouts;
    ERA and all per-9 rates are recomputed from the aggregated totals.
    ``inningsPitched`` from the API uses official notation (e.g. ``"180.2"``
    means 180⅔ IP); it is converted to IPouts for aggregation and then back
    to decimal IP for the output column.
    """
    _EMPTY = pl.DataFrame(
        schema={
            "Season": pl.Int32,
            "Age": pl.Int32,
            "IP": pl.Float64,
            "ERA": pl.Float64,
            "WHIP": pl.Float64,
            "K/9": pl.Float64,
            "BB/9": pl.Float64,
            "HR/9": pl.Float64,
            "W": pl.Int32,
            "L": pl.Int32,
            "SO": pl.Int32,
            "BB": pl.Int32,
        }
    )
    pid = int(player_id)

    # --- biographical data -------------------------------------------------
    try:
        person = _get_person(pid)
    except Exception as exc:
        print(
            f"[baseball-trajectory] _get_person({pid}) raised "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        raise

    birth_date = person.get("birthDate") or ""
    birth_year, birth_month = _parse_birth_date(birth_date)

    # --- yearByYear splits -------------------------------------------------
    try:
        splits = _get_yearby_year_splits(pid, "pitching")
    except Exception as exc:
        print(
            f"[baseball-trajectory] _get_yearby_year_splits({pid}, pitching) raised "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        raise

    rows: list[dict] = []
    for split in splits:
        season_str = split.get("season")
        stat = split.get("stat")
        if not season_str or stat is None:
            continue
        try:
            season = int(season_str)
        except (ValueError, TypeError):
            continue

        ip_decimal = _parse_ip(stat.get("inningsPitched"))
        ip_outs = round(ip_decimal * 3)
        rows.append(
            {
                "Season": season,
                "W": int(stat.get("wins") or 0),
                "L": int(stat.get("losses") or 0),
                "G": int(stat.get("gamesPlayed") or 0),
                "GS": int(stat.get("gamesStarted") or 0),
                "SV": int(stat.get("saves") or 0),
                "H": int(stat.get("hits") or 0),
                "ER": int(stat.get("earnedRuns") or 0),
                "HR": int(stat.get("homeRuns") or 0),
                "BB": int(stat.get("baseOnBalls") or 0),
                "SO": int(stat.get("strikeOuts") or 0),
                "IPouts": ip_outs,
            }
        )

    if not rows:
        print(
            f"[baseball-trajectory] player {pid}: no pitching splits returned "
            f"from /api/v1/people/{pid}/stats",
            file=sys.stderr,
        )
        return _EMPTY

    # Aggregate multi-team seasons.
    df = (
        pl.DataFrame(rows)
        .group_by("Season")
        .agg(
            pl.col("W").sum(),
            pl.col("L").sum(),
            pl.col("G").sum(),
            pl.col("GS").sum(),
            pl.col("SV").sum(),
            pl.col("H").sum(),
            pl.col("ER").sum(),
            pl.col("HR").sum(),
            pl.col("BB").sum(),
            pl.col("SO").sum(),
            pl.col("IPouts").sum(),
        )
        .sort("Season")
    )

    # Add Age column.
    ages = [_age(s, birth_year, birth_month) for s in df["Season"].to_list()]
    df = df.with_columns(pl.Series("Age", ages, dtype=pl.Int32))

    # Compute rate stats from aggregated counting totals.
    df = df.with_columns(
        (pl.col("IPouts") / 3.0).alias("IP"),
    ).with_columns(
        (27.0 * pl.col("ER") / pl.col("IPouts")).alias("ERA"),
        (3.0 * (pl.col("BB") + pl.col("H")) / pl.col("IPouts")).alias("WHIP"),
        (27.0 * pl.col("SO") / pl.col("IPouts")).alias("K/9"),
        (27.0 * pl.col("BB") / pl.col("IPouts")).alias("BB/9"),
        (27.0 * pl.col("HR") / pl.col("IPouts")).alias("HR/9"),
    )

    return (
        df.filter(pl.col("IPouts") > 0)
        .drop_nulls(subset=["Age"])
        .select(
            [
                "Season",
                "Age",
                "IP",
                "ERA",
                "WHIP",
                "K/9",
                "BB/9",
                "HR/9",
                "W",
                "L",
                "SO",
                "BB",
            ]
        )
        .sort("Season")
    )
