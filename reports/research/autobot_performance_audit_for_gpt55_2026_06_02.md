# AUTOBOT Performance Audit For GPT-5.5 - 2026-06-02

## Purpose

This report is designed to be copied into another advanced reasoning session for a second opinion on AUTOBOT performance and next technical priorities.

The goal is not to add another attractive trading module. The goal is to understand why AUTOBOT is still not net-profitable in validated paper/replay evidence, and to identify the smallest high-quality changes that could improve expected value without weakening live safety.

## Current Verdict

AUTOBOT is operational as a paper-first research/trading system, but the current validated performance evidence is not good enough for live trading.

The best recent research changes reduce losses materially, but none of the tested strategy configurations has produced robust positive net PnL after modeled fees, spread, slippage, and latency buffer.

No strategy should be promoted to live. Live trading must remain disabled until paper and replay evidence passes objective gates.

## Known Runtime Snapshot

Source: `docs/research/strategy_hypotheses.json`, registry snapshot dated 2026-05-29.

- Official paper aggregate net PnL: `-21.3979 EUR`
- Official paper closed trades: `555`
- Only positive official pair in snapshot: `TRXEUR`
  - Net PnL: `0.8851 EUR`
  - Profit factor: `1.48`
  - Win rate: `52.54%`
- Main blockers listed:
  - `cost_guard`
  - `microstructure_filter`
  - `opportunity_selection`
  - `strategy_governance_reconciliation`
- Interpretation: official paper ledger is still negative in aggregate; no strategy is live-ready.

## Research Dataset Used For Recent Validation

Source: `data/vps_autobot_state_2026-06-01.db`

Table: `market_price_samples`

Period:

- Start: `2026-05-27T20:25:09Z`
- End: `2026-06-01T11:55:57Z`

Symbols:

- `BTCZEUR`
- `ETHZEUR`
- `SOLEUR`
- `LTCZEUR`
- `XLMZEUR`
- `XRPZEUR`
- `TRXEUR`
- `ADAEUR`
- `LINKEUR`
- `DOTEUR`
- `BCHEUR`
- `ATOMEUR`
- `AVAXEUR`
- `AAVEEUR`

Costs:

- Research cost model includes taker fees, fallback spread, slippage, and latency buffer.
- Results below are net of modeled costs.

## Strategy Status Summary

### Dynamic Grid

Current status: `candidate`

Evidence:

- Official paper is running, but aggregate PnL is negative.
- TRXEUR is positive in one snapshot, but this is not enough because evidence may be pair-dominated.
- Standardized event-driven baselines are still incomplete for grid.

Decision:

- Continue testing.
- Do not promote to live.
- Do not increase risk based only on TRXEUR.

Main concern:

- Grid can look good on one ranging pair and fail badly when trend or spread regime changes.
- The current proof is not a robust walk-forward validation.

### Trend Momentum

Current status: `learning`

Evidence:

- Trend replay evidence is negative after costs.
- Stricter entry filters and cost-aware gates reduce losses but do not yet create profit.

Decision:

- Keep research/shadow-only.
- Do not route to official paper/live until positive net expectancy is proven.

### Mean Reversion

Current status: `learning`

Evidence:

- Shadow lab exists.
- No standardized replay/baseline evidence strong enough yet.

Decision:

- Keep research/shadow-only.
- Validate only after proper baselines and costs.

### Opportunity / Regime Scoring

Current role:

- Scoring and routing layer, not a standalone profit engine.

Decision:

- Useful as a filter/ranker.
- Must not be treated as proof of strategy profitability.

## Recent Research Results

### 1. Baseline Trend Setup Quality

Report: `reports/research/vps_2026_06_02_trend_setup_quality_setup_quality.md`

Configuration:

- Strategy: `trend_momentum`
- Symbols: top 14 EUR pairs listed above
- Trades: `221`

Results:

- Gross PnL: `-45.083564 EUR`
- Net PnL: `-115.803564 EUR`
- Cost-dominated trades: `140`
- Win rate: `17.19%`
- Average MFE: `66.44 bps`
- Average exit capture: `-20.38 bps`

Key diagnosis:

