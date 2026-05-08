# User guide

The sidebar workflow is two-step: **find a player, then commit.**

## 1. Pick a player type

The *Player type* radio swaps the metric list:

| Player type | Available metrics                |
| ----------- | -------------------------------- |
| Batter      | OPS, OBP, SLG, AVG, HR, ISO      |
| Pitcher     | ERA, WHIP, K/9, BB/9, HR/9       |

The *weight* used in the curve fit follows automatically: PA for
batters, IP for pitchers.

## 2. Find your player

### Typeahead (active and recently retired)

Start typing a name (≥2 characters). The dropdown updates as you type,
showing matches from the current MLB season and the three prior
seasons. The first keystroke incurs a one-time ~1-second pause while
the season roster downloads; everything after is sub-millisecond.

### Deep search (older retirees)

If the dropdown stays empty, the player isn't on a recent roster.
Click **Search** anyway. The app falls back to a ~30-season lookup
that covers most modern retirees (Albert Pujols, Adrián Beltré, Ichiro
Suzuki, etc.). You'll see a notification asking you to pick from the
new dropdown.

## 3. Commit the selection

Click **Search**. This loads the player's career stats and updates:

- The trajectory plot.
- The career summary table (one row).
- The season-by-season log.

!!! note "Why a separate commit step?"

    Picking a name in the dropdown does not load stats on its own —
    only Search does. The dropdown updates as you type, and
    auto-loading on every interim selection would thrash the chart and
    waste roster fetches.

## 4. Adjust filters

- **Min PA / IP per season** — drops noisy partial seasons before the
  curve is fit. Default is 100; raise for full-time players, lower to
  include rookie debuts.
- **Refresh data cache** — clears the in-process roster and career
  caches. Useful when you've left the app running across a roster
  move or a new MLB game day.

## Reading the chart

- Each dot is a season; **dot size scales with playing time** (PA or
  IP).
- The solid curve is the **weighted quadratic fit**.
- The shaded ribbon is the **95% confidence band**.
- The dashed vertical line is the **fitted peak age** — only drawn
  when the quadratic is concave-down (i.e., a real peak exists).
- For metrics where lower is better (ERA, WHIP, BB/9, HR/9) the y-axis
  is **inverted** so the peak is at the top of the chart.

## Switching players

Clear the *Player name* box, type the next name, pick from the new
dropdown, click **Search**. The plot and tables update to the newly
committed player.
