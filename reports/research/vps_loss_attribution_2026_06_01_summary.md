# VPS Loss Attribution Summary - 2026-06-01

Source: local read-only copy of `/opt/Projet_AUTOBOT/data/autobot_state.db`
from the VPS.

Run id: `vps_2026_06_01_top14_loss_attribution`

Mode: `backtest`

Scope:

- 14 symbols.
- 3 strategy families: `grid`, `trend`, `mean_reversion`.
- 42 matrix cells.
- 42 analyzed trade journals.
- 0 missing journals.
- 1,318 closed research trades.

## Aggregate Result

| Metric | Value |
| --- | ---: |
| Gross PnL before research costs | -237.923673 |
| Net PnL after costs | -659.683673 |
| Total modeled cost | 632.640000 |
| Cost-flipped trades | 301 |

Interpretation:

- The problem is not only fees/spread/slippage.
- The gross PnL is already negative before costs.
- Costs then make the result much worse and flip 301 trades from gross-positive
  or flat into net-negative.
- This points to weak entry/exit quality plus targets that are too small
  relative to realistic costs.

## By Strategy Family

| Strategy | Trades | Gross PnL | Net PnL | Cost | Cost-Flipped Trades |
| --- | ---: | ---: | ---: | ---: | ---: |
| grid | 391 | -65.373353 | -190.493353 | 187.680000 | 78 |
| trend | 221 | -45.083564 | -115.803564 | 106.080000 | 24 |
| mean_reversion | 706 | -127.466757 | -353.386757 | 338.880000 | 199 |

Interpretation:

- `mean_reversion` is the biggest loss source by total PnL and trade count.
- `grid` loses less than mean reversion but is still negative before costs.
- `trend` trades less and loses less, but does not yet overcome cost drag.

## Worst Cells

| Symbol | Strategy | Trades | Gross PnL | Net PnL | Cost | Cost-Flipped | Worst Exit | Worst Entry |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| XLMZEUR | grid | 211 | -4.338183 | -71.858183 | 101.280000 | 26 | grid_stop_loss | grid_support_touch |
| XLMZEUR | trend | 121 | -21.605366 | -60.325366 | 58.080000 | 8 | trend_exit | trend_breakout |
| XLMZEUR | mean_reversion | 109 | -11.017837 | -45.897837 | 52.320000 | 15 | mean_reversion_stop | mean_reversion_zscore_entry |
| BCHEUR | mean_reversion | 53 | -20.012221 | -36.972221 | 25.440000 | 13 | mean_reversion_stop | mean_reversion_zscore_entry |
| SOLEUR | mean_reversion | 66 | -11.233881 | -32.353881 | 31.680000 | 20 | mean_reversion_exit | mean_reversion_zscore_entry |

## Practical Diagnosis

1. `XLMZEUR` dominates the worst results across all three strategy families in
   this captured sample. That does not mean the pair is always bad, but it does
   mean current logic does not adapt well to its observed behavior.
2. `grid` is mostly damaged by `grid_stop_loss` after `grid_support_touch`,
   suggesting the support-touch entry is too weak or stop/recenter logic is not
   aligned with the actual move.
3. `mean_reversion` repeatedly enters on `mean_reversion_zscore_entry` and exits
   through `mean_reversion_stop` or weak mean-reversion exits. The z-score signal
   is not enough by itself.
4. `trend` uses `trend_breakout` entries and mostly exits through `trend_exit`.
   It creates fewer trades, but breakout confirmation still appears too weak or
   too late after costs.
5. 301 trades are cost-flipped, so even when direction is not terrible, targets
   are often too close to the modeled transaction cost.

## Recommended Next Engineering Action

Do not lower global thresholds.

Do not promote any of these families.

Next work should add per-strategy quality diagnostics:

- entry edge at signal time versus final result;
- maximum favorable excursion and maximum adverse excursion after entry;
- TP distance versus cost distance;
- stop distance versus realized adverse move;
- hold duration by strategy;
- regime at entry;
- pair-level cooldown or stricter routing when one pair repeatedly dominates
  losses.

The most important immediate research question is:

> Are losing trades mostly bad direction, bad exit timing, or targets too small
> relative to costs?

This report proves that costs are a major drag, but also that raw gross edge is
negative. AUTOBOT needs better signal quality and better exit logic before more
aggressive allocation can be justified.

## Safety

This report is research-only. It does not authorize paper promotion or live
trading.
