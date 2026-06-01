# VPS Exit Capture Diagnostics Summary - 2026-06-01

Source: local read-only copy of `/opt/Projet_AUTOBOT/data/autobot_state.db`
from the VPS.

Dataset window: `2026-05-27T20:25:09Z` to `2026-06-01T11:55:57Z`.

Run id: `vps_2026_06_01_top14_exit_capture`

Mode: `backtest`

Scope:

- 14 symbols: `TRXEUR`, `SOLEUR`, `ETHZEUR`, `BTCZEUR`, `LTCZEUR`,
  `XLMZEUR`, `XRPZEUR`, `ADAEUR`, `LINKEUR`, `DOTEUR`, `BCHEUR`,
  `ATOMEUR`, `AVAXEUR`, `AAVEEUR`.
- 3 strategy families: `grid`, `trend`, `mean_reversion`.
- 42 matrix cells.
- 42 successful cells.
- 0 runtime errors.
- 1,318 closed research trades.
- Costs included through the configured research cost model.

## Aggregate Result

| Metric | Value |
| --- | ---: |
| Gross PnL before modeled costs | -237.923673 |
| Net PnL after costs | -659.683673 |
| Total modeled cost | 632.640000 |
| Cost-flipped trades | 301 |
| Trades with MFE above cost | 298 |
| Trades with MFE above cost but net loss | 49 |
| Average MFE | 34.073026 bps |
| Average MAE | -54.518933 bps |
| Average exit capture | -18.035640 bps |
| Average MFE giveback | 52.108666 bps |
| Average positive MFE capture ratio | 0.452270 |
| Average MFE/Cost ratio | 0.681461 |

Interpretation:

- Average trade path reaches `+34.1 bps` favorable movement but exits around
  `-18.0 bps` from entry after execution pricing.
- Average giveback is `52.1 bps`, meaning the system often gives back more than
  the favorable movement it first saw.
- Positive MFE capture is about `45.2%` on average. That is not enough when the
  average MFE is already below cost distance.
- `49` trades had enough favorable excursion to cover cost but still closed as
  net losses. These are the clearest candidates for exit-quality investigation.

## By Strategy Family

| Strategy | Trades | Net PnL | Cost | MFE>Cost | MFE>Cost Lost | Avg MFE | Avg MAE | Avg Exit | Avg Giveback | Positive Capture | MFE/Cost |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| grid | 391 | -190.493353 | 187.680000 | 130 | 0 | 42.722067 | -85.121411 | -16.704494 | 59.426561 | 0.706047 | 0.854441 |
| trend | 221 | -115.803564 | 106.080000 | 81 | 43 | 66.441342 | -46.511374 | -20.381459 | 86.822801 | 0.175703 | 1.328827 |
| mean_reversion | 706 | -353.386757 | 338.880000 | 87 | 6 | 19.150684 | -40.077151 | -18.038547 | 37.189231 | 0.398297 | 0.383014 |

## Practical Diagnosis

### Trend

Trend is the clearest exit-capture problem:

- Average MFE: `66.44 bps`
- Average MFE/Cost: `1.33`
- Average exit capture: `-20.38 bps`
- Average giveback: `86.82 bps`
- Positive capture ratio: `17.57%`
- MFE-above-cost lost trades: `43 / 81`

This means trend often sees enough favorable movement to pay the modeled cost,
but the exit converts much of that opportunity into a loss. The next trend work
should focus on exit mechanics, not entry expansion:

- trailing stop responsiveness;
- take-profit capture;
- partial profit-taking simulation;
- timeout/exit lag;
- avoiding full giveback after breakout.

### Grid

Grid remains mostly an entry/adverse-excursion problem:

- Average MFE: `42.72 bps`
- Average MAE: `-85.12 bps`
- Average exit: `-16.70 bps`
- Average giveback: `59.43 bps`
- MFE-above-cost lost trades: `0`

Grid does have some favorable movement, but adverse movement is much larger.
The issue is less "it had profit and failed to take it" and more "support-touch
entries are too early or the stop/recenter behavior is not aligned with noise."

### Mean Reversion

Mean reversion remains the weakest entry-quality family:

- Trades: `706`
- Average MFE: `19.15 bps`
- Average MFE/Cost: `0.38`
- MFE-above-cost rate: `87 / 706`, about `12.3%`
- Positive capture ratio: `39.83%`

The main issue is that most mean-reversion trades never create enough favorable
movement to justify execution. Tightening exits will not fix this unless entry
and regime gating are improved first.

## Worst Cells With Exit-Capture Signal

| Symbol | Strategy | Trades | Net PnL | MFE>Cost | MFE>Cost Lost | Avg MFE | Avg Exit | Avg Giveback | Positive Capture | Worst Exit |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| XLMZEUR | grid | 211 | -71.858183 | 102 | 0 | 49.190072 | -2.054162 | 51.244234 | 0.752836 | grid_stop_loss |
| XLMZEUR | trend | 121 | -60.325366 | 52 | 25 | 92.912276 | -17.839619 | 110.751895 | 0.177814 | trend_exit |
| XLMZEUR | mean_reversion | 109 | -45.897837 | 47 | 1 | 45.068933 | -10.099019 | 55.167951 | 0.659514 | mean_reversion_stop |
| BCHEUR | mean_reversion | 53 | -36.972221 | 5 | 0 | 18.129928 | -37.724955 | 55.854883 | 0.525307 | mean_reversion_stop |
| SOLEUR | mean_reversion | 66 | -32.353881 | 3 | 1 | 9.006098 | -17.005726 | 26.011824 | 0.301382 | mean_reversion_exit |

## Important Caveat

`average_mfe_capture_ratio` is intentionally available in JSON but can become
noisy when MFE is extremely small. For human reading, prefer:

- `average_positive_mfe_capture_ratio`
- `average_mfe_giveback_bps`
- `mfe_above_cost_lost_trade_count`

These are more stable and more actionable.

## Recommended Next Engineering Action

Do not lower thresholds, do not increase allocation, and do not promote any
strategy.

Next work should implement a small research-only exit experiment for `trend`:

1. Compare current `trend_exit` with:
   - fixed take-profit after cost buffer;
   - ATR trailing stop;
   - MFE-protecting trailing stop;
   - time stop after breakout failure.
2. Reuse the same replay data and cost model.
3. Require baseline comparisons and no live/paper promotion.
4. Judge only by net PnL, MFE capture, drawdown and trade count.

The highest-probability improvement path is not "more trades"; it is better
profit capture on the subset of trades that already shows sufficient favorable
excursion.

## Safety

This report is research-only. It does not authorize paper promotion or live
trading.
