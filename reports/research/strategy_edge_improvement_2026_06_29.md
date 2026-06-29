# Strategy Edge Improvement - 2026-06-29

This report is research-only. It does not promote strategies, create orders,
modify official paper trading, or change live/runtime flags.

## Pair attribution

| Symbol | Net PnL EUR | Trades | PF | Winrate % | Positive share | Research action | Reasons |
|---|---:|---:|---:|---:|---:|---|---|
| BCHEUR | 30.1973 | 5 | 10.5783 | 60.0000 | 0.6795 | concentration_watch_research_only | positive_pnl_concentration |
| SOLEUR | 5.8778 | 5 | 2.4530 | 80.0000 | 0.1323 | keep_testing_research | positive_after_costs |
| LTCZEUR | 3.0951 | 1 | - | 100.0000 | 0.0696 | observe_more | sample_too_small |
| ADAEUR | 2.3752 | 2 | 1.9201 | 50.0000 | 0.0534 | observe_more | sample_too_small |
| XRPZEUR | 1.5788 | 2 | 1.7749 | 50.0000 | 0.0355 | observe_more | sample_too_small |
| DOTEUR | 1.3160 | 3 | 1.7512 | 66.6667 | 0.0296 | observe_more | sample_too_small |
| TRXEUR | 0.0000 | 0 | - | - | 0.0000 | observe_more | sample_too_small |
| BTCZEUR | 0.0000 | 0 | - | - | 0.0000 | observe_more | sample_too_small |
| AAVEEUR | -1.4445 | 10 | 0.9224 | 30.0000 | 0.0000 | cost_aware_review | mixed_or_cost_sensitive |
| LINKEUR | -1.9235 | 1 | 0.0000 | 0.0000 | 0.0000 | observe_more | sample_too_small |
| ETHZEUR | -2.1470 | 1 | 0.0000 | 0.0000 | 0.0000 | observe_more | sample_too_small |
| ATOMEUR | -2.2424 | 1 | 0.0000 | 0.0000 | 0.0000 | observe_more | sample_too_small |
| AVAXEUR | -12.2619 | 7 | 0.2488 | 14.2857 | 0.0000 | research_quarantine_candidate | material_negative_contribution, weak_pair_profit_factor |
| XLMZEUR | -17.2975 | 7 | 0.0172 | 14.2857 | 0.0000 | research_quarantine_candidate | material_negative_contribution, weak_pair_profit_factor |

## Leave-one-symbol-out

| Removed | Net without symbol | Delta | Interpretation |
|---|---:|---:|---|
| XLMZEUR | 24.4209 | 17.2975 | pair_damages_portfolio |
| AVAXEUR | 19.3853 | 12.2619 | pair_damages_portfolio |
| ATOMEUR | 9.3657 | 2.2424 | pair_damages_portfolio |
| ETHZEUR | 9.2703 | 2.1470 | pair_damages_portfolio |
| LINKEUR | 9.0468 | 1.9235 | pair_damages_portfolio |
| AAVEEUR | 8.5679 | 1.4445 | pair_damages_portfolio |
| TRXEUR | 7.1233 | 0.0000 | neutral_or_small_sample |
| BTCZEUR | 7.1233 | 0.0000 | neutral_or_small_sample |
| DOTEUR | 5.8074 | -1.3160 | depends_on_positive_pair |
| XRPZEUR | 5.5446 | -1.5788 | depends_on_positive_pair |
| ADAEUR | 4.7481 | -2.3752 | depends_on_positive_pair |
| LTCZEUR | 4.0282 | -3.0951 | depends_on_positive_pair |
| SOLEUR | 1.2456 | -5.8778 | depends_on_positive_pair |
| BCHEUR | -23.0740 | -30.1973 | depends_on_positive_pair |

## Trend Momentum redesign plan

- strong_multi_timeframe_trend: avoid weak single-timeframe momentum (no_capital)
- range_chop_avoidance: block momentum in sideways regimes (no_capital)
- minimum_volatility: require enough movement to cover costs (no_capital)
- volume_confirmation: avoid low-liquidity momentum signals (no_capital)
- momentum_persistence: require continuation across multiple bars (no_capital)
- spread_cost_floor: reject trades whose edge cannot exceed costs (no_capital)
- strict_cooldown: reduce clustered false signals (no_capital)

## Mean Reversion cost-aware review plan

- tp_above_round_trip_cost_plus_margin: avoid gross wins that become net flat
- spread_filter: only trade cheap symbols
- minimum_volatility: ensure mean reversion amplitude covers cost
- range_regime_only: avoid catching falling/strong trending assets
- strong_trend_block: block reversion against dominant trend
- exit_timing_review: reduce winners decaying back to cost
- portfolio_aware_walk_forward: validate net effect with capital constraints

## Candidate families

| Family | Status | Baseline | Notes |
|---|---|---|---|
| breakout_volatility | research_design_ready | high_conviction_current | use 1h/4h volatility expansion and cost-aware breakout confirmation |
| range_breakout | research_design_only | no_trade,buy_and_hold,random_signal_same_frequency,high_conviction_current | requires range identification before breakout validation |
| liquidity_sweep_fakeout | research_design_only | high_conviction_current | needs spread/depth snapshots; no order-book-dependent capital until coverage is long enough |
| volume_anomaly | research_design_only | high_conviction_current | needs reliable OHLCV volume and anti-overfit walk-forward |
| multi_timeframe_confirmation | already_represented_by_high_conviction | high_conviction_current | improve with pair/regime attribution instead of broad parameter tuning |
| volatility_expansion | already_represented_by_high_conviction | high_conviction_current | split attribution by family in future walk-forward reports |
| regime_switch_strategy | research_design_only | high_conviction_current | use existing regime/entropy tools as filters, not price prediction |

## Recommendations

- Keep High Conviction in active_research only; do not promote until trade count, folds and concentration improve.
- Run leave-one-symbol-out and research-only quarantine analysis before trusting any positive headline PnL.
- Keep Trend Momentum no_capital until redesigned filters lift stress PF above 1.10.
- Keep Mean Reversion no_capital until TP/cost and range-only filters prove net profitability after costs.
- Keep Relative Value no_go and Grid archived/no_go.
- Add family-level attribution to future High Conviction walk-forward outputs before adding new strategy families.
- Test research-only pair quarantine for: AVAXEUR, XLMZEUR

## Safety confirmation

- research_only: true
- orders_created: false
- official_paper_modified: false
- live_modified: false
- runtime_router_modified: false
- runtime_sizing_modified: false
- child_instance_created: false
- live_promotion_allowed: false
