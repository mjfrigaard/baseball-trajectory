"""Shiny app for baseball-trajectory.

A small interactive tool for exploring a player's career arc on a single
metric (OPS for batters, ERA for pitchers, and so on). The user searches
for a player, picks a metric, and the app fits a weighted quadratic curve
to their per-season values and renders the trajectory.

The app uses Shiny for Python (core API, not express) and Polars for all
data wrangling.
"""

from __future__ import annotations

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


# ----------------------------------------------------------------------
# UI definition
# ----------------------------------------------------------------------
# The sidebar holds all input controls; the main panel shows three cards:
# the trajectory plot, a one-row career summary, and the per-season log.
app_ui = ui.page_sidebar(
    ui.sidebar(
        # Toggle between batter metrics (OPS, ...) and pitcher metrics (ERA, ...).
        ui.input_radio_buttons(
            "player_type",
            "Player type",
            {"batter": "Batter", "pitcher": "Pitcher"},
        ),
        # Free-text search box. Auto-suggests as the user types (≥2 chars).
        ui.input_text(
            "player_name",
            "Player name",
            placeholder="Start typing… e.g. Trout",
        ),
        # Manual trigger. Forces a fresh search and resets the cached
        # player selection — useful when switching to a new player after
        # one is already loaded (the dropdown gets recreated and the
        # auto-fired player_id event can be missed otherwise).
        ui.input_action_button("search", "Search", class_="btn-primary"),
        # Filled in by the server once a search has matches — a dropdown
        # of players to pick from.
        ui.output_ui("player_picker"),
        # Choices populated by the server based on player_type.
        ui.input_select("metric", "Metric", choices=[]),
        # Drops noisy partial seasons (cups of coffee, injury years, etc).
        ui.input_numeric(
            "min_weight",
            "Min PA / IP per season",
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
    ),
    # Page-level loading indicator: shows a top progress bar + subtle dimmer
    # while reactive outputs (the plot, the data tables) are recalculating.
    ui.busy_indicators.use(),
    ui.card(
        ui.card_header("Career Trajectory"),
        ui.output_plot("trajectory_plot", height="500px"),
    ),
    ui.card(
        ui.card_header("Career Summary"),
        # Using output_data_frame (not output_table) so we stay Polars-only —
        # render.table would round-trip through pandas.
        ui.output_data_frame("summary_table"),
    ),
    ui.card(
        ui.card_header("Season Log"),
        ui.output_data_frame("season_table"),
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

    # ---- Typeahead -------------------------------------------------------
    @reactive.effect
    def _auto_search():
        # Fires on every keystroke. Updates the dropdown ONLY — does not
        # touch committed_player_id, so the currently-rendered player
        # stays put until the user explicitly clicks Search.
        query = (input.player_name() or "").strip()
        if len(query) < 2:
            search_results.set(pl.DataFrame())
            return
        try:
            # Narrow window: fast for active and recently-retired players.
            search_results.set(data.search_player(query, seasons_back=3))
        except Exception as exc:
            ui.notification_show(
                f"Could not load player data: {exc}",
                type="error",
                duration=8,
            )

    # ---- Commit ----------------------------------------------------------
    @reactive.effect
    @reactive.event(input.search)
    def _run_search():
        # Search button = "commit the selection AND/OR widen the search."
        # Two cases:
        #   1. Dropdown has a valid pick → commit it, plot loads.
        #   2. Dropdown is empty (typeahead found nothing) → run a deep
        #      lookup (~30 years of rosters) so retirees like Pujols turn
        #      up. The user then picks from the new dropdown and clicks
        #      Search again to commit.
        try:
            pid = input.player_id()
        except Exception:
            pid = None
        df = search_results.get()

        if pid and not df.is_empty():
            match = df.filter(pl.col("playerID") == pid)
            if not match.is_empty():
                selected_player_name.set(match["fullName"][0])
                committed_player_id.set(pid)
                return

        # No valid selection — fall back to deep search.
        query = (input.player_name() or "").strip()
        if not query:
            ui.notification_show("Enter a player name", type="warning")
            return
        try:
            results = data.search_player(query, seasons_back=29)
        except Exception as exc:
            ui.notification_show(
                f"Could not load player data: {exc}",
                type="error",
                duration=8,
            )
            return
        if results.is_empty():
            ui.notification_show(
                f"No players match {query!r} in the last ~30 seasons.",
                type="warning",
                duration=6,
            )
            return
        search_results.set(results)
        ui.notification_show(
            "Pick a player from the list, then click Search again.",
            type="message",
            duration=4,
        )

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
        df = search_results.get()
        if df.is_empty():
            return ui.div()
        choices = {
            row["playerID"]: (
                f"{row['fullName']}"
                + (f" (debut {row['debutYear']})" if row["debutYear"] else "")
                + (f" — {row['finalYear']}" if row["finalYear"] else "")
            )
            for row in df.iter_rows(named=True)
        }
        return ui.input_select("player_id", "Select player", choices=choices)

    # ---- Metric list synced to player type ------------------------------
    @reactive.effect
    def _sync_metric_choices():
        # When the user toggles batter/pitcher, swap the metric dropdown to
        # the relevant list. Runs once at startup as well to populate it.
        if input.player_type() == "batter":
            choices = list(BATTING_METRICS.keys())
        else:
            choices = list(PITCHING_METRICS.keys())
        ui.update_select("metric", choices=choices, selected=choices[0])

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
        return "PA" if input.player_type() == "batter" else "IP"

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
            if input.player_type() == "batter":
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
            return plot_empty("Type a name, pick from the list, then click Search")
        metric = input.metric()
        if not metric:
            return plot_empty("Pick a metric")
        weight_col = _weight_col()
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
        s = summarize_career(df, y_col=metric, weight_col=weight_col)
        best = s["best_season"] or {}
        # One-row summary: career-weighted average, total opportunity,
        # best season, and the fitted peak age.
        summary = pl.DataFrame(
            {
                f"Weighted {metric}": [s["weighted_mean"]],
                f"Total {weight_col}": [s["total_weight"]],
                "Best Season": [best.get("Season")],
                f"Best {metric}": [best.get(metric)],
                "Best Age": [best.get("Age")],
                "Peak Age": [s["peak_age"]],
            }
        )
        return render.DataGrid(summary)

    @render.data_frame
    def season_table():
        df = career_df()
        if df is None or df.is_empty():
            return pl.DataFrame()
        # Shiny supports Polars DataFrames natively in DataGrid.
        return render.DataGrid(df, height="300px")


# Standard Shiny entry point — picked up by both `shiny run` and our
# console script in __main__.py.
app = App(app_ui, server)
