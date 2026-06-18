# High Conviction Discovery - high_conviction_discovery_2026_06_18

## Summary

- Generated at: `2026-06-18T18:22:45.946409+00:00`
- Data paths: `1`
- Symbols: `ADAEUR, AVAXEUR, DOTEUR, LINKEUR, SOLEUR, TRXEUR, XRPZEUR`
- Timeframes: `15m, 1h, 5m`
- Cost profile: `research_stress`
- Round-trip cost estimate: `98.000 bps`
- Setups detected: `508`
- Conclusion: **no_profitable_high_conviction_candidate_yet**

This report generates swing/high-conviction candidates directly from OHLCV. It does not assume the existing grid signals are the available opportunity set.

## Setups By Family

| Family | Count |
| --- | ---: |
| breakout_1h_4h | 45 |
| major_support_mean_reversion | 35 |
| pullback_trend | 154 |
| trend_continuation | 268 |
| volatility_expansion | 6 |

## Setups By Symbol

| Symbol | Count |
| --- | ---: |
| ADAEUR | 72 |
| AVAXEUR | 28 |
| DOTEUR | 63 |
| LINKEUR | 106 |
| SOLEUR | 95 |
| TRXEUR | 53 |
| XRPZEUR | 91 |

## Expected Move Distribution

| Bucket | Count |
| --- | ---: |
| lt_200_bps | 0 |
| 200_499_bps | 268 |
| 500_999_bps | 221 |
| gte_1000_bps | 19 |

## Top Scenarios

| Scenario | Status | Trades | Net PnL EUR | PF | Winrate | Expectancy bps | Max DD bps | Avg MFE/MAE | Best | Worst |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| trend_invalidation__min1000bps__rr2__hold24h | research_only | 19 | -13.177 | 0.205 | 31.579 | -69.355 | 1390.396 | 4.902 | LINKEUR | AVAXEUR |
| trend_invalidation__min1000bps__rr2__hold72h | research_only | 19 | -13.177 | 0.205 | 31.579 | -69.355 | 1390.396 | 4.902 | LINKEUR | AVAXEUR |
| trend_invalidation__min1000bps__rr2__hold168h | research_only | 19 | -13.177 | 0.205 | 31.579 | -69.355 | 1390.396 | 4.902 | LINKEUR | AVAXEUR |
| trend_invalidation__min1000bps__rr3__hold24h | research_only | 19 | -13.177 | 0.205 | 31.579 | -69.355 | 1390.396 | 4.902 | LINKEUR | AVAXEUR |
| trend_invalidation__min1000bps__rr3__hold72h | research_only | 19 | -13.177 | 0.205 | 31.579 | -69.355 | 1390.396 | 4.902 | LINKEUR | AVAXEUR |
| trend_invalidation__min1000bps__rr3__hold168h | research_only | 19 | -13.177 | 0.205 | 31.579 | -69.355 | 1390.396 | 4.902 | LINKEUR | AVAXEUR |
| trend_invalidation__min1000bps__rr2__hold6h | research_only | 19 | -14.785 | 0.102 | 26.316 | -77.814 | 1478.457 | 4.274 | LINKEUR | AVAXEUR |
| trend_invalidation__min1000bps__rr3__hold6h | research_only | 19 | -14.785 | 0.102 | 26.316 | -77.814 | 1478.457 | 4.274 | LINKEUR | AVAXEUR |
| fixed_tp_sl__min1000bps__rr2__hold6h | research_only | 19 | -24.693 | 0.035 | 15.789 | -129.962 | 2469.269 | 2.008 | LINKEUR | AVAXEUR |
| trailing__min1000bps__rr2__hold6h | research_only | 19 | -24.693 | 0.035 | 15.789 | -129.962 | 2469.269 | 2.008 | LINKEUR | AVAXEUR |
| partial_runner__min1000bps__rr2__hold6h | research_only | 19 | -24.693 | 0.035 | 15.789 | -129.962 | 2469.269 | 2.008 | LINKEUR | AVAXEUR |
| fixed_tp_sl__min1000bps__rr3__hold6h | research_only | 19 | -24.693 | 0.035 | 15.789 | -129.962 | 2469.269 | 2.008 | LINKEUR | AVAXEUR |
| trailing__min1000bps__rr3__hold6h | research_only | 19 | -24.693 | 0.035 | 15.789 | -129.962 | 2469.269 | 2.008 | LINKEUR | AVAXEUR |
| partial_runner__min1000bps__rr3__hold6h | research_only | 19 | -24.693 | 0.035 | 15.789 | -129.962 | 2469.269 | 2.008 | LINKEUR | AVAXEUR |
| trailing__min1000bps__rr2__hold72h | research_only | 19 | -32.336 | 0.072 | 10.526 | -170.189 | 3233.585 | 1.496 | LINKEUR | AVAXEUR |
| trailing__min1000bps__rr2__hold168h | research_only | 19 | -32.336 | 0.072 | 10.526 | -170.189 | 3233.585 | 1.496 | LINKEUR | AVAXEUR |
| trailing__min1000bps__rr3__hold72h | research_only | 19 | -32.336 | 0.072 | 10.526 | -170.189 | 3233.585 | 1.496 | LINKEUR | AVAXEUR |
| trailing__min1000bps__rr3__hold168h | research_only | 19 | -32.336 | 0.072 | 10.526 | -170.189 | 3233.585 | 1.496 | LINKEUR | AVAXEUR |
| fixed_tp_sl__min1000bps__rr2__hold24h | research_only | 19 | -32.725 | 0.079 | 10.526 | -172.236 | 3272.483 | 1.496 | LINKEUR | AVAXEUR |
| trailing__min1000bps__rr2__hold24h | research_only | 19 | -32.725 | 0.079 | 10.526 | -172.236 | 3272.483 | 1.496 | LINKEUR | AVAXEUR |
| partial_runner__min1000bps__rr2__hold24h | research_only | 19 | -32.725 | 0.079 | 10.526 | -172.236 | 3272.483 | 1.496 | LINKEUR | AVAXEUR |
| fixed_tp_sl__min1000bps__rr3__hold24h | research_only | 19 | -32.725 | 0.079 | 10.526 | -172.236 | 3272.483 | 1.496 | LINKEUR | AVAXEUR |
| trailing__min1000bps__rr3__hold24h | research_only | 19 | -32.725 | 0.079 | 10.526 | -172.236 | 3272.483 | 1.496 | LINKEUR | AVAXEUR |
| partial_runner__min1000bps__rr3__hold24h | research_only | 19 | -32.725 | 0.079 | 10.526 | -172.236 | 3272.483 | 1.496 | LINKEUR | AVAXEUR |
| fixed_tp_sl__min1000bps__rr2__hold72h | research_only | 19 | -33.004 | 0.053 | 10.526 | -173.707 | 3300.426 | 1.496 | LINKEUR | AVAXEUR |

