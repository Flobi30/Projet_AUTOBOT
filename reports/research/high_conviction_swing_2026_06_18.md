# High Conviction Swing Research - high_conviction_swing_2026_06_18

## Summary

- Generated at: `2026-06-18T16:56:59.285748+00:00`
- State DB: `/app/data/autobot_state.db`
- Window: `2026-06-15T16:55:00.588764+00:00` -> `2026-06-18T16:55:00.588764+00:00`
- Decision rows scanned: `2278`
- Signal candidates: `1112`
- Usable for replay: `891`
- Cost profile: `research_stress`
- Round-trip cost estimate: `98.000 bps`
- Conclusion: **micro_trade_bias_detected_no_candidate_yet**

## Expected Move Distribution

| Bucket | Count | Net-positive | Meets min edge | Avg gross bps | Avg net bps |
| --- | ---: | ---: | ---: | ---: | ---: |
| unknown | 221 | 0 | 0 | n/a | n/a |
| lt_50_bps | 0 | 0 | 0 | n/a | n/a |
| 50_99_bps | 0 | 0 | 0 | n/a | n/a |
| 100_149_bps | 891 | 335 | 111 | 138.778 | 45.063 |
| 150_249_bps | 0 | 0 | 0 | n/a | n/a |
| 250_399_bps | 0 | 0 | 0 | n/a | n/a |
| 400_999_bps | 0 | 0 | 0 | n/a | n/a |
| gte_1000_bps | 0 | 0 | 0 | n/a | n/a |

## Micro-Trade Assessment

- known_expected_move_signals: `891`
- signals_under_50_bps: `0`
- signals_under_100_bps: `0`
- signals_under_150_bps: `891`
- signals_under_300_bps: `891`
- signals_with_net_edge_above_required_minimum: `111`
- orientation: `micro_oriented`

## Best Scenarios

| Scenario | Status | Trades | Net PnL EUR | PF | Winrate | Expectancy bps | Max DD bps |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| fixed_tp_sl__min200bps__rr1.5__hold6h__mtf | research_only | 0 | 0.000 | n/a | n/a | n/a | 0.000 |
| trailing__min200bps__rr1.5__hold6h__mtf | research_only | 0 | 0.000 | n/a | n/a | n/a | 0.000 |
| partial_runner__min200bps__rr1.5__hold6h__mtf | research_only | 0 | 0.000 | n/a | n/a | n/a | 0.000 |
| fixed_tp_sl__min200bps__rr1.5__hold24h__mtf | research_only | 0 | 0.000 | n/a | n/a | n/a | 0.000 |
| trailing__min200bps__rr1.5__hold24h__mtf | research_only | 0 | 0.000 | n/a | n/a | n/a | 0.000 |
| partial_runner__min200bps__rr1.5__hold24h__mtf | research_only | 0 | 0.000 | n/a | n/a | n/a | 0.000 |
| fixed_tp_sl__min200bps__rr1.5__hold72h__mtf | research_only | 0 | 0.000 | n/a | n/a | n/a | 0.000 |
| trailing__min200bps__rr1.5__hold72h__mtf | research_only | 0 | 0.000 | n/a | n/a | n/a | 0.000 |
| partial_runner__min200bps__rr1.5__hold72h__mtf | research_only | 0 | 0.000 | n/a | n/a | n/a | 0.000 |
| fixed_tp_sl__min200bps__rr1.5__hold168h__mtf | research_only | 0 | 0.000 | n/a | n/a | n/a | 0.000 |
| trailing__min200bps__rr1.5__hold168h__mtf | research_only | 0 | 0.000 | n/a | n/a | n/a | 0.000 |
| partial_runner__min200bps__rr1.5__hold168h__mtf | research_only | 0 | 0.000 | n/a | n/a | n/a | 0.000 |
| fixed_tp_sl__min200bps__rr2__hold6h__mtf | research_only | 0 | 0.000 | n/a | n/a | n/a | 0.000 |
| trailing__min200bps__rr2__hold6h__mtf | research_only | 0 | 0.000 | n/a | n/a | n/a | 0.000 |
| partial_runner__min200bps__rr2__hold6h__mtf | research_only | 0 | 0.000 | n/a | n/a | n/a | 0.000 |
| fixed_tp_sl__min200bps__rr2__hold24h__mtf | research_only | 0 | 0.000 | n/a | n/a | n/a | 0.000 |
| trailing__min200bps__rr2__hold24h__mtf | research_only | 0 | 0.000 | n/a | n/a | n/a | 0.000 |
| partial_runner__min200bps__rr2__hold24h__mtf | research_only | 0 | 0.000 | n/a | n/a | n/a | 0.000 |
| fixed_tp_sl__min200bps__rr2__hold72h__mtf | research_only | 0 | 0.000 | n/a | n/a | n/a | 0.000 |
| trailing__min200bps__rr2__hold72h__mtf | research_only | 0 | 0.000 | n/a | n/a | n/a | 0.000 |

