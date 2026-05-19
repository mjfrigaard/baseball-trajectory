"""Shiny app for baseball-trajectory.

A small interactive tool for exploring a player's career arc on a single
metric (OPS for batters, ERA for pitchers, and so on). The user searches
for a player, picks a metric, and the app fits a weighted quadratic curve
to their per-season values and renders the trajectory.

The app uses Shiny for Python (core API, not express) and Polars for all
data wrangling.
"""

from __future__ import annotations

from pathlib import Path

import great_tables as gt
import polars as pl
from shiny import App, Inputs, Outputs, Session, reactive, render, ui

from baseball_trajectory import data
from baseball_trajectory.model import (
    BATTING_METRICS,
    PITCHING_METRICS,
    fit_player_curve,
    is_lower_better,
    summarize_career,
)
from baseball_trajectory.plots import plot_empty, plot_trajectory

_STYLES_PATH = Path(__file__).parent / "styles.css"

# Primary-position codes that count as a "pitcher" for search filtering.
# P = pure pitcher, TWP = two-way player (Ohtani-style; pitches *and*
# bats, so they appear in both modes). Position players (C, 1B, OF, ...)
# essentially never have enough pitching seasons to fit a curve, so
# they're excluded from the Pitcher dropdown.
_PITCHER_POSITION_CODES = frozenset({"P", "TWP"})


def _filter_by_position(df: pl.DataFrame, position_mode: str) -> pl.DataFrame:
    """Drop search-result rows whose primary position doesn't fit the
    Position toggle. Rows with a null primary position are excluded —
    we can't confirm the player has enough data on either side.
    """
    if df.is_empty() or "position" not in df.columns:
        return df
    not_null = pl.col("position").is_not_null()
    if position_mode == "pitcher":
        return df.filter(
            not_null & pl.col("position").is_in(list(_PITCHER_POSITION_CODES))
        )
    # Batter mode: anyone *not* a pure pitcher. TWP stays in because
    # two-way players bat too.
    return df.filter(not_null & (pl.col("position") != "P"))


# Human-readable labels shown in the Metric dropdown. The keys match
# BATTING_METRICS / PITCHING_METRICS so server logic still uses the bare
# acronym (e.g. "OPS") as a column name.
_BATTING_METRIC_LABELS: dict[str, str] = {
    "OPS": "OPS — On-base + Slugging",
    "OBP": "OBP — On-base percentage",
    "SLG": "SLG — Slugging percentage",
    "AVG": "AVG — Batting average",
    "HR": "HR — Home runs",
    "ISO": "ISO — Isolated power (SLG − AVG)",
}
_PITCHING_METRIC_LABELS: dict[str, str] = {
    "ERA": "ERA — Earned run average",
    "WHIP": "WHIP — Walks + hits per inning pitched",
    "K/9": "K/9 — Strikeouts per 9 innings",
    "BB/9": "BB/9 — Walks per 9 innings",
    "HR/9": "HR/9 — Home runs per 9 innings",
}

# Plain-language descriptions used wherever a metric name appears in the
# main panel (plot title/axis, summary caption, season-log rows). Shorter
# than _METRIC_DEFINITIONS — just the prose name of the stat, no formula.
_METRIC_DESCRIPTIONS: dict[str, str] = {
    "OPS": "On-base + Slugging",
    "OBP": "On-base percentage",
    "SLG": "Slugging percentage",
    "AVG": "Batting average",
    "HR": "Home runs",
    "ISO": "Isolated power",
    "ERA": "Earned run average",
    "WHIP": "Walks + hits per inning pitched",
    "K/9": "Strikeouts per 9 innings",
    "BB/9": "Walks per 9 innings",
    "HR/9": "Home runs per 9 innings",
}