## Top Raw Setups

| Symbol | Family | Entry | Expected bps | Stop bps | RR est. | Trend 1h | Trend 4h | ATR 15m | ATR 1h | Reason |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| AVAXEUR | major_support_mean_reversion | 2026-06-05T20:25:00+00:00 | 2500.000 | 80.000 | 31.250 | -181.582 | -194.553 | 35.827 | 85.064 | support reversion with 15m dislocation |
| SOLEUR | major_support_mean_reversion | 2026-06-05T20:25:00+00:00 | 2500.000 | 80.000 | 31.250 | -218.464 | -220.121 | 38.895 | 71.253 | support reversion with 15m dislocation |
| ADAEUR | major_support_mean_reversion | 2026-06-05T20:25:00+00:00 | 2500.000 | 80.000 | 31.250 | -246.331 | -279.753 | 29.420 | 69.868 | support reversion with 15m dislocation |
| DOTEUR | major_support_mean_reversion | 2026-06-05T20:25:00+00:00 | 2399.585 | 80.000 | 29.995 | -218.499 | -307.271 | 41.226 | 100.338 | support reversion with 15m dislocation |
| DOTEUR | pullback_trend | 2026-06-05T20:25:00+00:00 | 2267.840 | 90.000 | 25.198 | 184.655 | 184.655 | 43.931 | 135.224 | trend pullback recovery |
| LINKEUR | major_support_mean_reversion | 2026-06-05T20:25:00+00:00 | 2140.925 | 80.000 | 26.762 | -277.871 | -236.571 | 36.785 | 76.059 | support reversion with 15m dislocation |
| XRPZEUR | major_support_mean_reversion | 2026-06-05T20:25:00+00:00 | 1815.645 | 80.000 | 22.696 | -268.341 | -271.940 | 35.537 | 65.101 | support reversion with 15m dislocation |
| AVAXEUR | trend_continuation | 2026-06-07T04:35:00+00:00 | 1126.547 | 110.000 | 10.241 | 744.254 | 189.036 | 43.258 | 131.327 | multi-timeframe trend continuation |
| AVAXEUR | breakout_1h_4h | 2026-06-07T08:35:00+00:00 | 1126.535 | 354.913 | 3.174 | 189.387 | 84.207 | 46.900 | 111.813 | 1h/4h trend breakout |
| AVAXEUR | breakout_1h_4h | 2026-06-07T08:50:00+00:00 | 1126.339 | 352.974 | 3.191 | 189.387 | 84.207 | 42.711 | 111.813 | 1h/4h trend breakout |
| AVAXEUR | trend_continuation | 2026-06-07T04:50:00+00:00 | 1107.809 | 110.000 | 10.071 | 744.254 | 189.036 | 43.059 | 131.327 | multi-timeframe trend continuation |
| AVAXEUR | trend_continuation | 2026-06-07T03:05:00+00:00 | 1090.187 | 110.000 | 9.911 | 400.989 | 400.989 | 44.760 | 149.131 | multi-timeframe trend continuation |
| AVAXEUR | trend_continuation | 2026-06-07T03:35:00+00:00 | 1088.329 | 110.000 | 9.894 | 400.989 | 400.989 | 44.352 | 149.131 | multi-timeframe trend continuation |
| AVAXEUR | trend_continuation | 2026-06-07T03:50:00+00:00 | 1088.329 | 110.000 | 9.894 | 400.989 | 400.989 | 42.390 | 149.131 | multi-timeframe trend continuation |
| AVAXEUR | trend_continuation | 2026-06-07T03:20:00+00:00 | 1079.047 | 110.000 | 9.810 | 400.989 | 400.989 | 44.303 | 149.131 | multi-timeframe trend continuation |
| ADAEUR | breakout_1h_4h | 2026-06-07T01:20:00+00:00 | 1071.949 | 301.708 | 3.553 | 144.524 | 409.833 | 61.018 | 189.206 | 1h/4h trend breakout |
| ADAEUR | breakout_1h_4h | 2026-06-07T01:05:00+00:00 | 1071.228 | 287.369 | 3.728 | 144.524 | 409.833 | 60.354 | 189.206 | 1h/4h trend breakout |
| DOTEUR | breakout_1h_4h | 2026-06-07T04:50:00+00:00 | 1052.420 | 297.011 | 3.543 | 751.059 | 263.222 | 36.613 | 119.518 | 1h/4h trend breakout |
| LINKEUR | breakout_1h_4h | 2026-06-07T22:05:00+00:00 | 1047.225 | 347.118 | 3.017 | 662.881 | 693.835 | 57.823 | 126.962 | 1h/4h trend breakout |
| AVAXEUR | pullback_trend | 2026-06-07T04:35:00+00:00 | 995.220 | 369.043 | 2.697 | 744.254 | 189.036 | 43.258 | 131.327 | trend pullback recovery |
| ADAEUR | breakout_1h_4h | 2026-06-07T22:05:00+00:00 | 982.006 | 293.479 | 3.346 | 543.024 | 492.952 | 70.985 | 154.221 | 1h/4h trend breakout |
| AVAXEUR | pullback_trend | 2026-06-07T04:50:00+00:00 | 976.483 | 377.355 | 2.588 | 744.254 | 189.036 | 43.059 | 131.327 | trend pullback recovery |
| ADAEUR | breakout_1h_4h | 2026-06-07T09:05:00+00:00 | 954.060 | 428.121 | 2.228 | 567.474 | 558.493 | 66.349 | 147.757 | 1h/4h trend breakout |
| SOLEUR | breakout_1h_4h | 2026-06-07T22:05:00+00:00 | 924.000 | 280.562 | 3.293 | 644.320 | 673.201 | 67.820 | 148.174 | 1h/4h trend breakout |
| DOTEUR | breakout_1h_4h | 2026-06-07T22:05:00+00:00 | 921.277 | 259.714 | 3.547 | 343.896 | 273.104 | 55.767 | 125.447 | 1h/4h trend breakout |

