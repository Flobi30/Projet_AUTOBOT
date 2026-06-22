# High Conviction Portfolio Replay - high_conviction_portfolio_2026_06_22

## Scope

- Initial capital: `500.0000 EUR`
- Setups scanned: `508`
- Scenario variants tested: `48` per cost profile and sizing policy
- Symbols: `ADAEUR, AVAXEUR, DOTEUR, LINKEUR, SOLEUR, TRXEUR, XRPZEUR`
- Mode: `research_only`, no runtime order or promotion.

## Legacy Independent Replay

| Cost Profile | Scenario | Trades | Net PnL EUR | PF | Winrate | Max DD % |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| paper_current_taker | trend_invalidation__min1000bps__rr2__hold24h | 19 | -12.4175 | 0.2266 | 31.5789 | 2.9391 |
| paper_current_taker | trend_invalidation__min1000bps__rr2__hold72h | 19 | -12.4175 | 0.2266 | 31.5789 | 2.9391 |
| paper_current_taker | trend_invalidation__min1000bps__rr3__hold24h | 19 | -12.4175 | 0.2266 | 31.5789 | 2.9391 |
| paper_current_taker | trend_invalidation__min1000bps__rr3__hold72h | 19 | -12.4175 | 0.2266 | 31.5789 | 2.9391 |
| research_stress | trend_invalidation__min1000bps__rr2__hold24h | 19 | -13.1775 | 0.2050 | 31.5789 | 3.0591 |
| research_stress | trend_invalidation__min1000bps__rr2__hold72h | 19 | -13.1775 | 0.2050 | 31.5789 | 3.0591 |
| research_stress | trend_invalidation__min1000bps__rr3__hold24h | 19 | -13.1775 | 0.2050 | 31.5789 | 3.0591 |
| research_stress | trend_invalidation__min1000bps__rr3__hold72h | 19 | -13.1775 | 0.2050 | 31.5789 | 3.0591 |
| paper_current_taker | trailing__min1000bps__rr2__hold72h | 19 | -31.5758 | 0.0765 | 15.7895 | 6.6958 |
| paper_current_taker | trailing__min1000bps__rr3__hold72h | 19 | -31.5758 | 0.0765 | 15.7895 | 6.6958 |
| paper_current_taker | fixed_tp_sl__min1000bps__rr2__hold24h | 19 | -31.9648 | 0.0826 | 10.5263 | 6.7008 |
| paper_current_taker | trailing__min1000bps__rr2__hold24h | 19 | -31.9648 | 0.0826 | 10.5263 | 6.7008 |

## Portfolio-Aware Replay