# One-line definitions shown under the Metric dropdown — formula plus a
# rough anchor for "what's good?". Full definitions and benchmarks live
# in docs/metrics.md.
_METRIC_DEFINITIONS: dict[str, str] = {
    "OPS": "OBP + SLG. Higher is better; .900+ is All-Star tier.",
    "OBP": "(H + BB + HBP) / (AB + BB + HBP + SF). Higher is better; .400+ is elite.",
    "SLG": "Total bases per at-bat. Higher is better; .500+ is excellent power.",
    "AVG": "H / AB — hits per at-bat. Higher is better; .300+ is excellent.",
    "HR": "Home-run count per season. 30+ marks a power-hitter season.",
    "ISO": "SLG − AVG. Pure extra-base power; .200+ is excellent.",
    "ERA": "9 × ER / IP — earned runs per 9 innings. Lower is better; under 3.00 is elite.",
    "WHIP": "(BB + H) / IP — baserunners per inning. Lower is better; under 1.10 is elite.",
    "K/9": "9 × K / IP. Higher is better; 9.0+ marks a power pitcher.",
    "BB/9": "9 × BB / IP. Lower is better; under 2.5 is excellent control.",
    "HR/9": "9 × HR / IP. Lower is better; under 0.8 is excellent.",
}


# ----------------------------------------------------------------------
# UI definition
# ----------------------------------------------------------------------
# The sidebar holds all input controls; the main panel shows three cards:
# the trajectory plot, a one-row career summary, and the per-season log.
app_ui = ui.page_sidebar(
    ui.sidebar(
        # Active vs. retired controls how far back the player search reaches.
        # Active uses a small (3-season) roster window for fast typeahead;
        # Retired widens to ~50 seasons so older retirees (Griffey, Ryan, …)
        # come up.
        ui.input_select(
            "career_status",
            "Player type",
            {"active": "Active players", "retired": "Retired players"},
            selected="active",
        ),
        # Batter vs. pitcher — drives the metric list and the weight column.
        # Wrapped in a spacing block so there's visible breathing room
        # between Position and the Player name controls below it.
        ui.tags.div(
            ui.input_radio_buttons(
                "position",
                "Position",
                {"batter": "Batter", "pitcher": "Pitcher"},
            ),
            class_="bbt-position-block",
        ),
        # Free-text search box. Auto-suggests as the user types (≥2 chars).
        ui.input_text(
            "player_name",
            "Player name",
            placeholder="Start typing… e.g. Trout",
        ),
        # Step 1 — Search. Updates the dropdown of matches; does NOT
        # load stats. Use this when the live typeahead found nothing
        # (the Search button does a wider, deeper season lookup).
        ui.input_action_button("search", "Search", class_="btn-outline-primary"),
        # Dropdown of matches, populated by the server. Labels include
        # primary position so users can confirm they're picking a player
        # whose career data matches the Position toggle above.
        ui.output_ui("player_picker"),
        # Read-only summary of the picked dropdown row — full name,
        # primary position, debut/final season. Helps confirm the pick
        # before committing.
        ui.output_ui("selected_player_info"),
        # Step 2 — Get Stats. Commits the picked player; this is what
        # actually loads the trajectory plot and tables.
        ui.input_action_button("get_stats", "Get Stats", class_="btn-primary"),
        # Choices populated by the server based on position; labels include
        # the metric expansion so users don't have to memorize acronyms.
        ui.input_select("metric", "Metric", choices=[]),
        # Short inline definition of the currently-selected metric.
        # Updates whenever the dropdown changes. See metric_definition()
        # in the server and docs/metrics.md for the full breakdown.
        ui.output_ui("metric_definition"),
        # Drops noisy partial seasons (cups of coffee, injury years, etc).
        # Description lives in the inline tooltip ⓘ icon next to the label.
        ui.input_numeric(
            "min_weight",
            ui.tags.span(
                "Min PA / IP per season ",
                ui.tooltip(
                    ui.tags.span(
                        "ⓘ",
                        style=(
                            "cursor: help; color: #888; "
                            "font-weight: normal; margin-left: 2px;"
                        ),
                    ),
                    "Minimum plate appearances (batters) or innings "
                    "pitched (pitchers) for a season to count toward the "
                    "curve fit. Filters out partial seasons, September "
                    "call-ups, and injury-shortened years. Typical "
                    "thresholds: 502 PA / 162 IP qualify a player for "
                    "season-leading stats; 300 PA / 100 IP for a "
                    "full-time regular; 100 (the default) keeps most "
                    "non-trivial seasons; 0 disables the filter.",
                    placement="right",
                ),
            ),
            value=100,
            min=0,
        ),
        # Force-refresh the cached MLB Stats API data (useful if the app has
        # been running across a season boundary or after a roster move).
        ui.input_action_button(
            "refresh_cache",
            "Refresh data cache",
            class_="btn-secondary",
        ),
        ui.tags.small(
            "Data: MLB Stats API (statsapi.mlb.com). Current through the active season."
        ),
        # Wider than the default (~250px) so the descriptive metric labels
        # ("OPS — On-base + Slugging") fit on a single line.
        width=340,
    ),
    # Project-wide stylesheet — MLB navy + red accents.
    ui.include_css(_STYLES_PATH),
    # Page-level loading indicator: shows a top progress bar + subtle dimmer
    # while reactive outputs (the plot, the data tables) are recalculating.
    ui.busy_indicators.use(),
    ui.card(
        ui.card_header("Career Trajectory"),
        # Plain-language description of the active metric, shown just
        # under the card header. The plot itself also embeds it in the
        # title and y-axis label.
        ui.output_ui("metric_caption"),
        ui.output_plot("trajectory_plot", height="500px"),
    ),
    ui.card(
        ui.card_header("Career Summary"),
        ui.output_ui("metric_caption_summary"),
        # Using output_data_frame (not output_table) so we stay Polars-only —
        # render.table would round-trip through pandas.
        ui.output_data_frame("summary_table"),
    ),
    ui.card(
        ui.card_header("Season Log"),
        # Rendered as great-tables HTML (one row per metric, with an inline
        # nanoplot of year-by-year values) — see season_table() in server.
        # Each row's Metric column carries its plain-language description.
        ui.output_ui("season_table"),
    ),
    title="Baseball Trajectory",
)


