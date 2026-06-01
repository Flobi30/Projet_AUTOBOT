# VPS Trade Path Diagnostics Summary - 2026-06-01

Source: local read-only copy of `/opt/Projet_AUTOBOT/data/autobot_state.db`
from the VPS.

Dataset window: `2026-05-27T20:25:09Z` to `2026-06-01T11:55:57Z`.

Run id: `vps_2026_06_01_top14_trade_path`

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
| Average MFE | 34.073026 bps |
| Average MAE | -54.518933 bps |
| Average MFE/Cost ratio | 0.681461 |

Interpretation:

- Only `298 / 1,318` trades, about `22.6%`, moved far enough in the
  favorable direction to cover modeled costs.
- Average favorable excursion is smaller than modeled cost distance
  (`MFE/Cost = 0.681`), while average adverse excursion is larger than the
  favorable excursion (`MAE = -54.5 bps` vs `MFE = 34.1 bps`).
- This is stronger evidence that the current entries and exits are not merely
  being damaged by fees; most trades do not create enough favorable movement
  before adverse movement or exit.

## By Strategy Family

| Strategy | Trades | Gross PnL | Net PnL | Cost | Cost-Flipped | MFE>Cost | MFE>Cost Rate | Avg MFE | Avg MAE | Avg MFE/Cost |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| grid | 391 | -65.373353 | -190.493353 | 187.680000 | 78 | 130 | 33.25% | 42.722067 | -85.121411 | 0.854441 |
| trend | 221 | -45.083564 | -115.803564 | 106.080000 | 24 | 81 | 36.65% | 66.441342 | -46.511374 | 1.328827 |
| mean_reversion | 706 | -127.466757 | -353.386757 | 338.880000 | 199 | 87 | 12.32% | 19.150684 | -40.077151 | 0.383014 |

## Practical Reading

### Grid

Grid has moderate favorable movement but very large adverse movement:

- Average MFE: `42.72 bps`
- Average MAE: `-85.12 bps`
- MFE/Cost: `0.85`

This points to weak `grid_support_touch` entries and/or stop/recenter logic that
allows adverse movement to dominate. Grid is not just paying too much cost; it
is often wrong or too early around support.

### Trend

Trend is the most interesting diagnostic:

- Average MFE: `66.44 bps`
- Average MAE: `-46.51 bps`
- MFE/Cost: `1.33`

Trend frequently creates enough favorable movement to beat cost, but still ends
negative. That suggests the next research target should be exit quality:
trailing, take-profit capture, late exit, or giving back favorable movement.
Trend should not be promoted, but it deserves a deeper exit-specific audit
before being discarded.

### Mean Reversion

Mean reversion is the weakest family:

- Trades: `706`
- Net PnL: `-353.386757`
- MFE>Cost rate: `12.32%`
- Average MFE/Cost: `0.383`

This is mostly an entry-quality/regime problem. The z-score snapback entry is
not enough by itself. It is over-triggering in conditions where price does not
revert far enough before costs and adverse movement.

## Worst Cells

| Symbol | Strategy | Trades | Net PnL | Cost | MFE>Cost | Avg MFE | Avg MAE | Avg MFE/Cost | Worst Exit | Worst Entry |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| XLMZEUR | grid | 211 | -71.858183 | 101.280000 | 102 | 49.190072 | -75.997536 | 0.983801 | grid_stop_loss | grid_support_touch |
| XLMZEUR | trend | 121 | -60.325366 | 58.080000 | 52 | 92.912276 | -57.583786 | 1.858246 | trend_exit | trend_breakout |
| XLMZEUR | mean_reversion | 109 | -45.897837 | 52.320000 | 47 | 45.068933 | -66.727958 | 0.901379 | mean_reversion_stop | mean_reversion_zscore_entry |
| BCHEUR | mean_reversion | 53 | -36.972221 | 25.440000 | 5 | 18.129928 | -62.315215 | 0.362599 | mean_reversion_stop | mean_reversion_zscore_entry |
| SOLEUR | mean_reversion | 66 | -32.353881 | 31.680000 | 3 | 9.006098 | -25.677849 | 0.180122 | mean_reversion_exit | mean_reversion_zscore_entry |

## Diagnosis

The previous loss attribution showed that gross PnL was already negative before
costs. This trade-path diagnostic adds why:

1. Most trades do not travel far enough favorably to pay for realistic costs.
2. Adverse movement is usually larger than favorable movement.
3. Mean reversion is overactive and low quality.
4. Grid has a stop-loss/support-touch problem: adverse movement is too large
   after entry.
5. Trend has a different problem: it often gets enough favorable excursion, but
   exits still convert that into negative net PnL.

## Recommended Next Engineering Action

Do not lower thresholds and do not increase allocation.

Next work should split by strategy:

1. For trend, add exit-capture diagnostics:
   - MFE captured percentage;
   - giveback from MFE to exit;
   - exit lag in bars;
   - trailing stop versus fixed TP comparison.
2. For grid, audit support-touch entries:
   - entry distance to recent low;
   - whether stop is inside normal noise;
   - whether recenter logic triggers too late.
3. For mean reversion, tighten entry/regime requirements before any official
   paper promotion:
   - require stronger snapback confirmation;
   - avoid trending regimes;
   - require MFE/Cost evidence by symbol before enabling.
4. Rerun with baseline comparisons and walk-forward once exit-capture fields are
   added.

## Safety

This report is research-only. It does not authorize paper promotion or live
trading.