- Too many trades do not move enough after entry to overcome cost.
- The strategy often sees some favorable movement, but exits poorly.
- Regime context is still `unknown`, which is a critical validation gap.

Breakout buckets:

- Weak breakout `<40 bps`: `146` trades, net `-72.677642 EUR`
- Medium breakout `40-80 bps`: `67` trades, net `-32.005396 EUR`
- Strong breakout `>=80 bps`: `8` trades, net `-11.120526 EUR`

ATR buckets:

- Weak ATR `<15 bps`: `73` trades, win rate `5.48%`, net `-40.380329 EUR`
- Medium ATR `15-50 bps`: `144` trades, win rate `22.92%`, net `-70.164125 EUR`
- Strong ATR `>=50 bps`: `4` trades, net `-5.259110 EUR`

Interpretation:

- Weak ATR and weak breakouts are very damaging.
- However, simply requiring stronger ATR produced too few trades and still did not create profit.

### 2. Trend Exit Experiment

Report: `reports/research/vps_trend_exit_experiment_2026_06_02_summary.md`

Compared modes:

- Baseline ATR/trailing/exit-low behavior
- `cost_buffer_tp`
- `mfe_trailing`
- `time_stop`

Results:

| Mode | Trades | Gross PnL EUR | Net PnL EUR | Cost EUR | Avg Exit Capture bps |
| --- | ---: | ---: | ---: | ---: | ---: |
| baseline | 221 | -45.083564 | -115.803564 | 106.080000 | -20.381459 |
| cost_buffer_tp | 276 | -61.945157 | -150.265157 | 132.480000 | -22.423716 |
| mfe_trailing | 243 | -48.463463 | -126.223463 | 116.640000 | -19.925879 |
| time_stop | 221 | -45.083564 | -115.803564 | 106.080000 | -20.381459 |

Interpretation:

- Exit-only changes did not fix profitability.
- `mfe_trailing` slightly improved exit capture but not enough.
- `cost_buffer_tp` increased turnover and costs, worsening net PnL.
- The larger problem is entry quality and cost/edge mismatch, not exits alone.

### 3. Trend Entry Filter Experiment

Report: `reports/research/vps_trend_entry_filter_experiment_2026_06_02_summary.md`

Results:

| Config | confirm_bps | min_momentum_bps | min_atr_bps | Trades | Net PnL EUR | Cost EUR | Cost-Dominated |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline | 20 | 25 | 8 | 221 | -115.803564 | 106.080000 | 140 |
| no_weak_breakout | 40 | 40 | 15 | 94 | -36.414494 | 45.120000 | 43 |
| strong_momentum | 40 | 100 | 15 | 75 | -27.351476 | 36.000000 | 32 |
| strong_breakout | 80 | 100 | 15 | 24 | -21.645635 | 11.520000 | 14 |
| high_atr_strong | 40 | 100 | 50 | 6 | -10.368624 | 2.880000 | 2 |

Interpretation:

- Stricter entry filters reduce loss a lot.
- Best tested entry direction: `confirm_bps=40`, `min_momentum_bps=100`, `min_atr_bps=15`.
- Still negative after costs.
- Do not promote.

### 4. Cost / Edge Gate Experiment

Report: `reports/research/vps_trend_cost_edge_gate_experiment_2026_06_02_summary.md`

Base configuration:

- `confirm_bps=40`
- `min_momentum_bps=100`
- `min_atr_bps=15`

Tested gate:

- Require `gross_edge_bps - estimated_round_trip_cost_bps >= min_signal_net_edge_bps`

Results:

| Config | Min Net Edge After Cost | Trades | Gross PnL EUR | Net PnL EUR | Cost EUR | Cost-Dominated | Avg Exit bps |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| no gate | none | 75 | -3.351476 | -27.351476 | 36.000000 | 32 | -4.464617 |
| edge 0 | 0 | 75 | -3.351476 | -27.351476 | 36.000000 | 32 | -4.464617 |
| edge 40 | 40 | 75 | -3.351476 | -27.351476 | 36.000000 | 32 | -4.464617 |
| edge 80 | 80 | 47 | 0.303366 | -14.736634 | 22.560000 | 16 | 0.644879 |
| edge 120 | 120 | 30 | 3.227229 | -6.372771 | 14.400000 | 11 | 10.747757 |

