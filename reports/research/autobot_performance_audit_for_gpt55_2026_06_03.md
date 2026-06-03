# AUTOBOT Performance Audit For GPT-5.5 - 2026-06-03

## Copy-Paste Objective

You are reviewing AUTOBOT, a paper-first crypto trading system. The goal is not to add attractive modules or force more trades. The goal is to identify why validated paper/replay performance is still negative and what should be improved first to obtain a realistic positive expectancy after fees, spread, slippage, and execution friction.

Live trading must remain disabled. No strategy may be promoted to live without explicit human validation, objective paper evidence, baseline comparison, and paper/live parity review.

## Current Verdict

AUTOBOT is operational as a paper-first research system, but it is not yet a validated profitable trading bot.

The strongest conclusion from current evidence is:

- The issue is not only transaction costs.
- Gross PnL is already negative in the research matrix.
- Costs then make the result much worse.
- Current grid, trend, and mean-reversion defaults do not pass robust validation.
- The validation and traceability infrastructure is improving, but strategy quality is not proven yet.

No strategy should be promoted to live. No allocation should be increased based on current evidence.

## Latest Code Context

Latest relevant commit: `24c492b Add canonical execution trace bridge`

This commit improves measurement quality by making accepted BUY/SELL decision events persist before order creation and trade ledger writes. It does not alter live trading, strategy thresholds, sizing, risk, cost guards, Kraken execution, or dashboard behavior.

Previous diagnostic found the execution/PnL audit trail was incomplete:

- Total traces reconstructed: `8,948`
- Canonical complete traces: `455`
- Complete ratio: `5.08%`
- Execution complete traces: `0`
- Orphan trades: `555`
- Linked net PnL EUR: `-21.397803`

Interpretation: paper trading existed, but the audit trail could not reliably answer which exact signal and decision caused each realized PnL row. The latest bridge should improve future traceability, but old rows are not retroactively fixed.

## Official Paper Snapshot

Source: strategy registry / paper ledger snapshot dated 2026-05-29.

- Official paper closed trades: `555`
- Official paper aggregate net PnL: `-21.3979 EUR`
- Official paper profit factor: `0.361`
- Official paper win rate: `26.85%`
- Only positive official pair in snapshot: `TRXEUR`
  - Net PnL: `0.8851 EUR`
  - Profit factor: `1.48`
  - Win rate: `52.54%`

Interpretation:

TRXEUR being positive is not enough. The result is tiny, pair-dominated, and does not prove a robust strategy. Aggregate official paper performance is negative.

## Research Dataset

Source: local read-only copy of VPS database `data/vps_autobot_state_2026-06-01.db`.

Table used: `market_price_samples`

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

Cost model:

- Includes taker fees, fallback spread, slippage, and latency buffer.
- Bid/ask depth and queue position are still simulated, not fully measured from historical order book.

## Validation Matrix Result

Scope:

- 14 symbols
- 3 strategy families: grid, trend, mean reversion
- 42 matrix cells
- 42 successful cells
- 0 runtime errors
- Costs included

Registry-style recommendations:

| Strategy | Current Status | Recommended | Closed Trades | Net PnL | Best PF | Worst DD | Live Allowed |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| grid / `dynamic_grid` | candidate | rejected | 391 | -190.493353 | 0.305394 | 7.191241 | false |
| mean reversion | learning | rejected | 706 | -353.386757 | 0.283037 | 4.589784 | false |
| trend / `trend_momentum` | learning | rejected | 221 | -115.803564 | 0.540026 | 6.801713 | false |

Interpretation:

- No strategy family passed on any of the 14 symbols.
- The best observed PF is still far below 1.0 in the validation matrix.
- The losses are not isolated to one pair.
- Mean reversion is the largest loss source by total trade count and net loss.

## Loss Attribution

Aggregate research result:

| Metric | Value |
| --- | ---: |
| Gross PnL before modeled costs | -237.923673 |
| Net PnL after costs | -659.683673 |
| Total modeled costs | 632.640000 |
| Cost-flipped trades | 301 |

By strategy:

| Strategy | Trades | Gross PnL | Net PnL | Cost | Cost-Flipped |
| --- | ---: | ---: | ---: | ---: | ---: |
| grid | 391 | -65.373353 | -190.493353 | 187.680000 | 78 |
| trend | 221 | -45.083564 | -115.803564 | 106.080000 | 24 |
| mean reversion | 706 | -127.466757 | -353.386757 | 338.880000 | 199 |

Interpretation:

The gross result is already negative, so the main problem is signal/exit quality. Costs are a second major drag, not the only cause.

## Trade Path Diagnostics

Aggregate:

- Closed research trades: `1,318`
- Gross PnL before costs: `-237.923673`
- Net PnL after costs: `-659.683673`
- Cost-flipped trades: `301`
- Trades with MFE above cost: `298 / 1,318` or about `22.6%`
- Average MFE: `34.073026 bps`
- Average MAE: `-54.518933 bps`
- Average MFE/Cost ratio: `0.681461`

By strategy:

| Strategy | Trades | Net PnL | MFE > Cost Rate | Avg MFE | Avg MAE | Avg MFE/Cost |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| grid | 391 | -190.493353 | 33.25% | 42.722067 | -85.121411 | 0.854441 |
| trend | 221 | -115.803564 | 36.65% | 66.441342 | -46.511374 | 1.328827 |
| mean reversion | 706 | -353.386757 | 12.32% | 19.150684 | -40.077151 | 0.383014 |

Interpretation:

- Mean reversion is overactive and low-quality.
- Grid often enters too early or uses support-touch/stop logic that allows adverse movement to dominate.
- Trend is the most interesting family: it often sees favorable movement above cost, but exits convert that into negative net PnL. Trend likely needs exit-capture work before being discarded.

## Strategy x Regime Results

Regime-aware replay with Markov/entropy context:

| Strategy | Trades | Gross PnL | Net PnL | Verdict |
| --- | ---: | ---: | ---: | --- |
| dynamic_grid | 391 | -65.373353 | -190.493353 | FAIL |
| mean_reversion | 706 | -127.466757 | -353.386757 | FAIL |
| trend_momentum edge120 | 30 | 3.227229 | -6.372771 | FAIL_WITH_SIGNAL |

Notable buckets:

- `dynamic_grid / chaos`: 312 trades, 58.65% win rate, net `-130.593793`
- `dynamic_grid / range`: 37 trades, net `-20.529342`
- `mean_reversion / range`: 200 trades, 0.50% win rate, net `-106.172022`
- `trend_momentum edge120 / chaos`: 24 trades, net `+1.236346`
- `mean_reversion / high_vol`: 4 trades, net `+0.714304`

Interpretation:

Small positive pockets exist, but they are not proof. The samples are too small or fail baselines.

## Baseline Comparison

Baselines used:

- no-trade
- buy-and-hold within matching regime segments
- deterministic random same-frequency entries

Result:

No strategy/regime bucket beats its best baseline.

Examples:

- `trend_momentum / chaos`: strategy `+1.236346 EUR`, but regime buy-and-hold `+252.495862 EUR`, delta `-251.259515 EUR`
- `mean_reversion / high_vol`: strategy `+0.714304 EUR`, but regime buy-and-hold `+338.818134 EUR`, delta `-338.103831 EUR`
- `dynamic_grid / chaos`: strategy `-130.593793 EUR`, random same-frequency `+50.040744 EUR`, delta `-180.634537 EUR`

Interpretation:

The few positive buckets look more like market exposure, sample noise, or poor capture of a favorable regime than strategy edge.

## Walk-Forward Result

Walk-forward diagnostic:

- Train window: 600 bars
- Test window: 30 bars
- Step: 30 bars
- Min total trades: 30
- Folds evaluated: 1,696
- Buckets evaluated: 1,057

Verdict:

- Diagnostic tool: `PASS_WITH_WARNINGS`
- Strategy promotion: `FAIL`

Key rows:

