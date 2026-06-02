# VPS Strategy Regime Comparison - 2026-06-02

## Objective

Compare AUTOBOT's current research strategy families by market regime, using the same conservative replay/cost framework.

This is a research-only diagnostic. It does not authorize official paper execution, live trading, strategy promotion, or increased sizing.

## Dataset

- Source: `data/vps_autobot_state_2026-06-01.db`
- Table: `market_price_samples`
- Period: `2026-05-27T20:25:09Z` to `2026-06-01T11:55:57Z`
- Symbols: `BTCZEUR`, `ETHZEUR`, `SOLEUR`, `LTCZEUR`, `XLMZEUR`, `XRPZEUR`, `TRXEUR`, `ADAEUR`, `LINKEUR`, `DOTEUR`, `BCHEUR`, `ATOMEUR`, `AVAXEUR`, `AAVEEUR`
- Costs: research cost model including taker fees, fallback spread, slippage, and latency buffer.
- Regime source: research Markov/entropy regime context, attached without future-bar look-ahead.

## Strategy Configurations

| Strategy | Configuration | Notes |
| --- | --- | --- |
| `dynamic_grid` | current research default | Used to test whether grid is actually profitable by regime. |
| `mean_reversion` | current research default | Used to test whether the current snapback logic has net edge. |
| `trend_momentum` | `confirm_bps=40`, `min_momentum_bps=100`, `min_atr_bps=15`, `min_signal_net_edge_bps=120` | Best recent trend candidate, still research-only. |

## Overall Result

| Strategy | Trades | Gross PnL EUR | Net PnL EUR | Verdict |
| --- | ---: | ---: | ---: | --- |
| `dynamic_grid` | 391 | -65.373353 | -190.493353 | FAIL |
| `mean_reversion` | 706 | -127.466757 | -353.386757 | FAIL |
| `trend_momentum` edge120 | 30 | 3.227229 | -6.372771 | FAIL_WITH_SIGNAL |

The full combined report is available at:

- `reports/research/vps_2026_06_02_strategy_regime_comparison/vps_2026_06_02_strategy_regime_comparison.md`
- `reports/research/vps_2026_06_02_strategy_regime_comparison/vps_2026_06_02_strategy_regime_comparison.json`

## Key Buckets

| Strategy | Regime | Trades | Win Rate | Net PnL EUR | Diagnostic |
| --- | --- | ---: | ---: | ---: | --- |
| `dynamic_grid` | `chaos` | 312 | 58.65% | -130.593793 | High win rate but cost and exit capture destroy the edge. |
| `dynamic_grid` | `range` | 37 | 37.84% | -20.529342 | Grid is not yet proving its expected range advantage. |
| `dynamic_grid` | `high_vol` | 27 | 74.07% | -9.546466 | Good-looking win rate, still negative after costs. |
| `mean_reversion` | `chaos` | 496 | 19.96% | -242.470512 | Strong evidence that the current default is not suited here. |
| `mean_reversion` | `range` | 200 | 0.50% | -106.172022 | Current default fails even where mean reversion should be plausible. |
| `mean_reversion` | `high_vol` | 4 | 100.00% | 0.714304 | Positive but too small to use. |
| `trend_momentum` edge120 | `high_vol` | 6 | 0.00% | -7.609117 | Harmful in this replay; likely needs blocking or heavy penalty. |
| `trend_momentum` edge120 | `chaos` | 24 | 41.67% | 1.236346 | Slight positive signal, but sample too small and baselines missing. |

## Interpretation

AUTOBOT is not merely failing because a few pairs are bad. The current tested strategy defaults are not reliably extracting net edge from the available market movement.

Main findings:

1. `dynamic_grid` remains the most runtime-relevant strategy family, but current research replay is strongly negative after costs.
2. `mean_reversion` current default is not ready; it is both high-turnover and poor-quality in the tested data.
3. `trend_momentum` with edge gating is the least bad candidate, but still negative overall.
4. Regime labels are valuable because they reveal hidden behavior, but they are not enough by themselves to authorize trades.
5. Positive pockets exist only in tiny or weak samples and should be treated as hypotheses, not proof.

## Decision

Do not promote any tested configuration.

Do not increase capital allocation.

Do not lower thresholds to create more trades.

Keep all changes research-only until the next validation layer proves:

- positive net PnL after costs;
- adequate closed-trade count;
- baseline outperformance;
- walk-forward stability;
- robust performance by regime;
- official paper/research ledger reconciliation.

## Recommended Next Work

1. Add mandatory baselines for every strategy x regime bucket:
   - no-trade;
   - buy-and-hold when applicable;
   - random-entry same-frequency.
2. Add walk-forward splits on the same 14 symbols.
3. Test strategy-specific regime blockers in research only:
   - block or penalize `trend_momentum` edge120 in `high_vol`;
   - keep testing `trend_momentum` in `chaos` only with baselines;
   - reject or heavily constrain current `mean_reversion` defaults;
   - retest `dynamic_grid` only with stricter cost/MFE conditions.
4. Reconcile official paper ledger vs research replay so the same decision can be traced from signal to PnL.

## Safety

- Live trading remains disabled and untouched.
- Official paper execution is unchanged.
- The dashboard and runtime router are unchanged.
- No registry promotion was performed.
- This report is research-only.