Interpretation:

- Cost-aware gating helps.
- `edge_120` is the best tested trend candidate so far.
- It is still negative after costs.
- Sample size is only `30` trades.
- It should remain research-only.

Important:

- The gate is disabled by default.
- It does not alter live trading, official paper execution, Kraken integration, or dashboard behavior.

### 5. Strategy x Regime Comparison

Report: `reports/research/vps_2026_06_02_strategy_regime_comparison/vps_2026_06_02_strategy_regime_comparison.md`

Purpose:

- Compare the current research versions of grid, trend momentum, and mean reversion by market regime.
- Keep the same conservative cost model.
- Use regime labels only as diagnostics, not as execution permission.

Configurations:

- Dynamic grid: current research replay/default configuration.
- Mean reversion: current research replay/default configuration.
- Trend momentum: stricter candidate with `confirm_bps=40`, `min_momentum_bps=100`, `min_atr_bps=15`, and `min_signal_net_edge_bps=120`.

Overall results:

| Strategy | Trades | Gross PnL EUR | Net PnL EUR | Interpretation |
| --- | ---: | ---: | ---: | --- |
| dynamic_grid | 391 | -65.373353 | -190.493353 | High turnover and costs dominate; even decent win rates do not save it. |
| mean_reversion | 706 | -127.466757 | -353.386757 | Current default is too loose and strongly negative. |
| trend_momentum edge120 | 30 | 3.227229 | -6.372771 | Least bad tested setup, but still negative after costs. |

Important regime buckets:

| Strategy | Regime | Trades | Win Rate | Net PnL EUR | Notes |
| --- | --- | ---: | ---: | ---: | --- |
| dynamic_grid | chaos | 312 | 58.65% | -130.593793 | Win rate looks acceptable, but costs and poor exit capture destroy net PnL. |
| dynamic_grid | range | 37 | 37.84% | -20.529342 | Grid is not currently proving its expected range edge. |
| dynamic_grid | high_vol | 27 | 74.07% | -9.546466 | Good win rate but still net negative; sample concentrated on XLMZEUR. |
| mean_reversion | chaos | 496 | 19.96% | -242.470512 | Very poor fit in this regime. |
| mean_reversion | range | 200 | 0.50% | -106.172022 | Current mean-reversion default is not working in range either. |
| mean_reversion | high_vol | 4 | 100.00% | 0.714304 | Positive but only 4 trades; not actionable. |
| trend_momentum edge120 | high_vol | 6 | 0.00% | -7.609117 | This setup should likely block or penalize high-vol entries. |
| trend_momentum edge120 | chaos | 24 | 41.67% | 1.236346 | Slightly positive, but too small for promotion. |

Interpretation:

- The latest evidence strengthens the conclusion that AUTOBOT's problem is not simply "wrong pair selection".
- The current strategy defaults do not yet convert market movement into robust net profit.
- Grid is especially concerning: it can show a high win rate while losing money after costs.
- Mean reversion should be considered learning-only or rejected in its current default form until retested with stricter setup selection.
- Trend momentum with cost/edge gating is the closest candidate, but it is still too weak and too small-sample.
- No strategy should be promoted or sized up.

### 6. Strategy x Regime Baseline Comparison

Report: `reports/research/vps_2026_06_02_strategy_regime_baselines/vps_2026_06_02_strategy_regime_comparison_baseline_comparison.md`

Baselines added:

- `no_trade`
- `buy_and_hold_regime_segments`
- `random_signal_same_frequency_regime`

Result:

No strategy/regime bucket beats its best baseline.

Important examples:

| Strategy | Regime | Trades | Strategy Net EUR | Best Baseline | Baseline Net EUR | Delta EUR |
| --- | --- | ---: | ---: | --- | ---: | ---: |
| trend_momentum edge120 | chaos | 24 | 1.236346 | buy_and_hold_regime_segments | 252.495862 | -251.259515 |
| mean_reversion | high_vol | 4 | 0.714304 | buy_and_hold_regime_segments | 338.818134 | -338.103831 |
| dynamic_grid | chaos | 312 | -130.593793 | random_signal_same_frequency_regime | 50.040744 | -180.634537 |
| dynamic_grid | range | 37 | -20.529342 | no_trade | 0.000000 | -20.529342 |
| mean_reversion | range | 200 | -106.172022 | no_trade | 0.000000 | -106.172022 |

Interpretation:

- The small positive `trend_momentum / chaos` and `mean_reversion / high_vol` pockets are not evidence of strategy edge.
- They fail against simple regime-aware references.
- AUTOBOT should not promote or size up any of these buckets.
- The next requirement is walk-forward strategy x regime validation with baselines.

## Main Performance Diagnosis

AUTOBOT's poor performance is not explained by one single pair or one missing indicator.

The strongest evidence points to these issues:

1. Cost drag is too high relative to realized edge.
   - Many trades have movement, but not enough net movement after fees/spread/slippage.
   - In baseline trend replay, `140/221` trades were cost-dominated.

2. Entry quality is too weak.
   - Weak breakout and weak ATR trades are highly damaging.
   - Filtering weak entries improves results materially.

3. Exit capture is poor, but exit-only changes are insufficient.
   - Baseline average exit capture is negative.
   - MFE exists, but AUTOBOT often gives it back before closing.
   - However, tested exit variants did not solve the issue alone.

4. Regime context is not yet integrated into validation journals.
   - Recent setup quality replay reports all trades under `unknown` regime.
   - That prevents knowing whether grid/trend/mean reversion are being used in the right market states.

5. Strategy proof is still fragmented.
   - Official paper, shadow labs, and research replays are closer than before, but still not fully reconciled.
   - Dynamic grid has official paper evidence but lacks full standardized baselines.
   - Trend has improved replay diagnostics but remains negative.
   - Mean reversion lacks enough standardized evidence.

6. Dashboard/readiness should not be used as proof of profitability.
   - Runtime health means the system runs.
   - It does not mean strategies have positive expectancy.

## What Should Not Be Done

Do not:

- Activate live trading.
- Increase capital allocation to "make PnL visible".
- Lower global thresholds just to create more trades.
- Promote TRXEUR evidence as proof of global edge.
- Add ML/XGBoost/sentiment/deep learning to execution decisions before robust validation.
- Optimize one short dataset until it looks profitable.
- Treat synthetic replay success as real performance proof.

## Highest Priority Improvements

### Priority 1 - Reconcile Official Paper vs Research Replay

The system needs one canonical way to answer:

- Which signals were generated?
- Which were accepted/rejected?
- Which were executed?
- What was the modeled cost at decision time?
- What was the actual paper fill?
- What was the final net PnL?

Without that, AUTOBOT can keep "learning" from inconsistent ledgers.

### Priority 2 - Add Regime-Labeled Validation

Each trade and rejected signal should include:

- range / trend / chaos / low_activity / high_vol
- ATR bucket
- spread bucket
- liquidity bucket
- volatility bucket
- score bucket

Then evaluate each strategy by regime:

- Grid should be judged mostly in range/tight-spread regimes.
- Trend should be judged in persistent momentum/expanding-volatility regimes.
- Mean reversion should be judged in range/snapback regimes and blocked in strong trend continuation.

### Priority 3 - Make Cost/Edge Gate Part Of Research Candidate Selection

The cost/edge gate is promising because it reduced trend net loss from `-27.35 EUR` to `-6.37 EUR` on the tested dataset.

But it must stay research-only until:

- longer datasets confirm it;
- it beats no-trade and buy-and-hold/random baselines;
- it works across regimes or is explicitly regime-scoped;
- sample size is larger;
- exit behavior is improved.

### Priority 4 - Validate Grid With Baselines

Grid is still the most important runtime strategy historically, but aggregate official paper PnL is negative.

Needed:

- event-driven replay for grid;
- no-trade baseline;
- buy-and-hold baseline per pair;
- random-entry same-frequency baseline;
- static grid previous-config baseline;
- grid performance by regime;
- spread/cost sensitivity.

