# AUTOBOT Strategy Regime Walk-Forward Summary - 2026-06-02

## Verdict

PASS_WITH_WARNINGS for the diagnostic tool.

FAIL for strategy promotion.

The strategy/regime walk-forward diagnostic ran on the VPS AUTOBOT state database and found no strategy/regime bucket that is robust enough to promote. The only positive bucket, `mean_reversion / high_vol`, passed fold baseline checks but contains only 4 trades. It is therefore classified as `keep_testing`, not as validated.

## Run Context

| Field | Value |
| --- | --- |
| Base commit before this change | `3aa6281` |
| Run id | `vps_2026_06_02_strategy_regime_wf_defaults` |
| Data source | `data/vps_autobot_state_2026-06-01.db` |
| Symbols | `BTCZEUR`, `ETHZEUR`, `SOLEUR`, `LTCZEUR`, `XLMZEUR`, `XRPZEUR`, `TRXEUR`, `ADAEUR`, `LINKEUR`, `DOTEUR`, `BCHEUR`, `ATOMEUR`, `AVAXEUR`, `AAVEEUR` |
| Strategies | `grid`, `trend`, `mean_reversion` |
| Regime context | Enabled |
| Train window | 600 bars |
| Test window | 30 bars |
| Step window | 30 bars |
| Min folds | 2 |
| Min passing folds | 2 |
| Min total trades | 30 |
| Costs | 16 bps fee, 8 bps spread, 4 bps slippage |
| Folds evaluated | 1696 |
| Buckets evaluated | 1057 |

## Strategy x Regime Result

| Strategy | Regime | Folds | Passing | Positive | Trades | Net PnL EUR | Delta vs Best Baseline EUR | Worst Delta EUR | Status | Reason |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| dynamic_grid | chaos | 280 | 107 | 164 | 308 | -125.063335 | -353.924994 | -12.167974 | modify | non_positive_aggregate_net_pnl |
| mean_reversion | chaos | 366 | 58 | 72 | 494 | -240.891029 | -347.327016 | -12.597238 | modify | non_positive_aggregate_net_pnl |
| trend_momentum | chaos | 174 | 28 | 30 | 203 | -101.778844 | -125.826026 | -6.756468 | modify | non_positive_aggregate_net_pnl |
| mean_reversion | range | 145 | 0 | 0 | 196 | -102.875530 | -102.875530 | -3.467052 | modify | insufficient_baseline_passing_folds |
| dynamic_grid | high_vol | 26 | 9 | 19 | 27 | -9.546466 | -55.571562 | -9.935247 | keep_testing | insufficient_total_trades |
| dynamic_grid | unknown | 8 | 0 | 0 | 11 | -27.473578 | -27.473578 | -8.275667 | keep_testing | insufficient_total_trades |
| dynamic_grid | range | 30 | 13 | 13 | 35 | -18.333109 | -18.333109 | -4.833231 | modify | non_positive_aggregate_net_pnl |
| trend_momentum | high_vol | 14 | 2 | 2 | 14 | -12.143286 | -12.143286 | -1.887624 | keep_testing | insufficient_total_trades |
| mean_reversion | unknown | 5 | 1 | 1 | 5 | -4.579935 | -4.579935 | -1.579426 | keep_testing | insufficient_total_trades |
| dynamic_grid | low_activity | 2 | 0 | 0 | 2 | -2.408606 | -2.408606 | -2.364529 | keep_testing | insufficient_total_trades |
| trend_momentum | range | 3 | 0 | 0 | 3 | -1.499101 | -1.499101 | -0.796106 | keep_testing | insufficient_total_trades |
| mean_reversion | high_vol | 4 | 4 | 4 | 4 | 0.714304 | 0.714304 | 0.085819 | keep_testing | insufficient_total_trades |

## Interpretation

The defaults are not ready for promotion. `dynamic_grid / chaos`, `mean_reversion / chaos`, and `trend_momentum / chaos` have enough samples to be meaningful, and all three lose money net of costs and lose versus the best simple baseline in aggregate.

The apparent positive pocket, `mean_reversion / high_vol`, is too small to trust. Four trades can be luck, regime timing, or dataset coincidence. It should be monitored and replayed on more data, not promoted to official paper or live.

The result supports the current research direction: AUTOBOT needs stricter setup selection, better strategy gating, and more realistic validation before any runtime trading changes. Adding more trades or lowering thresholds would be the wrong next move unless a validated setup proves positive expectancy after costs.

## Artifacts

| Artifact | Path |
| --- | --- |
| Full markdown report | `reports/research/vps_2026_06_02_strategy_regime_walk_forward_defaults/vps_2026_06_02_strategy_regime_wf_defaults_strategy_regime_walk_forward.md` |
| Full JSON report | `reports/research/vps_2026_06_02_strategy_regime_walk_forward_defaults/vps_2026_06_02_strategy_regime_wf_defaults_strategy_regime_walk_forward.json` |

## Safety

This diagnostic is research-only. It does not change paper execution, strategy routing, capital allocation, risk management, Kraken integration, or live trading. It does not authorize any strategy promotion.
