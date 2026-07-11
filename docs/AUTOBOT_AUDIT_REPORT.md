# AUTOBOT Audit Report

Date: 2026-05-31
Scope: AUTOBOT V2 repository at commit `96fce31`, current paper-first architecture, research validation stack, official paper ledger, shadow labs and strategy governance.

## Executive Summary

AUTOBOT is operationally stable enough to run in paper mode, but it is not yet a scientifically validated trading system. The current codebase contains many useful components, yet too many of them live in parallel: runtime paper execution, shadow labs, strategy routing, dashboard metrics, registry gates and replay validation do not yet share one canonical research/backtest contract.

The main performance evidence is still weak:

- Official paper ledger: `555` closed trades.
- Official paper net PnL: `-21.397803 EUR`.
- Official paper profit factor: `0.361`.
- Official paper win rate: `26.85%`.
- Only `TRXEUR` is positive in official paper, and the absolute PnL is small.
- Shadow labs show strong positive results on some variants, especially `XXLMZEUR`, but this conflicts with official paper results and must be reconciled before promotion.

No strategy is live-ready. Live auto-promotion must remain disabled.

## Current Architecture

### Runtime Orchestration

| Area | Files | Role | Current Assessment |
| --- | --- | --- | --- |
| Entrypoint/orchestration | `src/autobot/v2/main_async.py`, `orchestrator_async.py`, `orchestrator_services.py`, `orchestrator_core.py` | Starts websocket, instances, services, paper executor and background tasks | Works, but orchestration owns too many concerns |
| Instances | `instance_async.py`, `instance.py`, `colony_manager.py`, `instance_activation_manager.py` | Per-symbol/paper worker and activation state | Useful, but naming can confuse "pair worker" with independent trading bot |
| Market data | `websocket_async.py`, `market_data_quality.py`, `markets.py`, `market_selector.py`, `universe_manager.py` | Ticker/book ingestion, pair list, market quality and universe selection | Good runtime sensors; historical data repository remains missing |
| Strategy layer | `strategies/grid_async.py`, `strategies/trend_async.py`, `strategies/mean_reversion.py`, `setup_shadow_lab.py`, `trend_shadow_lab.py`, `mean_reversion_shadow_lab.py` | Grid, trend and mean-reversion logic plus paper-only shadow variants | Strategies and shadow labs are not yet normalized behind one research interface |
| Opportunity/routing | `opportunity_scoring.py`, `strategy_router.py`, `strategy_governance.py`, `strategy_promotion_gate.py` | Scores opportunities, ranks engines, applies governance and promotion rules | Valuable, but must be validated by replay and official/shadow reconciliation |
| Risk/execution | `risk_manager.py`, `signal_handler_async.py`, `order_router.py`, `order_executor_async.py`, `paper_trading.py`, `kill_switch.py` | Sizing, cost guard, microstructure filter, order execution and paper simulation | Live safety exists; paper/live parity needs a formal cost/execution model |
| Persistence/ledger | `persistence.py`, `decision_journal.py`, `strategy_trade_reconciliation.py`, `pnl_causality_audit.py` | SQLite state, positions, orders, trade ledger, decision ledger | Strong base, but research/backtest ledger is not yet canonical |
| Metrics/validation | `quant_validation.py`, `pf_validation.py`, `research_validation_harness.py`, `reports/research/backtest_audit.md` | Realized paper metrics, PBO/DSR proxy, replay harness | Improving; still incomplete as full event-driven backtesting system |
| Dashboard/API | `api/dashboard.py`, `dashboard/src/*` | Operational monitoring | Useful for humans, but should stay read-only and avoid trading decisions |

## Decision Flow

Observed intended pipeline:

`MarketData -> Strategy Signal -> OpportunityScore -> StrategyRouter/Governance -> Risk/Cost/Microstructure -> PaperExecution -> Position/TradeLedger -> Metrics/Dashboard`

Current gaps:

- Shadow labs can produce positive evidence that does not match official paper results.
- Official runtime execution and research replay do not yet consume one identical strategy interface.
- Backtests/replays do not yet cover all strategies on real historical OHLCV or order-book data.
- Paper execution is more realistic than before, but still not proven equivalent to future live behavior.

## Where Key Truths Live

| Truth | Current Source |
| --- | --- |
| Official paper realized PnL | `trade_ledger` in `data/autobot_state.db`, exposed through `quant_validation.py` and dashboard endpoints |
| Paper order/fill lifecycle | `paper_trading.py`, `orders`, `order_state_transitions`, `trade_ledger`, `paper_trades.db` |
| Shadow grid evidence | `setup_shadow_lab.db`, `setup_shadow_lab.py` |
| Shadow trend evidence | `trend_shadow_lab.db`, `trend_shadow_lab.py` |
| Shadow mean-reversion evidence | `mean_reversion_shadow_lab.db`, `mean_reversion_shadow_lab.py` |
| Decision trace | `decision_ledger`, `signal_outcomes`, `signal_handler_async.py` |
| Runtime market samples | `market_price_samples`, now loadable by `research_validation_harness.py` |
| Dashboard truth | Should be backend API only; no frontend-invented trading truth |