### Priority 5 - Validate Mean Reversion Separately

Mean reversion may be a better fit than pure grid/trend for some crypto EUR pairs, but it is still learning-only.

Needed:

- z-score / band / ATR regime validation;
- snapback expectancy after costs;
- trend-continuation failure analysis;
- walk-forward by symbol/regime.

### Priority 6 - Improve Exit Capture Only After Entry Quality

Exit improvement should not be ignored, but exit-only experiments failed.

Next exit research should be conditional:

- only on entries passing strong momentum + cost/edge gate;
- only in known trend regime;
- compare MFE trailing, conservative TP/SL, time stop, and regime-based exit.

## Suggested Question For GPT-5.5

Copy the prompt below into a new session if you want a deep external review.

```text
You are a senior quantitative trading systems engineer. Audit the AUTOBOT performance evidence below and propose concrete next steps.

Goal:
Help decide what should be improved next in AUTOBOT to move from negative paper/replay performance toward a robust positive expectancy system. Do not propose live trading. Do not propose increasing risk to hide weak edge. Do not propose adding complex ML unless the validation layer can prove it.

Current system:
- AUTOBOT is a paper-first crypto trading system on Kraken EUR pairs.
- It has dynamic grid, trend momentum, mean reversion, opportunity scoring, regime/entropy/Markov scoring, risk guards, paper trading, shadow labs, and an event-driven research validation harness.
- Live auto-promotion is disabled.
- Human review is required for live.

Known official paper snapshot:
- Aggregate official paper net PnL: -21.3979 EUR
- Official paper closed trades: 555
- Only positive official pair in snapshot: TRXEUR
  - Net PnL: 0.8851 EUR
  - Profit factor: 1.48
  - Win rate: 52.54%
- Interpretation: official paper is negative in aggregate; no live readiness.

Recent research dataset:
- Source: VPS paper state SQLite, table market_price_samples
- Period: 2026-05-27T20:25:09Z to 2026-06-01T11:55:57Z
- Symbols: BTCZEUR, ETHZEUR, SOLEUR, LTCZEUR, XLMZEUR, XRPZEUR, TRXEUR, ADAEUR, LINKEUR, DOTEUR, BCHEUR, ATOMEUR, AVAXEUR, AAVEEUR
- Costs include taker fees, fallback spread, slippage, and latency buffer.

Trend baseline setup quality:
- Trades: 221
- Gross PnL: -45.083564 EUR
- Net PnL: -115.803564 EUR
- Cost-dominated trades: 140
- Win rate: 17.19%
- Average MFE: 66.44 bps
- Average exit capture: -20.38 bps
- Weak breakout <40 bps: 146 trades, net -72.677642 EUR
- Weak ATR <15 bps: 73 trades, win rate 5.48%, net -40.380329 EUR
- Regime context is currently unknown in this replay.

Trend exit experiments:
- Baseline: 221 trades, net -115.803564 EUR
- cost_buffer_tp: 276 trades, net -150.265157 EUR
- mfe_trailing: 243 trades, net -126.223463 EUR
- time_stop: 221 trades, net -115.803564 EUR
- Conclusion: exit-only changes did not fix performance.

Trend entry filter experiments:
- Baseline: 221 trades, net -115.803564 EUR, cost-dominated 140
- no_weak_breakout (confirm 40, momentum 40, ATR 15): 94 trades, net -36.414494 EUR, cost-dominated 43
- strong_momentum (confirm 40, momentum 100, ATR 15): 75 trades, net -27.351476 EUR, cost-dominated 32
- strong_breakout (confirm 80, momentum 100, ATR 15): 24 trades, net -21.645635 EUR
- high_atr_strong (confirm 40, momentum 100, ATR 50): 6 trades, net -10.368624 EUR
- Conclusion: stricter entries reduce losses but remain negative.

Trend cost/edge gate experiments using strong_momentum baseline:
- no gate: 75 trades, gross -3.351476 EUR, net -27.351476 EUR, cost 36.0 EUR, cost-dominated 32, avg exit -4.46 bps
- edge 80: 47 trades, gross 0.303366 EUR, net -14.736634 EUR, cost 22.56 EUR, cost-dominated 16, avg exit 0.64 bps
- edge 120: 30 trades, gross 3.227229 EUR, net -6.372771 EUR, cost 14.4 EUR, cost-dominated 11, avg exit 10.75 bps
- Conclusion: cost-aware gating helps materially but still does not produce positive net PnL.

Strategy x regime comparison:
- Dynamic grid: 391 trades, gross -65.373353 EUR, net -190.493353 EUR.
- Mean reversion: 706 trades, gross -127.466757 EUR, net -353.386757 EUR.
- Trend momentum edge120: 30 trades, gross 3.227229 EUR, net -6.372771 EUR.
- Trend chaos bucket: 24 trades, net +1.236346 EUR, but too small to promote.
- Mean-reversion high-vol bucket: 4 trades, net +0.714304 EUR, too tiny to trust.
- Conclusion: all tested strategy families remain net negative overall. Regime labels are useful diagnostically, but they do not yet prove a tradable edge.

Strategy x regime baseline comparison:
- No strategy/regime bucket beats its best baseline.
- Trend chaos bucket is positive vs no-trade but loses to regime buy-and-hold by -251.259515 EUR.
- Mean-reversion high-vol bucket is positive vs no-trade but loses to regime buy-and-hold by -338.103831 EUR.
- Dynamic grid chaos loses to random same-frequency by -180.634537 EUR.
- Conclusion: the remaining positive pockets are not actionable edges.

Current diagnosis:
1. Costs consume too much of the edge.
2. Entry quality is weak, especially weak breakout and weak ATR trades.
3. Exit capture is poor, but exit-only changes are insufficient.
4. Regime labels are missing in validation journals.
5. Grid/trend/mean-reversion evidence is fragmented between official paper, shadow, and research replay.
6. Dynamic grid is candidate but aggregate official paper is negative.
7. Trend is learning-only and negative in replay.
8. Mean reversion is learning-only and lacks standardized evidence.

Question:
Based on professional quant/trading-system best practices, what should AUTOBOT improve next?

Please answer with:
1. Most likely root causes of negative performance.
2. Which strategy family should be prioritized next: grid, trend, mean reversion, or portfolio/router validation.
3. Whether the issue is more likely signal quality, exit logic, cost model, market regime selection, data quality, or execution assumptions.
4. A ranked 30-day technical roadmap.
5. Specific tests/backtests to run before changing production paper behavior.
6. Validation metrics and thresholds to require.
7. What not to change yet.
8. Any architecture changes needed to align paper, replay, shadow, and future live.
9. How to avoid overfitting while improving PnL.
10. A cautious recommendation for the next concrete code change.

Important constraints:
- Do not activate live trading.
- Do not lower global thresholds just to increase trade count.
- Do not increase risk/capital to hide weak edge.
- Do not add new ML models unless the validation system can prove them out-of-sample.
- Treat all results as net after fees/spread/slippage.
- Require baselines: no-trade, buy-and-hold, and random-entry same-frequency.
- Require regime-labeled performance.
```

## Recommended Next Internal Action

The next most useful AUTOBOT work item is not another strategy. It is to add regime context to the validation journals and rerun the matrix so that grid, trend, and mean-reversion are judged only in the market regimes they are designed for.

Recommended immediate experiment:

1. Keep current production/paper runtime unchanged.
2. In research replay only, attach regime context to every trade:
   - regime label
   - entropy score
   - Markov state
   - ATR bucket
   - spread bucket
   - liquidity bucket
3. Rerun:
   - grid replay by regime
   - trend `strong_momentum + edge_120` by regime
   - mean-reversion by regime
4. Reject configurations that are only good in tiny samples.
5. Promote nothing until a strategy beats baselines net of costs with enough closed trades.

## Bottom Line

AUTOBOT is becoming a serious validation system, but current performance evidence says it is not yet a serious profit engine.

The most promising direction is not "more trades"; it is fewer, better-qualified trades with:

- cost-aware edge gating;
- regime-specific routing;
- stricter entry validation;
- better exit capture only after entry quality is proven;
- canonical paper/replay ledger reconciliation.
