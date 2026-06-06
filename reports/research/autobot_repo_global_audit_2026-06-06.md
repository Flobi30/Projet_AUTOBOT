# AUTOBOT Repo Global Audit - 2026-06-06

Commit audited: `8f06680`

Scope: runtime paper/live, research/backtest stack, grid results, strategy-experiments runner, costs, duplication/spin-off and live guards.

## Executive Verdict

AUTOBOT is not live-ready and not paper-validated. The repo is now better instrumented for measurement, but the official runtime still appears grid-oriented and the research/paper parity is not tight enough to use research conclusions as promotion evidence.

No live setting was changed in this audit. No Kraken order path was executed.

## Runtime Entry Map

| Area | Files | Role | Can influence paper orders? | Live risk |
| --- | --- | --- | --- | --- |
| Process entry | `src/autobot/v2/main_async.py` | starts orchestrator, startup attestation, API/dashboard | yes, by starting orchestrator services | high if env/live gates are changed |
| Startup safety | `src/autobot/v2/startup_attestation.py` | startup checks and evidence | indirect | safety-critical |
| Orchestration | `src/autobot/v2/orchestrator_async.py` | instance lifecycle, market data, spin-off, risk/executor wiring | yes | high |
| Paper execution | `src/autobot/v2/paper_trading.py` | simulated executor and paper ledger | yes | medium if confused with live |
| Async execution | `src/autobot/v2/order_executor_async.py` | live-capable Kraken order executor | no in paper unless wired | very high |

## Research Stack Map

| Module | Status | Notes |
| --- | --- | --- |
| `dataset_builder.py` | research-only | builds datasets from runtime samples; runtime samples lack real volume/book data. |
| `market_data_repository.py` | research-only | loads CSV/Parquet/state DB; no order path. |
| `backtest_engine.py` | research-only | simulates validation; separate from runtime execution. |
| `execution_cost_model.py` | research-only | default conservative cost model: 16 bps fee, 8 bps spread, 4 bps slippage, 1 bps latency. |
| `metrics_engine.py` | research-only | computes net metrics. |
| `loss_attribution.py` | research-only | explains failure modes such as `weak_mfe_below_cost`. |
| `grid_experiment_runner.py` | research-only | grid variants; no promotion. |
| `strategy_experiment_runner.py` | research-only | trend/mean-reversion variants; no promotion. |
| `walk_forward.py` | research-only | validation support. |
| `strategy_scorecard.py` | research-only | evidence score; does not authorize live alone. |
| `historical_data_collector.py` | new, research-only | public Kraken OHLCV collector; no private endpoints. |
| `data_quality_report.py` | new, research-only | flags gaps, missing volume, missing bid/ask/depth. |
| `batch_strategy_validation.py` | new, research-only | multi-window validation wrapper. |
| `research_paper_parity.py` | new, research-only | compares research replay with official paper ledger. |

## Runtime Strategy Map

| Component | Status | Can affect orders? | Assessment |
| --- | --- | --- | --- |
| Official grid | active | yes | Runtime remains effectively grid-first/grid-dominant for official paper evidence. |
| Trend research | research/backtest and some shadow/dashboard visibility | not proven as official runtime order source | must remain research-only. |
| Mean reversion | shadow/research; module disabled by default in `ModuleManager` | not by default | must remain research-only. |
| `strategy_router.py` | dashboard/observe and possible routing snapshot | should be treated as decision-critical if enabled | needs parity hardening before allowing paper/live routing changes. |
| `strategy_governance` | registry/promotion guard area | should block unvalidated strategies | should become mandatory in every route to execution. |
| Shadow labs | shadow-only | no official order path intended | useful evidence, not promotion by itself. |
| Setup optimizer | observe/research assist | can become dangerous if wired to runtime entries | keep observe-only until validated. |
| Module manager | active module toggles | yes if modules are enabled | risky defaults: some helper modules default true; experimental modules mostly false. |

## Risk And Execution Map

| Component | Role | Risk |
| --- | --- | --- |
| `RiskManager` | risk checks by instance/config | must remain before execution. |
| `OrchestratorRiskManager` | orchestrator-level risk control | critical. |
| `PaperTradingExecutor` | official paper fills/ledger | cost parity is close on average, but slippage anomalies exist. |
| `OrderRouter` | live-capable routing | must remain behind paper/live gates and human confirmation. |
| `OrderExecutorAsync` | live Kraken execution | high-risk; no change made. |
| Startup gates | live/paper safety checks | no live relaxation detected in this work. |

## Duplication / Scaling Map

| Component | Status | Assessment |
| --- | --- | --- |
| `check_spin_off` in `orchestrator_async.py` | runtime-capable logic | can create child instances if runtime criteria pass; older logic relies on active in-memory child state plus PF/capital. |
| `instance_lineage` | persistent lineage table | exists, but old runtime check should be audited to ensure lifetime one-split rule is enforced persistently before execution. |
| `ColonyManager` | logical routing/budget view | paper/logical planning; not enough as validation evidence. |
| `InstanceActivationManager` | activation tiers | can affect running/paused behavior. |
| `PortfolioAllocator` | allocation logic | can affect sizing if wired. |
| `ScalabilityGuard` | resource guard | useful guard; not a strategy validator. |
| `instance_split_policy.py` | new, disabled policy | blocks split unless strict evidence passes; executor flag defaults false. |
| `instance_split_planner.py` | new, read-only planner | checks persistent lineage and policy; creates no child. |

## Answers To Required Questions

- Modules that can really influence paper orders: `orchestrator_async.py`, official grid path, `signal_handler_async.py`, `RiskManager`, `PaperTradingExecutor`, and any runtime-enabled router/module that feeds signals before execution.
- Research-only modules: dataset builder, validation matrix, backtest engine, cost model, metrics, loss attribution, grid experiments, strategy experiments, historical collector, data quality, batch validation, research-paper parity.
- Dormant/feature-flagged modules: mean reversion runtime, XGBoost, sentiment, pyramiding, instance split executor. Some optional helper modules default active in `ModuleManager` and should be treated carefully.
- Dangerous if activated too early: live `OrderExecutorAsync`, `OrderRouter`, Kelly/pyramiding, XGBoost/sentiment, setup optimizer as execution input, spin-off executor.
- Runtime official still oriented grid: yes, official paper ledger evidence is mostly `dynamic_grid`.
- Router/governance can block grid only if every execution path uses it. This is not yet fully proven by parity.
- Duplication can create a child in older runtime path. New split policy/planner is blocking/read-only, but old runtime `check_spin_off` still deserves hardening before any executor is enabled.
- Duplication is now blocked by the new policy for unvalidated/unprofitable evidence. Existing runtime must still be wired to this policy before being trusted.
- Live remains blocked by configuration rules and was not changed by this audit.

## Main Risks

1. Research/paper mismatch is high: research sees trades paper did not take and misses paper trades on many symbols.
2. Data quality from runtime samples is not enough for strategy validation: no real volume, no bid/ask/depth, many gaps.
3. Paper ledger has slippage anomalies and missing realized PnL rows.
4. Old spin-off logic must not be trusted until it is routed through persistent split policy.

## Recommendation

Do not promote any strategy or duplication. Next work should focus on data foundation and parity before trying to improve PnL.