## Technical Debt

### Complexity Before Validation

AUTOBOT contains many advanced modules: XGBoost, sentiment NLP, CNN/LSTM, multi-indicator voting, Kelly sizing, pyramiding, autonomous review, regime/entropy scoring, shadow labs and colony logic. These are potentially useful, but they increase degrees of freedom before the validation pipeline is strong enough.

Decision: keep these modules in the repository, but keep them disabled or learning-only unless they pass objective validation.

### Strategy Interface Fragmentation

Grid, trend, mean-reversion and shadow variants do not expose one shared signal contract such as:

`generate_signal(candle_window, portfolio_state, market_regime) -> Signal`

Decision: introduce a research strategy interface before adapting strategies. Do not force runtime strategies into it abruptly.

### Backtesting Gaps

Existing `research_validation_harness.py` is a good start, but there is no complete production-grade historical backtest engine yet.

Current missing pieces:

- OHLCV repository with data-quality checks.
- Standard trade journal independent from runtime DB.
- Standalone cost model with fees, spread, slippage and liquidity rejection.
- Metrics engine shared by backtest, walk-forward and paper reports.
- Walk-forward engine with train/validation/test separation.
- Strategy scorecard that decides promotion state objectively.

### PnL And Cost Risk

Official paper uses `trade_ledger`, but shadow labs and replay reports can use different cost assumptions. This can explain why shadow `XXLMZEUR` appears profitable while official paper `XXLMZEUR` is negative.

Decision: every report must version its fee/spread/slippage assumptions and show gross PnL vs net PnL.

### Live/Paper Mixing Risk

Current registry says:

- `live_auto_promotion_allowed = false`.
- live review requires `paper_validated`.
- human review is required.

Decision: preserve this. No roadmap phase should weaken live safety.

### Dashboard Scope Creep

The dashboard has accumulated many advanced diagnostics. This is useful for debugging but too much for day-to-day operation.

Decision: keep dashboard changes out of the research foundation phase. Later simplify around health, PnL, risk, decisions and current blocker.

## Module Decisions

| Module/Area | Decision | Reason |
| --- | --- | --- |
| `dynamic_grid` | Keep as candidate, do not live | Official paper aggregate is negative; needs official/shadow reconciliation |
| `trend_momentum` | Keep learning/shadow | Positive shadow pockets exist, but no robust official/walk-forward proof |
| `mean_reversion` | Keep learning/shadow | Evidence is too small and mixed |
| `opportunity_scoring` | Keep as guard, validate by ablation | Useful ranking layer but not standalone alpha |
| `entropy_markov_regime` | Keep as bounded sensor | Useful context, not proof of prediction |
| `triangular_arbitrage` | Keep retired from execution | Needs synchronized depth and multi-leg execution model |
| XGBoost/sentiment/CNN/LSTM/AI agents | Disable from real decisions by default | Too many degrees of freedom without out-of-sample proof |
| Kelly aggressive sizing/pyramiding | Disable by default | Dangerous without >200 robust trades per strategy |
| Paper executor | Keep, but compare with research cost model | Official paper is closest to future live path |
| Shadow labs | Keep isolated | Shadow evidence must never promote automatically |

## Priority Refactor Plan

1. Create isolated research package:
   - `MarketDataRepository`
   - `ExecutionCostModel`
   - `TradeJournal`
   - `MetricsEngine`
2. Build simple event-driven backtest engine on top of that package.
3. Run real replay/backtests from `market_price_samples` and CSV/OHLCV.
4. Reconcile official paper vs shadow, starting with `XXLMZEUR`.
5. Add walk-forward validation.
6. Add strategy scorecard and promotion recommendations.
7. Only then adapt runtime strategies more deeply.

## Immediate Red Flags To Investigate

- Official paper PF `0.361` after `555` closed trades.
- `XXLMZEUR` is strongly positive in shadow but negative in official paper.
- Large number of cancelled sell rows in `paper_trades.db` must be explained as expected lifecycle or bug.
- Websocket backpressure was active during observation and may affect timeliness.
- Market data/book invalidation has required many resubscriptions historically.

## Safety Invariants

- `ENABLE_LIVE_TRADING` must remain false unless the user explicitly approves live.
- Shadow results cannot authorize official paper/live execution.
- No ML/sentiment/deep-learning module can influence live decisions before out-of-sample validation.
- PnL must be net of fees, spread and slippage in validation reports.
- No strategy can be promoted without baseline comparison and human review.

## Current Verdict

AUTOBOT is a promising paper research system, not a live-ready profitable bot. The next work should improve measurement, not add alpha modules.
