# P18G Non-Regression - Generic Cross-Sectional Adapter - 2026-07-09

## Verdict

`PASS_WITH_WARNINGS`

Warning: local research smoke rejected `leader_laggard_momentum` after costs. This is expected and risk-reducing; it does not block deployment because the adapter, scheduler and memory behavior are functioning.

## Files Modified

- `Dockerfile`
- `docs/research/strategy_templates.json`
- `reports/research/alpha_research_memory.json`
- `src/autobot/v2/cli.py`
- `src/autobot/v2/research/alpha_hypothesis_runner.py`
- `src/autobot/v2/research/alpha_hypothesis_scheduler.py`
- `src/autobot/v2/research/generic_cross_sectional_ohlcv_adapter.py`
- `tests/research/test_alpha_hypothesis_runner.py`
- `tests/research/test_alpha_hypothesis_scheduler.py`
- `tests/research/test_generic_cross_sectional_ohlcv_adapter.py`
- `reports/research/p18g_generic_cross_sectional_adapter_2026-07-09.md`
- `reports/research/alpha_hypothesis_runner/p18g_scheduler_local.json`
- `reports/research/alpha_hypothesis_runner/p18g_scheduler_local.md`
- `reports/research/alpha_hypothesis_runner/p18g_cross_momentum_leader_laggard_smoke_local.json`
- `reports/research/alpha_hypothesis_runner/p18g_cross_momentum_leader_laggard_smoke_local.md`

## What Did Not Change

- No UI visible change.
- No live trading flag changed.
- No paper capital enabled.
- No strategy promoted.
- No shadow activation.
- No sizing/leverage change.
- No runtime order path integration.
- Grid remains no-go.

## Tests

```bash
python -m compileall -q src
$env:PYTHONPATH='src'; python -m pytest tests\research\test_generic_cross_sectional_ohlcv_adapter.py tests\research\test_alpha_hypothesis_runner.py tests\research\test_alpha_hypothesis_scheduler.py -q
$env:PYTHONPATH='src'; python -m pytest tests\research tests\test_v2_cli.py -q
```

Results:

- compileall: OK
- targeted tests: `23 passed`
- research/CLI non-regression: `282 passed`

## Research Smoke Evidence

- Scheduler selected `cross_momentum` / `leader_laggard_momentum`.
- Adapter readiness: `generic_cross_sectional_ohlcv_adapter=READY`.
- Smoke final status: `REJECT_FAST`.
- Trade count: `53`.
- PF net: `0.138464`.
- Net PnL EUR: `-147.515495`.
- Expectancy: `-2.783311`.
- Walk-forward was not launched after fast rejection.

## VPS Evidence

- GitHub/local/VPS commit: `2df2c851b4b231ca70f6e9dd7a8fe8a089826f1b`.
- VPS host used: `204.168.251.201`.
- Previous tested host `91.99.232.7` timed out on SSH port 22; `204.168.251.201` was recovered from prior AUTOBOT reports and confirmed with hostname `AUTOBOT`.
- Container `autobot-v2`: running and Docker health `healthy`.
- `/health`: `healthy`, websocket `connected`, instances `14`.
- Flags: `PAPER_TRADING=true`, `LIVE_TRADING_CONFIRMATION=false`, `STRATEGY_ROUTER_LIVE_ENABLED=false`, `COLONY_AUTO_LIVE_PROMOTION=false`.
- Critical/order/live log scan over last 200 lines: `0`.
- VPS scheduler selected `cross_momentum` / `relative_strength_rotation` after the template-specific `leader_laggard_momentum` rejection.
- VPS `relative_strength_rotation` smoke: `REJECT_FAST`, trade_count `42`, PF net `0.482841`, net PnL EUR `-37.949597`, expectancy `-0.903562`.
- Walk-forward was not launched after fast rejection.

## Safety Confirmation

- `paper_capital_allowed=false`
- `live_allowed=false`
- `promotable=false`
- No order path imported or called by the generic adapter.
- Research memory rejection is template-specific: `cross_momentum__leader_laggard_momentum`.

## Next Step

Deploy, rebuild the image because the Dockerfile changed, verify VPS/container alignment, then run the scheduler and only the next selected smoke gate. If the selected smoke fails, record rejection and stop.
