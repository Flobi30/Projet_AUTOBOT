# Relative Value / Statistical Arbitrage Research - relative_value_2026_06_22

## Scope

- Venue: `Kraken Spot OHLCV research data`.
- Direction: `long_only`; only the target symbol is bought and sold.
- References: statistical only; no reference short or hedge order exists.
- Mode: `research_only`; no runtime, paper, live, or promotion mutation.
- Timeframe: `15m`.
- Signals found: `217`.
- statsmodels / Engle-Granger available: `False`.

## Relationships

| Target (BUY only) | Reference basket (not traded) |
| --- | --- |
| ADAEUR | XRPZEUR |
| LINKEUR | DOTEUR |
| AVAXEUR | SOLEUR |

## Portfolio Results

| Cost profile | Trades | Net PnL EUR | Final equity EUR | PF | Winrate % | Max DD % | Avg cost EUR | Status |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| paper_current_taker | 14 | -14.6967 | 485.3033 | 0.2835 | 35.7143 | 4.3304 | 0.7521 | research_only |
| research_stress | 14 | -15.1406 | 484.8594 | 0.2730 | 35.7143 | 4.4164 | 0.7838 | research_only |

## paper_current_taker Attribution

| Relationship | Trades | Net PnL EUR |
| --- | ---: | ---: |
| ADAEUR_vs_XRPZEUR | 6 | -9.7131 |
| AVAXEUR_vs_SOLEUR | 6 | 0.0087 |
| LINKEUR_vs_DOTEUR | 2 | -4.9924 |

| Symbol | Trades | Net PnL EUR |
| --- | ---: | ---: |
| ADAEUR | 6 | -9.7131 |
| AVAXEUR | 6 | 0.0087 |
| LINKEUR | 2 | -4.9924 |

- exit_reason_count: `{'fixed_stop_loss': 6, 'fixed_take_profit': 2, 'time_stop': 1, 'trailing_stop': 3, 'zscore_mean_reversion': 2}`
- rejected_entries: `{'cost_guard_expected_mfe_below_cost': 72, 'one_position_per_symbol': 54, 'symbol_cooldown': 77, 'two_leg_liquidity_size_reduced': 5}`
- blockers: `['research_only_no_auto_promotion', 'sample_size_below_first_observation_minimum', 'net_pnl_not_positive_after_costs', 'profit_factor_not_above_base_threshold']`

## research_stress Attribution

| Relationship | Trades | Net PnL EUR |
| --- | ---: | ---: |
| ADAEUR_vs_XRPZEUR | 6 | -9.9439 |
| AVAXEUR_vs_SOLEUR | 6 | -0.1253 |
| LINKEUR_vs_DOTEUR | 2 | -5.0713 |

| Symbol | Trades | Net PnL EUR |
| --- | ---: | ---: |
| ADAEUR | 6 | -9.9439 |
| AVAXEUR | 6 | -0.1253 |
| LINKEUR | 2 | -5.0713 |

- exit_reason_count: `{'fixed_stop_loss': 6, 'fixed_take_profit': 2, 'time_stop': 1, 'trailing_stop': 3, 'zscore_mean_reversion': 2}`
- rejected_entries: `{'cost_guard_expected_mfe_below_cost': 72, 'one_position_per_symbol': 54, 'symbol_cooldown': 77, 'two_leg_liquidity_size_reduced': 5}`
- blockers: `['research_only_no_auto_promotion', 'sample_size_below_first_observation_minimum', 'net_pnl_not_positive_after_costs', 'profit_factor_not_above_base_threshold']`

## High Conviction Comparison

- high_conviction_report_path: `reports\research\high_conviction_portfolio_2026_06_22\high_conviction_portfolio_2026_06_22.json`
- high_conviction_report_loaded: `True`
- relative_value_best_net_pnl_eur: `-14.696746`
- relative_value_best_profit_factor: `0.2835068849032677`
- high_conviction_net_pnl_eur: `18.136974`
- high_conviction_profit_factor: `4.4941123610083515`
- high_conviction_trade_count: `9`
- status: `compared_to_high_conviction_portfolio`
- net_pnl_delta_vs_high_conviction_eur: `-32.83372`

## Validation

- first_observation_min_trades: `30`
- base_profile: `paper_current_taker`
- base_pf_threshold_strictly_greater_than: `1.2`
- stress_profile: `research_stress`
- stress_pf_threshold_strictly_greater_than: `1.1`
- max_drawdown_pct_strictly_below: `10.0`
- base_pass: `False`
- stress_pass: `False`
- overall_preliminary_pass: `False`
- live_promotion_allowed: `False`

## Signal Rejections


## Conclusion

`NO_GO_relative_value_validation_failed`

## Recommendations

- NO GO: the frozen long-only Relative Value model did not meet every base and stress validation gate.
- Engle-Granger was unavailable; install statsmodels only for a later validation pass, not to change the signal threshold.
- Keep Relative Value isolated in research-only replay; do not connect it to the router or official paper execution.
- Use the same frozen relationships and thresholds on longer Kraken OHLCV before considering any controlled shadow experiment.
- Do not add a reference short, leverage, margin, or pair scaling to compensate for a failed long-only result.
- Collect bid/ask and depth before treating fixed spread assumptions as sufficient for an intraday paper-candidate review.

## Safety

- Research-only; no runtime router or paper/live executor is imported.
- Kraken Spot long-only proxy: BUY/SELL target symbol only; references are never traded.
- No leverage, margin, auto-promotion, instance split, or Kraken order is possible.
- live_promotion_allowed: `False`
