# P0 Strategy Registry + Paper Ledger Non-Regression - 2026-07-01

## Verdict

PASS_WITH_WARNINGS pending VPS deployment verification.

## Scope

This patch hardens the official paper trading path around a mandatory strategy identity:

Signal / order intent -> registry and runtime policy -> promotion gate -> allocation/risk path -> paper/order router -> paper ledger -> metrics.

No new strategy was added. No UI-visible design was changed. No live trading flag, sizing rule, leverage rule, or runtime promotion flag was changed.

## Files Changed

- `docs/research/strategy_hypotheses.json`
- `src/autobot/v2/strategy_runtime_policy.py`
- `src/autobot/v2/strategy_promotion_gate.py`
- `src/autobot/v2/strategy_router.py`
- `src/autobot/v2/order_router.py`
- `src/autobot/v2/order_queue_async.py`
- `src/autobot/v2/paper_trading.py`
- `src/autobot/v2/persistence.py`
- `src/autobot/v2/paper/ledger_loader.py`
- `src/autobot/v2/signal_handler_async.py`
- `src/autobot/v2/orchestrator_async.py`
- `src/autobot/v2/portfolio_allocator.py`
- `src/autobot/v2/research/strategy_orchestrator.py`
- Tests under `tests/` and `src/autobot/v2/tests/`.

## Critical Behavior

- Fill-creating orders require `strategy_id` in `OrderRouter`.
- `PaperTradingExecutor` rejects market, limit, and stop-loss orders without `strategy_id`.
- `PaperTradingExecutor` rejects retired Grid aliases (`dynamic_grid`, `grid`, `grid_core`).
- `StatePersistence.append_trade_ledger()` rejects missing `strategy_id` and retired Grid aliases.
- Paper ledger schema now carries `strategy_id`, `timeframe`, `signal_source`, `gross_pnl`, `net_pnl`, `regime`.
- Paper ledger can aggregate metrics by `strategy_id`.
- Promotion gate requires `strategy_id`, fees evidence, slippage evidence, baseline comparison, and at least one out-of-sample period.
- `dynamic_grid` is marked `retired_from_execution` in the research registry and is not promotable.
- Portfolio allocation no longer applies legacy BTC/ETH preference when a metrics map exists; symbols without evidence receive conservative treatment.

## Strategy Registry Status

| Strategy | Status | Paper Status | Decision |
|---|---|---|---|
| dynamic_grid | retired_from_execution | archived_no_new_official_paper_writes | do_not_execute |
| trend_momentum | learning | shadow_only | continue_shadow_only |
| mean_reversion | learning | shadow_only | continue_shadow_only |
| opportunity_scoring | candidate | runtime_filter_active_paper_first | keep_as_guard_measure_incremental_value |
| entropy_markov_regime | learning | score_modifier_only | keep_observing_bounded_adjustment |
| no_trade_baseline | paper_validated | active_router_safety_choice | keep |
| triangular_arbitrage | retired_from_execution | not_routed | do_not_execute |

## Tests

Commands run locally:

```powershell
python -m compileall -q src
$env:PYTHONPATH='src'; python -m pytest tests/test_strategy_router.py tests/test_paper_trading.py tests/test_pf_phase2.py tests/test_persistence_compat.py tests/test_position_exit_and_allocation.py tests/research/test_archived_grid_defaults.py tests/paper/test_paper_ledger_loader.py src/autobot/v2/tests/test_order_router.py -q
$env:PYTHONPATH='src'; python -m pytest tests/research tests/test_v2_cli.py -q
$env:PYTHONPATH='src'; python -m pytest tests/test_strategy_validation_registry.py tests/test_strategy_router.py tests/test_strategy_governance.py tests/test_instance_split_policy.py tests/test_instance_split_planner.py tests/research/test_strategy_orchestrator.py tests/research/test_registry_recommendations.py tests/research/test_batch_strategy_decision_thresholds.py -q
$env:PYTHONPATH='src'; python -m pytest tests/test_strategy_trade_reconciliation.py tests/test_strategy_reconciliation.py tests/test_pair_strategy_health.py -q
$env:PYTHONPATH='src'; python -m pytest src/autobot/v2/tests/test_portfolio_allocator.py -q
$env:PYTHONPATH='src'; python -m pytest tests/test_strategy_router.py tests/test_paper_trading.py tests/test_pf_phase2.py tests/test_persistence_compat.py tests/test_position_exit_and_allocation.py tests/research/test_archived_grid_defaults.py tests/paper/test_paper_ledger_loader.py src/autobot/v2/tests/test_order_router.py src/autobot/v2/tests/test_portfolio_allocator.py tests/test_strategy_validation_registry.py tests/test_strategy_governance.py tests/test_instance_split_policy.py tests/test_instance_split_planner.py tests/test_strategy_trade_reconciliation.py tests/test_strategy_reconciliation.py tests/test_pair_strategy_health.py -q
```

Results:

- `compileall`: PASS.
- P0 router/paper/ledger focused suite: 88 passed, 4 existing pytest warnings.
- Research + CLI suite: 229 passed.
- Governance/registry suite: 65 passed.
- Strategy reconciliation suite: 12 passed.
- Portfolio allocator suite: 10 passed.
- Final combined P0 suite: 141 passed, 4 existing pytest warnings.

Warnings:

- Existing `PytestWarning` entries in `src/autobot/v2/tests/test_order_router.py` where non-async tests inherit an asyncio mark. Not introduced by this patch and not blocking.

## Live Safety Confirmation

- No live flag was changed.
- No Kraken order was created locally.
- No strategy was promoted.
- No instance split/duplication was enabled.
- Grid remains code-present but runtime-disabled/research-only.

## VPS Deployment

Pending at local report creation. Must be updated after deployment with:

- deployed commit SHA;
- container status;
- `/health`;
- `PAPER_TRADING`;
- `LIVE_TRADING_CONFIRMATION`;
- `ENABLE_LIVE_TRADING` if present;
- `ENABLE_INSTANCE_SPLIT_EXECUTOR` if present;
- log check for tracebacks/critical errors;
- confirmation no live order was created.

## Residual Risks

- Existing legacy open paper positions without strategy metadata may be blocked from new official ledger writes until explicitly reconciled or migrated. This is intentional for P0 safety but should be audited before any future paper promotion.
- Historical ledger rows without `strategy_id` remain historical data and are not retroactively trusted for strategy promotion.
- Tracked `.pyc` files in the repository were touched by local compilation; they are intentionally not part of this patch.
