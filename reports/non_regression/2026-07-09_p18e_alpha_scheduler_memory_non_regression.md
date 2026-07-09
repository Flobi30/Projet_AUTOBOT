# P18E Non-Regression - Alpha Scheduler + Memory

Date: 2026-07-09  
Verdict: PASS_WITH_WARNINGS  
Commit: `3e2a9deade93396133dc37f082461c106d14af7e`

## Changed Files

- `docs/research/alpha_knowledge_base.json`
- `docs/research/strategy_templates.json`
- `reports/research/alpha_research_memory.json`
- `src/autobot/v2/cli.py`
- `src/autobot/v2/research/alpha_hypothesis_scheduler.py`
- `tests/research/test_alpha_hypothesis_scheduler.py`

## What Changed

- Added a research-only alpha knowledge base.
- Added bounded strategy templates.
- Added JSON research memory and trial counter.
- Added `alpha-hypothesis-scheduler` CLI.
- Added automatic memory recording for `alpha-hypothesis-runner` CLI runs.
- Added tests for validation, memory counters, data-missing, adapter-missing, rejected configs, no free code generation, no paper/live/promotion, and grid no-go.

## Tests Run

Local:

```bash
python -m compileall -q src
```

Result: PASS

```bash
$env:PYTHONPATH='src'; python -m pytest tests\research\test_alpha_hypothesis_scheduler.py tests\research\test_alpha_hypothesis_runner.py tests\research\test_alpha_hypothesis_lab.py tests\research\test_strategy_risk_mandates.py tests\test_v2_cli.py -q
```

Result: 57 passed

```bash
$env:PYTHONPATH='src'; python -m pytest tests\research\test_archived_grid_defaults.py tests\test_strategy_validation_registry.py -q
```

Result: 19 passed

VPS research container:

```bash
python -m compileall -q src
```

Result: PASS

## VPS Runtime State

- VPS repo fast-forwarded to `3e2a9deade93396133dc37f082461c106d14af7e`
- Main container `autobot-v2`: healthy
- `/health`: healthy
- WebSocket: connected
- Instances: 14
- Main runtime container restart: not performed

Flags:

- `PAPER_TRADING=true`
- `LIVE_TRADING_CONFIRMATION=false`
- `STRATEGY_ROUTER_LIVE_ENABLED=false`
- `COLONY_AUTO_LIVE_PROMOTION=false`
- `ENABLE_INSTANCE_SPLIT_EXECUTOR` unset/false

## VPS Research Runs

Initial scheduler:

- Selected: `long_trend`
- Template: `regime_filtered_trend`
- Status: `RUNNABLE_SMOKE`
- Priority: 130.0

Selected smoke:

- Hypothesis: `long_trend`
- Final status: `REJECT_FAST`
- Trades: 404
- PF net: 0.5992
- Net PnL: -292.18 EUR
- Expectancy: -0.7232 EUR/trade
- No walk-forward launched because fast test failed.

Scheduler after smoke:

- Selected: none
- Runnable hypotheses remaining: none
- `volatility_breakout`: `REJECTED_CURRENT_CONFIG`
- `long_trend`: `REJECTED_CURRENT_CONFIG`
- funding/liquidation: `DATA_MISSING`
- cross-sectional/mean-reversion templates: `ADAPTER_MISSING`

## Safety Confirmation

- No live order.
- No paper capital.
- No promotion.
- No shadow activation.
- No runtime order path touched.
- No paper executor/router integration.
- No UI change.
- No sizing/leverage change.
- No free code generation.
- Grid remains no-go.

## Warnings

- PASS_WITH_WARNINGS because no alpha hypothesis remains runnable with existing adapters after P18E. This is a research outcome, not a runtime failure.
- Next progress requires either new data for currently data-missing families or a small bounded adapter for an existing template.

## Recommendation

Proceed only with research-only P18F: build one bounded adapter for a data-ready template, or improve data collection for a data-missing family. Do not activate shadow, paper capital, or live.
