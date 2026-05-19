# Metrics

Reference for every stat the app can plot, plus the **Min PA / IP**
knob that filters per-season data before the curve is fit. All
formulas use the abbreviations as they appear in the underlying MLB
Stats API.

## Batting metrics

For batters, the **weight column** in the weighted least-squares fit
is PA (plate appearances). Anchor points below are full-season values
for full-time players.

### AVG — Batting average

Hits per at-bat:

```
AVG = H / AB
```

A decimal between 0 and 1.

| Range  | Read                  |
| ------ | --------------------- |
| `.300+` | Excellent             |
| `.275`  | Solid regular         |
| `.250`  | Average MLB hitter    |
| `.220`  | Below average         |

### OBP — On-base percentage

Fraction of plate appearances where the batter reached base by hit,
walk, or hit-by-pitch:

```
OBP = (H + BB + HBP) / (AB + BB + HBP + SF)
```

Where `SF` = sacrifice flies. OBP excludes errors and fielder's
choices.

| Range   | Read         |
| ------- | ------------ |
| `.400+` | Elite        |
| `.360`  | All-Star     |
| `.330`  | Solid regular|
| `.300`  | Below average|

### SLG — Slugging percentage

Total bases gained per at-bat. A double counts as 2, a triple as 3, a
home run as 4:

```
SLG = (1B + 2·2B + 3·3B + 4·HR) / AB
```

| Range   | Read           |
| ------- | -------------- |
| `.500+` | Power hitter   |
| `.450`  | Strong power   |
| `.400`  | Average        |
| `.350`  | Limited power  |

### OPS — On-base + Slugging

The sum of OBP and SLG. The single most-used summary of offensive
value:

```
OPS = OBP + SLG
```

| Range   | Read           |
| ------- | -------------- |
| `.900+` | All-Star tier  |
| `.800`  | Above average  |
| `.700`  | Average        |
| `.600`  | Below average  |

### HR — Home runs

The count of home runs in a season — a raw total, not a rate stat.
The curve fits this against age directly.

| Range  | Read (full season) |
| ------ | ------------------ |
| `40+`  | Elite power        |
| `30`   | Power hitter       |
| `20`   | Full-time regular  |
| `10`   | Part-time / contact|

### ISO — Isolated power

Pure extra-base power, with singles' contribution removed:

```
ISO = SLG − AVG
```

A batter who hits only singles has SLG = AVG and therefore ISO = 0.

| Range   | Read           |
| ------- | -------------- |
| `.250+` | Elite power    |
| `.200`  | Power threat   |
| `.150`  | Average        |
| `.100`  | Light power    |

## Pitching metrics

For pitchers, the weight column is IP (innings pitched). All per-9
rates multiply by 9 to extrapolate to a full game's worth of innings.

### ERA — Earned run average

Earned runs allowed per 9 innings:

```
ERA = 9 × ER / IP
```

Where `ER` excludes runs that scored after a fielding error. **Lower
is better.**

| Range  | Read           |
| ------ | -------------- |
| `<2.00`| Cy Young tier  |
| `3.00` | All-Star       |
| `4.00` | Solid regular  |
| `5.00+`| Below average  |

### WHIP — Walks + Hits per Inning Pitched

Baserunners allowed per inning:

```
WHIP = (BB + H) / IP
```

**Lower is better.**

| Range  | Read           |
| ------ | -------------- |
| `<1.00`| Elite          |
| `1.20` | All-Star       |
| `1.30` | Solid regular  |
| `1.40+`| Below average  |

### K/9 — Strikeouts per 9 innings

```
K/9 = 9 × K / IP
```

**Higher is better.**

| Range | Read           |
| ----- | -------------- |
| `11+` | Power pitcher  |
| `9.0` | Strong         |
| `7.0` | Average        |
| `5.0` | Contact pitcher|

### BB/9 — Walks per 9 innings

```
BB/9 = 9 × BB / IP
```

**Lower is better** (better control).

| Range  | Read              |
| ------ | ----------------- |
| `<2.0` | Elite control     |
| `2.5`  | Strong            |
| `3.5`  | Average           |
| `5.0+` | Wild              |

### HR/9 — Home runs per 9 innings

```
HR/9 = 9 × HR / IP
```

**Lower is better.**

| Range   | Read           |
| ------- | -------------- |
| `<0.8`  | Elite          |
| `1.0`   | Strong         |
| `1.2`   | Average        |
| `1.5+`  | Homer-prone    |

## Min PA / IP per season

The **Min PA / IP per season** knob in the sidebar drops per-season
rows from the curve fit when they fall below a minimum playing-time
threshold. The unit follows the **Position** toggle:

- **PA (plate appearances)** when *Position* is *Batter*.
- **IP (innings pitched)** when *Position* is *Pitcher*.

It exists because a 50-PA September call-up or a 20-IP injury year
carries almost no signal about a player's true ability. A weighted
quadratic fit will still treat such a row as a data point (lightly
weighted, but present), and very-low-weight seasons can drag the fit
when they're outliers. Setting a minimum drops those rows entirely.

### Common thresholds

| Value     | What it represents                                                            |
| --------- | ----------------------------------------------------------------------------- |
| `502 PA`  | The official batting-title qualification (3.1 PA × games scheduled).          |
| `162 IP`  | The official ERA-title qualification (1 IP × games scheduled).                |
| `300 PA` / `100 IP` | Typical "full-time regular" lower bound.                            |
| `100`     | The default; keeps most non-trivial seasons.                                  |
| `0`       | Disables the filter — every season counts toward the fit.                     |

For a player whose role changed substantially over time
(starter-turned-reliever, regular-turned-bench), tuning this knob up
to focus on their prime role often gives a cleaner curve. For a young
player with only a few full seasons, tune it down to include
near-rookie years.

## See also

- [Modeling approach](modeling.md) — how the quadratic fit uses these
  metrics as the response variable, and how weights are applied.
- [Methods](methods.md) — worked example using OPS for Mickey Mantle,
  with the centered-form interpretation.