| Cost Profile | Policy | Scenario | Trades | Final Equity EUR | Net PnL EUR | PF | Winrate | Max DD % | Planned Exposure % | Marked Exposure % |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| paper_current_taker | dynamic_scaling | fixed_tp_sl__min500bps__rr2__hold72h | 9 | 518.1370 | 18.1370 | 4.4941 | 66.6667 | 2.6244 | 60.0000 | 61.2253 |
| paper_current_taker | dynamic_scaling | fixed_tp_sl__min500bps__rr3__hold72h | 9 | 518.1370 | 18.1370 | 4.4941 | 66.6667 | 2.6244 | 60.0000 | 61.2253 |
| paper_current_taker | conservative | fixed_tp_sl__min500bps__rr2__hold72h | 9 | 517.9824 | 17.9824 | 4.4643 | 66.6667 | 2.6028 | 60.0000 | 61.1654 |
| paper_current_taker | conservative | fixed_tp_sl__min500bps__rr3__hold72h | 9 | 517.9824 | 17.9824 | 4.4643 | 66.6667 | 2.6028 | 60.0000 | 61.1654 |
| research_stress | dynamic_scaling | fixed_tp_sl__min500bps__rr2__hold72h | 9 | 517.7677 | 17.7677 | 4.3468 | 66.6667 | 2.6242 | 60.0000 | 61.2254 |
| research_stress | dynamic_scaling | fixed_tp_sl__min500bps__rr3__hold72h | 9 | 517.7677 | 17.7677 | 4.3468 | 66.6667 | 2.6242 | 60.0000 | 61.2254 |
| research_stress | conservative | fixed_tp_sl__min500bps__rr2__hold72h | 9 | 517.6190 | 17.6190 | 4.3188 | 66.6667 | 2.6047 | 60.0000 | 61.1654 |
| research_stress | conservative | fixed_tp_sl__min500bps__rr3__hold72h | 9 | 517.6190 | 17.6190 | 4.3188 | 66.6667 | 2.6047 | 60.0000 | 61.1654 |
| paper_current_taker | dynamic_scaling | partial_runner__min500bps__rr2__hold24h | 10 | 517.2512 | 17.2512 | 3.1761 | 60.0000 | 2.6288 | 60.0000 | 61.6094 |
| paper_current_taker | dynamic_scaling | partial_runner__min500bps__rr3__hold24h | 10 | 517.2512 | 17.2512 | 3.1761 | 60.0000 | 2.6288 | 60.0000 | 61.6094 |
| paper_current_taker | conservative | partial_runner__min500bps__rr2__hold24h | 10 | 517.1905 | 17.1905 | 3.1976 | 60.0000 | 2.5983 | 60.0000 | 61.6094 |
| paper_current_taker | conservative | partial_runner__min500bps__rr3__hold24h | 10 | 517.1905 | 17.1905 | 3.1976 | 60.0000 | 2.5983 | 60.0000 | 61.6094 |
| paper_current_taker | dynamic_scaling | partial_runner__min500bps__rr2__hold72h | 9 | 516.8621 | 16.8621 | 4.2485 | 66.6667 | 2.6288 | 60.0000 | 61.6094 |
| paper_current_taker | dynamic_scaling | partial_runner__min500bps__rr3__hold72h | 9 | 516.8621 | 16.8621 | 4.2485 | 66.6667 | 2.6288 | 60.0000 | 61.6094 |
| research_stress | dynamic_scaling | partial_runner__min500bps__rr2__hold24h | 10 | 516.8404 | 16.8404 | 3.0829 | 60.0000 | 2.6287 | 60.0000 | 61.6094 |
| research_stress | dynamic_scaling | partial_runner__min500bps__rr3__hold24h | 10 | 516.8404 | 16.8404 | 3.0829 | 60.0000 | 2.6287 | 60.0000 | 61.6094 |
| research_stress | conservative | partial_runner__min500bps__rr2__hold24h | 10 | 516.7872 | 16.7872 | 3.1036 | 60.0000 | 2.6002 | 60.0000 | 61.6094 |
| research_stress | conservative | partial_runner__min500bps__rr3__hold24h | 10 | 516.7872 | 16.7872 | 3.1036 | 60.0000 | 2.6002 | 60.0000 | 61.6094 |
| paper_current_taker | conservative | partial_runner__min500bps__rr2__hold72h | 9 | 516.7392 | 16.7392 | 4.2248 | 66.6667 | 2.5983 | 60.0000 | 61.6094 |
| paper_current_taker | conservative | partial_runner__min500bps__rr3__hold72h | 9 | 516.7392 | 16.7392 | 4.2248 | 66.6667 | 2.5983 | 60.0000 | 61.6094 |
| research_stress | dynamic_scaling | partial_runner__min500bps__rr2__hold72h | 9 | 516.4932 | 16.4932 | 4.1068 | 66.6667 | 2.6287 | 60.0000 | 61.6094 |
| research_stress | dynamic_scaling | partial_runner__min500bps__rr3__hold72h | 9 | 516.4932 | 16.4932 | 4.1068 | 66.6667 | 2.6287 | 60.0000 | 61.6094 |
| research_stress | conservative | partial_runner__min500bps__rr2__hold72h | 9 | 516.3759 | 16.3759 | 4.0847 | 66.6667 | 2.6002 | 60.0000 | 61.6094 |
| research_stress | conservative | partial_runner__min500bps__rr3__hold72h | 9 | 516.3759 | 16.3759 | 4.0847 | 66.6667 | 2.6002 | 60.0000 | 61.6094 |

## Best Portfolio Result

- cost_profile: `paper_current_taker`
- policy: `dynamic_scaling`
- scenario: `{'label': 'fixed_tp_sl__min500bps__rr2__hold72h', 'min_expected_move_bps': 500.0, 'risk_reward_ratio': 2.0, 'max_hold_hours': 72.0, 'exit_mode': 'fixed_tp_sl'}`
- final_equity_eur: `518.136974`
- net_pnl_eur: `18.136974`
- profit_factor: `4.4941123610083515`
- winrate_pct: `66.66666666666666`
- max_drawdown_pct: `2.624387`
- average_exposure_pct: `40.202619`
- max_allocated_exposure_pct: `60.0`
- max_exposure_pct: `61.225301`
- critical_drawdown_stop: `False`
- blockers: `['research_only_no_auto_promotion', 'sample_size_below_candidate_minimum']`

### Pair Contributors

| Symbol | Trades | Net PnL EUR |
| --- | ---: | ---: |
| LINKEUR | 2 | 10.2491 |
| DOTEUR | 1 | 4.9290 |
| ADAEUR | 3 | 4.0407 |
| XRPZEUR | 1 | 2.3689 |
| SOLEUR | 1 | -1.7140 |
| AVAXEUR | 1 | -1.7367 |

### Losing Periods

- `2026-06-05`: `-5.1907 EUR`

## Comparison

- matching_scenario_label: `fixed_tp_sl__min500bps__rr2__hold72h`
- matching_legacy_non_portfolio_net_pnl_eur: `-275.924784`
- portfolio_net_pnl_eur: `18.136974`
- net_pnl_delta_eur: `294.061758`
- matching_legacy_max_drawdown_pct: `60.04789062211622`
- portfolio_max_drawdown_pct: `2.624387`
- legacy_is_not_capital_feasible: `True`
- portfolio_enforces_cash_exposure_cooldown_and_one_position_per_symbol: `True`

## Conclusion

`high_conviction_insufficient_sample_for_validation`

## Recommendations

- The portfolio replay is not evidence of viability yet: it has fewer than the configured closed-trade minimum.
- Treat every positive result as a research lead until longer OHLCV and walk-forward validation confirm it.

## Safety

- Research-only portfolio replay.
- No runtime paper/live component is modified by this command.
- No Kraken order can be created by this command.
- No strategy promotion, live permission, leverage or instance split is enabled.
- live_promotion_allowed: `False`