## Top Asymmetric Candidates

| Symbol | Strategy | Expected bps | Cost bps | MFE bps | MAE bps | MTF score | Asym score | Reason |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| XRPZEUR | grid | 134.862 | 93.461 | 232.842 | -438.661 | 1.000 | 28.078 | cost_guard |
| XRPZEUR | grid | 134.862 | 98.000 | 232.842 | -438.661 | 1.000 | 27.170 | Grid buy level 3 @ 1 |
| BCHEUR | grid | 141.792 | 92.909 | 200.298 | -1021.145 | 1.000 | 25.627 | opportunity_selection |
| XRPZEUR | grid | 137.144 | 88.123 | 194.531 | -474.458 | 1.000 | 25.543 | opportunity_selection |
| BCHEUR | grid | 142.921 | 86.533 | 233.463 | -991.951 | 0.750 | 25.332 | opportunity_selection |
| XRPZEUR | grid | 136.851 | 89.185 | 194.236 | -474.734 | 1.000 | 25.272 | cost_guard |
| XRPZEUR | grid | 135.064 | 88.915 | 262.762 | -410.705 | 0.750 | 24.615 | cost_guard |
| BCHEUR | grid | 141.792 | 98.000 | 200.298 | -1021.145 | 1.000 | 24.609 | Grid buy level 18 @ 188 |
| BCHEUR | grid | 142.431 | 96.687 | 265.198 | -964.016 | 0.750 | 24.574 | cost_guard |
| DOTEUR | grid | 135.664 | 90.576 | 253.917 | -600.480 | 0.750 | 24.509 | cost_guard |
| BCHEUR | grid | 142.431 | 98.000 | 265.198 | -964.016 | 0.750 | 24.443 | Grid buy level 12 @ 187 |
| BCHEUR | grid | 142.724 | 87.065 | 222.565 | -1001.544 | 0.750 | 24.116 | opportunity_selection |
| BCHEUR | grid | 138.094 | 98.000 | 260.809 | -967.880 | 0.750 | 24.009 | Grid buy level 12 @ 187 |
| BCHEUR | grid | 138.560 | 98.000 | 197.047 | -1024.007 | 1.000 | 23.961 | Grid buy level 18 @ 188 |
| BCHEUR | grid | 136.469 | 98.000 | 259.164 | -969.328 | 0.750 | 23.847 | Grid buy level 12 @ 187 |
| DOTEUR | grid | 135.664 | 98.000 | 253.917 | -600.480 | 0.750 | 23.766 | Grid buy level 11 @ 1 |
| XRPZEUR | grid | 135.064 | 98.000 | 262.762 | -410.705 | 0.750 | 23.706 | Grid buy level 2 @ 1 |
| DOTEUR | grid | 134.853 | 98.000 | 282.142 | -574.607 | 0.750 | 23.685 | Grid buy level 10 @ 1 |
| XRPZEUR | grid | 137.144 | 98.000 | 194.531 | -474.458 | 1.000 | 23.567 | Grid buy level 4 @ 1 |
| XRPZEUR | grid | 136.851 | 98.000 | 194.236 | -474.734 | 1.000 | 23.509 | Grid buy level 4 @ 1 |

## Recommendations

- Recent signals are too micro-oriented; larger potential filters should be researched before paper execution.
- Keep this high-conviction logic in research/paper-only until a larger sample proves net edge after costs.
- Do not promote any swing variant automatically; require official paper validation and human review.
- Keep micro-trades learning-only unless they beat the same cost profile with enough closed trades.
- Use multi-timeframe alignment and mandatory stop-loss/trailing rules for any future controlled paper test.
- Do not enable leverage or instance duplication before a strategy/pair passes PF, drawdown and sample-size gates.

## Safety

- Research-only replay from decision_ledger and market_price_samples.
- No official paper/live runtime component is modified or restarted.
- No Kraken order can be created by this command.
- No strategy registry mutation or promotion is performed.
- No instance duplication or live permission is enabled.
- live_promotion_allowed: `False`
