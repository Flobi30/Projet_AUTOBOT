# AUTOBOT Backtest And Validation Audit

Date: 2026-05-29

Scope: current AUTOBOT V2 strategy validation stack, including official paper
ledger analysis, setup shadow lab, trend shadow lab, mean-reversion shadow lab,
PBO/DSR proxy validation, strategy router, opportunity scoring and regime
features.

## Executive Finding

AUTOBOT has useful paper and shadow validation sensors, but it does not yet have
a full production-grade event-driven backtesting engine. Current results should
be treated as operational paper/shadow evidence, not as completed scientific
backtests. No current strategy should be considered live-ready.

## Components Audited

| Component | File | Role | Finding |
| --- | --- | --- | --- |
| Official paper validation | `src/autobot/v2/quant_validation.py` | Builds realized trade metrics from paper DB or trade ledger | Good for realized paper monitoring, not a historical market replay |
| PnL sequence checks | `src/autobot/v2/pf_validation.py` | Lightweight walk-forward and cost sensitivity over PnL sequences | Useful sanity check, but not enough for true OOS strategy validation |
| Grid shadow lab | `src/autobot/v2/setup_shadow_lab.py` | Paper-only grid variant simulator | Includes fees/slippage, but fill model is simplified |
| Trend shadow lab | `src/autobot/v2/trend_shadow_lab.py` | Paper-only trend/momentum variants | Includes fees/slippage, needs standardized baselines |
| Mean-reversion shadow lab | `src/autobot/v2/mean_reversion_shadow_lab.py` | Paper-only snapback variants | Includes fees/slippage, production strategy remains disabled |
| Strategy router | `src/autobot/v2/strategy_router.py` | Ranks grid/trend/mean-reversion/no-trade from shadow evidence | Correctly paper-only, but not a validator by itself |
| Strategy reconciliation | `src/autobot/v2/strategy_reconciliation.py` | Compares official paper with shadow evidence | Important guard; should remain mandatory before promotion |
| Regime features | `src/autobot/v2/regime_features.py` | Entropy/Markov context for scoring | Useful sensor; not proof of alpha |

## Cost Model

### Fees

Strengths:

- Official paper ledgers store fees and `quant_validation` includes fees when
  realized PnL is reconstructed.
- Grid, trend and mean-reversion shadow labs subtract per-side fee bps.
- Reconciliation reports fee drag and can flag fee deltas.

Gaps:

- Fee assumptions are not centrally versioned per backtest id.
- Shadow fee defaults differ by engine (`8 bps` grid, `12 bps` trend/mean
  reversion), which may be valid but must be documented per report.
- Baseline comparisons do not yet prove that every metric is net of the same fee
  model.

Verdict: partially covered, must be standardized in reports.

### Spread

Strengths:

- Opportunity scoring uses spread bps and can block wide spreads.
- Market data quality and order-book checks exist.

Gaps:

- The shadow labs primarily use fixed slippage/cost bps, not full historical
  bid/ask replay.
- A backtest can still be optimistic if it uses last-trade prices rather than
  bid/ask executable prices.

Verdict: monitored at runtime, incomplete in backtest simulation.

### Slippage

Strengths:

- Shadow labs subtract configurable slippage bps.
- Official trade reconciliation tracks slippage bps when available.

Gaps:

- No queue position, partial fill, depth depletion, latency or impact model.
- No stress grid that replays worse slippage regimes across all strategies.

Verdict: basic bps model only.

## Bias And Validation Risks

| Risk | Current State | Required Improvement |
| --- | --- | --- |
| Look-ahead bias | No obvious future-price use in rolling runtime labs, but no formal test across all strategy features | Add timestamped event-driven replay and tests that indicators only use data available at decision time |
| Survivorship bias | Static monitored universe; no historical universe management | Record universe snapshots and pair eligibility changes |
| Train/test separation | `pf_validation` checks PnL slices; no full raw-market train/test engine | Add strategy backtests with train, validation and out-of-sample windows |
| Walk-forward | Proxy available, not comprehensive | Add rolling market replay with frozen parameters per test window |
| Baseline comparison | No-trade is present in router; standardized buy/hold/random baselines are missing | Add required baseline metrics to every strategy report |
| Overfitting | PBO/DSR proxy exists, but not connected to parameter search counts for every engine | Track number of tried variants and use deflated metrics by strategy |
| Fill optimism | Shadow labs use threshold fills with fixed costs | Add bid/ask/depth fill model and partial fill handling |
| TP/SL realism | Grid/trend/mean-reversion exits exist, but fill assumption is simplified | Replay exits against executable prices and include latency/slippage |
| Metrics completeness | PnL, PF, win rate, DD, Sharpe proxy exist | Standardize Sortino, expectancy, median trade, regime split and baseline delta |

## Strategy-Level Status

| Strategy | Current Status | Reason |
| --- | --- | --- |
| `dynamic_grid` | `candidate` | Official paper is active but negative in aggregate; shadow evidence requires reconciliation and standardized baselines |
| `trend_momentum` | `learning` | Shadow-only, no official paper/walk-forward proof |
| `mean_reversion` | `learning` | Shadow-only and production class is explicitly disabled |
| `opportunity_scoring` | `candidate` | Useful guard, but needs ablation against no-score routing |
| `entropy_markov_regime` | `learning` | Sensor only; incremental value not proven |
| `no_trade_baseline` | `paper_validated` | Valid safety baseline |
| `triangular_arbitrage` | `retired_from_execution` | Prototype lacks synchronized depth/fill model |

## Critical Gaps

1. No full event-driven historical backtester yet.
2. No standardized strategy report generated from the same metrics schema.
3. No mandatory baseline bundle for every candidate.
4. No robust train/test/walk-forward engine over raw market data.
5. No depth-aware fill model.
6. No central backtest id/version tying parameters, data, fees and slippage.
7. Current regime scoring is a helpful context sensor, not validated alpha.

## Current Safe Interpretation

- A positive shadow result is not proof of profitability.
- A positive pair-level result, especially if dominated by one symbol, is not a
  portfolio-level strategy.
- Official paper PnL has more weight than shadow PnL because it is closer to the
  real execution path.
- AUTOBOT should keep learning in paper until a strategy passes the new
  registry workflow.

## Recommended Next Technical Step

Build a small event-driven backtest harness that replays saved ticks/order-book
snapshots through this pipeline:

`MarketData -> Signal -> OpportunityScore -> Risk -> SimulatedExecution -> Ledger -> Metrics -> Baselines`

The harness should output one immutable backtest id per strategy/config/symbol
set, then write validation reports from that id. Until then, strategies should
remain `learning` or `candidate`, except the explicit `no_trade_baseline`.
