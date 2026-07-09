# Non-Regression - P18F Memory Backfill + Adapter Backlog

Date: 2026-07-09  
Verdict: PASS

## What Changed

- Added conservative historical backfill for `reports/research/alpha_research_memory.json`.
- Added historical metrics/source fields to research memory records.
- Added adapter backlog ranking to `alpha-hypothesis-scheduler`.
- Added clear proposed adapter ids such as `leader_laggard_momentum_adapter`.
- Added tests for memory idempotence, rejected hypothesis blocking, adapter backlog ranking, and grid no-go.

## What Did Not Change

- No live trading.
- No paper capital.
- No strategy promotion.
- No runtime order path.
- No paper executor/router integration.
- No UI.
- No sizing/leverage/risk runtime change.
- Grid remains archived/no-go.

## Commands And Results

```bash
python -m compileall -q src
```

Result: PASS.

```bash
$env:PYTHONPATH='src'; python -m pytest tests\research\test_alpha_hypothesis_scheduler.py -q
```

Result: 12 passed.

```bash
$env:PYTHONPATH='src'; python -m pytest tests\research\test_alpha_hypothesis_scheduler.py tests\test_v2_cli.py -q
```

Result: 39 passed.

```bash
$env:PYTHONPATH='src'; python -m pytest tests\research\test_alpha_hypothesis_scheduler.py tests\test_v2_cli.py tests\research\test_archived_grid_defaults.py tests\test_grid_health_gate.py tests\test_grid_setup_optimizer_gate.py tests\test_strategy_validation_registry.py tests\test_strategy_governance.py -q
```

Result: 69 passed.

## Scheduler Evidence

Run:

```bash
python -m autobot.v2.cli alpha-hypothesis-scheduler --state-db data/autobot_state.db --data-paths data/research/daily/ohlcv --knowledge-base docs/research/alpha_knowledge_base.json --templates docs/research/strategy_templates.json --hypotheses docs/research/alpha_hypotheses.json --memory-path reports/research/alpha_research_memory.json --output-dir reports/research/alpha_hypothesis_runner --run-id p18f_scheduler_after_memory_backfill --max-variants 5 --max-symbols 6 --max-runtime-seconds 300
```

Result:

- Selected hypothesis: none.
- `volatility_breakout`: `REJECTED_CURRENT_CONFIG`, priority 0.
- `long_trend`: `REJECTED_CURRENT_CONFIG`, priority 0.
- Top missing adapter: `leader_laggard_momentum_adapter`.
- Memory records: 10.
- Missing source reports: 0.

## Trading Safety

The changed code is limited to research scheduler/memory/CLI. It does not import or call Kraken order paths, paper executor routing, sizing, live flags, or dashboard runtime behavior.

Confirmed by tests:

- rejected hypotheses are not scheduled as fresh candidates;
- grid remains no-go;
- data-missing adapters do not outrank data-ready adapters;
- memory records remain `paper_capital_allowed=false`, `live_allowed=false`, `promotable=false`.

## Residual Risks

- Adapter backlog priority is heuristic. It is bounded and research-only, but it should remain advisory until P18G implements one adapter and validates it.
- Local OHLCV sample is shorter than the latest VPS dataset; the P18F scheduler should be rerun on VPS after deployment for the authoritative report.

## Next Action

Proceed to P18G only after GitHub/VPS/container are synchronized and the VPS scheduler confirms the same top adapter recommendation.