| Strategy / Regime | Folds | Trades | Net PnL | Delta vs Best Baseline | Status | Reason |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| dynamic_grid / chaos | 280 | 308 | -125.063335 | -353.924994 | modify | non_positive_aggregate_net_pnl |
| mean_reversion / chaos | 366 | 494 | -240.891029 | -347.327016 | modify | non_positive_aggregate_net_pnl |
| trend_momentum / chaos | 174 | 203 | -101.778844 | -125.826026 | modify | non_positive_aggregate_net_pnl |
| mean_reversion / high_vol | 4 | 4 | 0.714304 | 0.714304 | keep_testing | insufficient_total_trades |

Interpretation:

No bucket is robust enough for promotion. The only positive one has only 4 trades.

## Current Hypotheses

1. Current AUTOBOT is too complex before strategy validation is strong enough.
2. Strategy defaults are not producing enough favorable movement after entry.
3. Mean reversion should probably be disabled or heavily constrained until it proves positive expectancy.
4. Grid is not currently behaving like a reliable range strategy; its support-touch and stop/recenter logic need research.
5. Trend has the best diagnostic signal because MFE often exceeds costs, but exit capture is poor.
6. Shadow results and official paper results are not reconciled enough to trust shadow winners.
7. The canonical decision/order/trade/PnL trace has historically been incomplete; commit `24c492b` improves future traceability but needs fresh runtime validation.
8. The dashboard should remain read-only and should not drive decisions.
9. More allocation or lower thresholds would likely amplify losses unless edge improves first.

## What To Improve First

Recommended priority:

1. Validate the canonical trace bridge on fresh paper runtime data.
2. Build/reinforce a single research contract for strategies:
   `MarketData -> Signal -> OpportunityScore -> Risk -> SimulatedExecution -> Ledger -> Metrics -> Baselines -> Decision`
3. Focus on trend exit-capture diagnostics:
   - MFE captured percentage
   - giveback from MFE to exit
   - exit lag in bars
   - trailing vs fixed TP vs time-stop
   - stop distance versus adverse movement
4. Constrain or pause mean reversion defaults until the z-score entry is proven with regime and confirmation filters.
5. Rework grid support-touch logic:
   - entry distance to recent low/high
   - volatility-normalized stop distance
   - recenter timing
   - avoid entering inside normal noise
6. Reconcile shadow and official paper:
   - same costs
   - same spread/slippage model
   - same signal contract
   - same ledger fields
7. Run baselines for every candidate:
   - no-trade
   - buy-and-hold
   - random same-frequency
8. Do not add ML, sentiment, or deep learning to official decisions until the base validation and ledger are reliable.

## Questions For GPT-5.5 To Answer

Please analyze this evidence and answer:

1. Is the main bottleneck entry quality, exit quality, cost model, strategy-regime mismatch, or trace/measurement quality?
2. Given MFE/MAE diagnostics, which family should be fixed first: grid, trend, or mean reversion?
3. For trend, what exit-capture mechanism should be tested first without overfitting?
4. For grid, what diagnostics would prove whether support-touch entries are too early?
5. For mean reversion, what confirmation/regime filters should be required before it can trade again in research?
6. Is the current cost model too conservative, realistic, or still optimistic for Kraken crypto pairs?
7. What minimum dataset and closed-trade count should be required before trusting any positive bucket?
8. How should AUTOBOT reconcile shadow winners with official paper losers?
9. What should be the next smallest code change with the highest information value?
10. What should explicitly not be changed yet?

## Hard Constraints

- Do not enable live trading.
- Do not increase allocation to chase losses.
- Do not lower thresholds just to create trades.
- Do not promote any strategy based on shadow-only performance.
- Do not trust a positive bucket unless it beats baselines after costs and survives walk-forward.
- Do not add complex ML until simple validated strategy evidence exists.
- Do not treat TRXEUR alone as proof of global edge.

## Desired Output From GPT-5.5

Please provide:

- Root-cause diagnosis ranked by confidence.
- Recommended next 3 engineering changes.
- Which strategy family to prioritize and why.
- Which strategy family to pause/constrain and why.
- Validation tests to run before and after changes.
- Metrics that would prove improvement.
- Failure criteria that should stop further optimization.
- A short roadmap that improves measurement first, then edge, then allocation.