# ----------------------------------------------------------------------
# Server logic
# ----------------------------------------------------------------------
def server(input: Inputs, output: Outputs, session: Session) -> None:
    # Matches from the most recent search — drives the dropdown only.
    search_results: reactive.value[pl.DataFrame] = reactive.value(pl.DataFrame())
    # Display name of the player whose stats are currently rendered.
    selected_player_name: reactive.value[str] = reactive.value("")
    # The "loaded" player. Stays empty until the user clicks Search; this
    # is what career_df depends on, NOT input.player_id. Decoupling means
    # picking a name from the dropdown is just a preview — the user has to
    # click Search to actually load the stats.
    committed_player_id: reactive.value[str] = reactive.value("")
    # True when the latest search returned matches but the Position
    # filter dropped them all (e.g. searching "Trout" in Pitcher mode
    # finds Mike Trout, but he's a CF and gets filtered out). Lets the
    # picker show a position-aware empty message.
    position_filter_emptied: reactive.value[bool] = reactive.value(False)

    # ---- Typeahead -------------------------------------------------------
    @reactive.effect
    def _auto_search():
        # Fires on every keystroke. Updates the dropdown ONLY — does not
        # touch committed_player_id, so the currently-rendered player
        # stays put until the user explicitly clicks Search.
        query = (input.player_name() or "").strip()
        if len(query) < 2:
            search_results.set(pl.DataFrame())
            position_filter_emptied.set(False)
            return
        # Active mode: small 3-season window for fast typeahead. Retired
        # mode: ~50 seasons so older retirees (Griffey Jr. 2010, Nolan
        # Ryan 1993, …) come up. First keystroke in retired mode pays a
        # roster-download cost; subsequent keystrokes are local filters.
        seasons_back = 50 if input.career_status() == "retired" else 3
        try:
            raw = data.search_player(query, seasons_back=seasons_back)
        except Exception as exc:
            ui.notification_show(
                f"Could not load player data: {exc}",
                type="error",
                duration=8,
            )
            return
        # Position-aware filter: hide non-pitchers in Pitcher mode and
        # vice versa. Re-fires when the Position toggle changes.
        filtered = _filter_by_position(raw, input.position())
        position_filter_emptied.set(not raw.is_empty() and filtered.is_empty())
        search_results.set(filtered)

    # ---- Search (find players, no commit) -------------------------------
    @reactive.effect
    @reactive.event(input.search)
    def _run_search():
        # Search runs a deeper lookup than auto-typeahead and refreshes
        # the dropdown. It never loads stats — that's Get Stats' job.
        query = (input.player_name() or "").strip()
        if not query:
            ui.notification_show("Enter a player name", type="warning")
            return
        deep_seasons = 80 if input.career_status() == "retired" else 29
        try:
            results = data.search_player(query, seasons_back=deep_seasons)
        except Exception as exc:
            ui.notification_show(
                f"Could not load player data: {exc}",
                type="error",
                duration=8,
            )
            return
        if results.is_empty():
            ui.notification_show(
                f"No players match {query!r}.",
                type="warning",
                duration=6,
            )
            return
        filtered = _filter_by_position(results, input.position())
        if not results.is_empty() and filtered.is_empty():
            other = "Batter" if input.position() == "pitcher" else "Pitcher"
            ui.notification_show(
                f"Found matches for {query!r}, but none are "
                f"{input.position()}s. Try switching Position to {other}.",
                type="warning",
                duration=8,
            )
        position_filter_emptied.set(not results.is_empty() and filtered.is_empty())
        search_results.set(filtered)

    # ---- Get Stats (commit picked player, load plot) --------------------
    @reactive.effect
    @reactive.event(input.get_stats)
    def _get_stats():
        try:
            pid = input.player_id()
        except Exception:
            pid = None
        if not pid:
            ui.notification_show(
                "Pick a player from the list first.",
                type="warning",
                duration=5,
            )
            return

        df = search_results.get()
        if not df.is_empty():
            match = df.filter(pl.col("playerID") == pid)
            if not match.is_empty():
                row = match.to_dicts()[0]
                selected_player_name.set(row.get("fullName") or pid)

                # Gentle warning when the Position toggle disagrees with
                # the player's primary position — covers the "picked
                # Trout in Pitcher mode" failure mode by telling the user
                # before they see an empty plot.
                pos = (row.get("position") or "").upper()
                wants_pitcher = input.position() == "pitcher"
                is_pitcher = pos == "P"
                if pos and (wants_pitcher != is_pitcher):
                    other = "Batter" if wants_pitcher else "Pitcher"
                    ui.notification_show(
                        f"{row.get('fullName')} is listed as {pos}. "
                        f"Switch Position to {other} for matching stats.",
                        type="warning",
                        duration=8,
                    )
        committed_player_id.set(pid)

    @reactive.effect
    @reactive.event(input.refresh_cache)
    def _refresh_cache():
        try:
            data.refresh_cache()
            ui.notification_show(
                "Data cache cleared. Next search will re-download.",
                type="message",
            )
        except Exception as exc:
            ui.notification_show(f"Refresh failed: {exc}", type="error", duration=8)

    @render.ui
    def player_picker():
        # Once a search returns matches, show a dropdown so the user can
        # pick the right person (multiple players can share a name).
        # Labels include primary position so the user can spot a
        # position/career-status mismatch *before* clicking Get Stats.
        df = search_results.get()
        if df.is_empty():
            if position_filter_emptied.get():
                pos = input.position()
                other = "Batter" if pos == "pitcher" else "Pitcher"
                return ui.tags.p(
                    f"No matching {pos}s found. Try a different name "
                    f"or switch Position to {other}.",
                    style=("color: #888; font-style: italic; margin: 0.5rem 0;"),
                )
            return ui.div()
        choices = {}
        for row in df.iter_rows(named=True):
            label = row["fullName"]
            if row.get("position"):
                label += f" — {row['position']}"
            if row.get("debutYear") and row.get("finalYear"):
                label += f" ({row['debutYear']}–{row['finalYear']})"
            choices[row["playerID"]] = label
        return ui.input_select("player_id", "Select player", choices=choices)

    @render.ui
    def selected_player_info():
        # Read-only card describing the player currently picked in the
        # dropdown. Renders nothing until both a search has happened AND
        # a row is selected.
        try:
            pid = input.player_id()
        except Exception:
            return ui.div()
        if not pid:
            return ui.div()
        df = search_results.get()
        if df.is_empty():
            return ui.div()
        match = df.filter(pl.col("playerID") == pid)
        if match.is_empty():
            return ui.div()
        row = match.to_dicts()[0]
        pos = row.get("position") or "?"
        debut = row.get("debutYear") or "?"
        final = row.get("finalYear") or "?"
        return ui.tags.div(
            ui.tags.span("Selected player", class_="bbt-selected-label"),
            ui.tags.strong(row.get("fullName") or pid),
            ui.tags.br(),
            ui.tags.small(
                f"{pos} · {debut}–{final}",
                style="color: #666;",
            ),
            class_="bbt-selected-player",
        )

    # ---- Metric list synced to position ---------------------------------
    @reactive.effect
    def _sync_metric_choices():
        # When the user toggles batter/pitcher, swap the metric dropdown to
        # the relevant list. The labels are descriptive (e.g. "OPS —
        # On-base + Slugging") while the underlying value stays the bare
        # acronym so the rest of the server code keeps using it as a
        # column name.
        labels = (
            _BATTING_METRIC_LABELS
            if input.position() == "batter"
            else _PITCHING_METRIC_LABELS
        )
        first = next(iter(labels))
        ui.update_select("metric", choices=labels, selected=first)

    @render.ui
    def metric_definition():
        # Short formula/benchmark line shown under the metric dropdown.
        # Updates whenever input.metric changes.
        m = input.metric()
        if not m or m not in _METRIC_DEFINITIONS:
            return ui.div()
        return ui.div(
            ui.tags.small(
                _METRIC_DEFINITIONS[m],
                style="color: #555;",
            ),
            style="margin: -0.5rem 0 0.75rem 0;",
        )

    def _metric_caption(m: str) -> ui.Tag:
        # Reused by both the Career Trajectory and Career Summary cards.
        return ui.tags.div(
            ui.tags.strong(m),
            f" — {_METRIC_DESCRIPTIONS.get(m, '')}",
            class_="bbt-metric-caption",
        )

    @render.ui
    def metric_caption():
        m = input.metric()
        if not m or m not in _METRIC_DESCRIPTIONS:
            return ui.div()
        return _metric_caption(m)

    @render.ui
    def metric_caption_summary():
        m = input.metric()
        if not m or m not in _METRIC_DESCRIPTIONS:
            return ui.div()
        return _metric_caption(m)

    # ---- Small helpers reading the dynamic player_id input --------------
    def _selected_player_id() -> str | None:
        # The player_id dropdown is created dynamically by player_picker,
        # so accessing it before the first search raises a SilentException.
        try:
            value = input.player_id()
        except Exception:
            return None
        return value or None

    def _weight_col() -> str:
        return "PA" if input.position() == "batter" else "IP"

    def _player_name_for(player_id: str) -> str:
        # Prefer the cached selection name (survives the search box being
        # cleared); fall back to the live search results, then to the raw ID.
        cached = selected_player_name.get()
        if cached:
            return cached
        df = search_results.get()
        if not df.is_empty():
            match = df.filter(pl.col("playerID") == player_id)
            if not match.is_empty():
                return match["fullName"][0]
        return player_id

    # ---- Career frame, filtered by the min-weight knob ------------------
    @reactive.calc
    def career_df() -> pl.DataFrame | None:
        # Reads committed_player_id, NOT the live dropdown — so changing
        # the dropdown selection alone doesn't load new stats. The user
        # has to click Search to commit.
        player_id = committed_player_id.get() or None
        if player_id is None:
            return None
        try:
            if input.position() == "batter":
                df = data.get_batting_career(player_id)
            else:
                df = data.get_pitching_career(player_id)
        except Exception as exc:
            ui.notification_show(
                f"Could not load career data: {exc}",
                type="error",
                duration=8,
            )
            return None
        weight_col = _weight_col()
        threshold = input.min_weight() or 0
        return df.filter(pl.col(weight_col) >= threshold)

    # ---- Outputs ---------------------------------------------------------
    @render.plot
    def trajectory_plot():
        df = career_df()
        if df is None or df.is_empty():
            return plot_empty("Search, pick from the list, then click Get Stats")
        metric = input.metric()
        if not metric:
            return plot_empty("Pick a metric")
        weight_col = _weight_col()
        # Guard against a Position/player mismatch (e.g. Batter selected
        # while the committed player is a pitcher). career_df may have
        # rows for the wrong group, in which case the metric column
        # won't be present.
        if metric not in df.columns or weight_col not in df.columns:
            return plot_empty(
                f"No {metric} data for this player — try the other "
                f"Position (Batter / Pitcher)."
            )
        fit = fit_player_curve(df, y_col=metric, weight_col=weight_col)
        if fit is None:
            return plot_empty("Not enough qualifying seasons to fit a curve")
        return plot_trajectory(
            df,
            fit,
            y_col=metric,
            weight_col=weight_col,
            player_name=_player_name_for(committed_player_id.get() or ""),
            lower_better=is_lower_better(metric),
            metric_description=_METRIC_DESCRIPTIONS.get(metric),
        )

    @render.data_frame
    def summary_table():
        df = career_df()
        if df is None or df.is_empty():
            return pl.DataFrame()
        metric = input.metric()
        if not metric:
            return pl.DataFrame()
        weight_col = _weight_col()
        if metric not in df.columns or weight_col not in df.columns:
            return pl.DataFrame()
        s = summarize_career(df, y_col=metric, weight_col=weight_col)
        best = s["best_season"] or {}

        def _round2(value):
            return round(value, 2) if value is not None else None

        # One-row summary: career-weighted average, total opportunity,
        # best season, and the fitted peak age. Rate stats and peak age
        # are rounded to two decimals for display.
        summary = pl.DataFrame(
            {
                f"Weighted {metric}": [_round2(s["weighted_mean"])],
                f"Total {weight_col}": [s["total_weight"]],
                "Best Season": [best.get("Season")],
                f"Best {metric}": [_round2(best.get(metric))],
                "Best Age": [best.get("Age")],
                "Peak Age": [_round2(s["peak_age"])],
            }
        )
        return render.DataGrid(summary)

    @render.ui
    def season_table():
        # Each row is a metric for the active player type; the Trend column
        # is a great-tables nanoplot of year-by-year values.
        df = career_df()
        if df is None or df.is_empty():
            return ui.div()

        metric_map = (
            BATTING_METRICS if input.position() == "batter" else PITCHING_METRICS
        )
        # Filter to metrics actually present in the frame — guards against
        # a Position/player mismatch where the committed player has no
        # data for the requested group.
        metric_cols = [m for m in metric_map.keys() if m in df.columns]
        if not metric_cols:
            return ui.div(
                ui.tags.p(
                    "No matching stats — try the other Position toggle.",
                    style="color: #666; font-style: italic;",
                ),
            )

        df_sorted = df.sort("Season")
        seasons = df_sorted["Season"].to_list()
        if not seasons:
            return ui.div()
        span = f"{seasons[0]}–{seasons[-1]}"

        rows = []
        for m in metric_cols:
            values = [v for v in df_sorted[m].to_list() if v is not None]
            if not values:
                continue
            label = (
                f"{m} — {_METRIC_DESCRIPTIONS[m]}" if m in _METRIC_DESCRIPTIONS else m
            )
            rows.append({"Metric": label, "Years": span, "Trend": values})
        if not rows:
            return ui.div()

        table_df = pl.DataFrame(rows)
        tbl = gt.GT(table_df).fmt_nanoplot(columns="Trend", plot_type="line")
        return ui.HTML(tbl.as_raw_html())


# Standard Shiny entry point — picked up by both `shiny run` and our
# console script in __main__.py.
app = App(app_ui, server)