## Grid/Micro Comparison

- micro_report_path: `reports\research\high_conviction_swing_2026_06_18.json`
- micro_report_loaded: `True`
- discovery_best_net_pnl_eur: `-13.177494`
- discovery_best_profit_factor: `0.20500460974499213`
- micro_conclusion: `micro_trade_bias_detected_no_candidate_yet`
- micro_best_net_pnl_eur: `-257.562023`
- micro_best_profit_factor: `0.008584559978723753`
- micro_best_trade_count: `269`
- status: `discovery_compared_to_micro_report`
- net_pnl_delta_vs_micro_eur: `244.38452900000001`

## Recommendations

- Discovery ran on independent OHLCV setups; compare its net PnL and PF against the micro report before deciding.
- Keep discovery research-only; do not promote any setup to official paper without longer data and manual review.
- Use this report to decide which setup family deserves deeper OHLCV walk-forward, not to authorize live trading.
- Keep existing micro/grid trades learning-only unless they prove net profitability after runtime-comparable costs.
- Do not enable leverage or instance duplication before a setup passes profit factor, drawdown and sample-size gates.

## Safety

- Research-only OHLCV setup discovery.
- No decision_ledger signal is required for discovery.
- No official paper/live runtime component is modified or restarted.
- No Kraken order can be created by this command.
- No strategy registry mutation or promotion is performed.
- No instance duplication, leverage or live permission is enabled.
- live_promotion_allowed: `False`
