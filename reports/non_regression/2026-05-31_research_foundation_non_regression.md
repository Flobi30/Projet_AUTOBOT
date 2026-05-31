# Non-Regression Report - Research Foundation Modules

Date: 2026-05-31
Verdict: PASS_WITH_WARNINGS

## Scope

This change starts the roadmap's validation/research foundation. It adds isolated
research-only components and documentation. It does not change runtime strategy
selection, paper execution, live execution, Kraken integration, dashboard routes,
or Docker configuration.

## Files Changed

- `docs/AUTOBOT_AUDIT_REPORT.md`
  - Adds a current-state architecture and risk audit for AUTOBOT.
- `reports/research/autobot_performance_audit_for_gpt55_2026-05-31.md`
  - Adds a performance audit brief intended for follow-up external review.
- `src/autobot/v2/research/__init__.py`
  - Introduces an isolated research package.
- `src/autobot/v2/research/market_data_repository.py`
  - Adds `MarketBar`, `MarketDataRepository`, and market data quality reporting.
- `src/autobot/v2/research/execution_cost_model.py`
  - Adds research-only fee/spread/slippage/latency/liquidity simulation.
- `src/autobot/v2/research/trade_journal.py`
  - Adds deterministic research trade records plus JSON/CSV export helpers.
- `src/autobot/v2/research/metrics_engine.py`
  - Adds net-of-cost metrics, drawdown, PF, winrate, expectancy, Sharpe-like,
    Sortino-like, baseline comparison, and regime aggregation.
- `src/autobot/v2/research/backtest_engine.py`
  - Adds a deterministic research-only OHLCV replay/backtest engine with
    explicit costs, no-trade/buy-hold baselines, JSON/Markdown reports, and
    non-live decisions.
- `tests/research/*`
  - Adds unit tests for the new research foundation modules.

## Critical Areas Checked

- Live trading: unchanged.
- Paper trading runtime: unchanged.
- Strategy router: unchanged.
- Risk management runtime: unchanged.
- Dashboard/API runtime: unchanged.
- Existing replay harness: unchanged.
- Docker/VPS runtime: not modified and not restarted for this local-only change.
- Persistent data: untouched.

## Trading Safety Confirmation

- No strategy can be promoted by these modules.
- No Kraken/live order path is imported or called.
- No sizing, leverage, stop-loss, take-profit, kill-switch, or execution rule was changed.
- No fallback permissive route was added.
- The new execution cost model is research-only and cannot submit orders.
- The new backtest engine is research-only and cannot submit orders.
- The new metrics engine reports undefined profit factor as `None` instead of
  inventing a fake large value when there are no losses.

## Validation Commands

```powershell
python -m py_compile src\autobot\v2\research\market_data_repository.py src\autobot\v2\research\execution_cost_model.py src\autobot\v2\research\trade_journal.py src\autobot\v2\research\metrics_engine.py
python -m py_compile src\autobot\v2\research\backtest_engine.py tests\research\test_backtest_engine.py
```

Result: PASS

```powershell
$env:PYTHONPATH='src'; python -m pytest tests\research -q
```

Result: PASS - `13 passed in 0.18s`

Follow-up after adding `BacktestEngine`: PASS - `17 passed in 0.20s`

```powershell
$env:PYTHONPATH='src'; python -m pytest tests\test_research_validation_harness.py tests\test_strategy_validation_registry.py -q
```

Result: PASS - `24 passed in 0.25s`

```powershell
python -m compileall -q src
```

Result: PASS

Note: `compileall` modified tracked `__pycache__` files. Those generated cache
changes were restored so the final diff contains only source/docs/tests.

## Warnings / Limits

- This is not yet the full roadmap. It is the measurement foundation only.
- The new modules are not yet wired into production paper/live runtime.
- The new backtest engine is a first deterministic research backtester, not yet
  a full order-book/tick-level simulator and not yet a walk-forward engine.
- No VPS redeploy was performed because no runtime code path was changed.
- No live safety runtime test was necessary for this isolated package, but the
  next integration step should include the standard VPS `/health` and logs check.

## Recommendation

Proceed to the next roadmap step only by wiring these components into the
validation harness, still research-only. Do not modify live execution, strategy
promotion, or dashboard behavior until the harness can produce reliable reports
from real replay datasets.
