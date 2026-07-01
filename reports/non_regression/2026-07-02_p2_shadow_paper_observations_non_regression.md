# P2 Shadow Paper Observations Non-Regression - 2026-07-02

## Verdict

PASS_WITH_WARNINGS

P2 adds an explicit `shadow_paper` observation path for closed shadow-lab trades. The path writes attributed observations with `strategy_id` into the post-P0 `trade_ledger`, while keeping them separate from `paper_capital` and non-promotable.

## Files Modified

- `src/autobot/v2/strategy_runtime_policy.py`
- `src/autobot/v2/persistence.py`
- `src/autobot/v2/paper/ledger_loader.py`
- `src/autobot/v2/paper/official_performance.py`
- `src/autobot/v2/paper/shadow_observation_sync.py`
- `src/autobot/v2/cli.py`
- `tests/paper/test_shadow_observation_sync.py`
- `tests/paper/test_official_performance.py`
- `tests/test_v2_cli.py`

## Trading Safety

- Live trading was not enabled.
- No Kraken order path was added or invoked.
- No strategy was promoted.
- No sizing, leverage, risk, router, or live flag was changed.
- `paper_capital` writes require explicit promotion-gate attestation.
- `shadow_paper` observations are reportable, but excluded from paper-capital promotion evidence.
- Grid aliases remain blocked by `strategy_runtime_policy`.

## Behavior

- `shadow_paper` can write observations for:
  - `trend_momentum`
  - `mean_reversion`
  - `high_conviction_swing`
  - `opportunity_scoring`
- The first sync implementation reads closed trade sources for:
  - `trend_momentum` via `trend_shadow_trades`
  - `mean_reversion` via `mean_reversion_shadow_trades`
- `high_conviction_swing` and `opportunity_scoring` are reported as observation-capable but currently have no closed-shadow-trade source wired to this sync.
- `paper-performance-summary` now separates:
  - `shadow_paper`
  - `paper_capital`
  - legacy/non-reportable rows

## Commands Executed

```powershell
python -m py_compile src/autobot/v2/paper/shadow_observation_sync.py src/autobot/v2/paper/official_performance.py src/autobot/v2/cli.py src/autobot/v2/persistence.py src/autobot/v2/strategy_runtime_policy.py
python -m compileall -q src
$env:PYTHONPATH='src'; python -m pytest tests\paper\test_shadow_observation_sync.py tests\paper\test_official_performance.py -q
$env:PYTHONPATH='src'; python -m pytest tests\paper\test_shadow_observation_sync.py tests\paper\test_official_performance.py tests\paper\test_paper_ledger_loader.py tests\test_pf_phase2.py tests\test_strategy_validation_registry.py tests\test_v2_cli.py::test_cli_paper_performance_summary_reads_official_post_p0_ledger -q
$env:PYTHONPATH='src'; python -m pytest tests\paper tests\test_v2_cli.py tests\test_pf_phase2.py tests\test_strategy_validation_registry.py -q
```

## Test Results

- Targeted shadow/official performance: `7 passed`
- Ledger/CLI/governance targeted set: `42 passed`
- Wider paper/CLI/governance set: `74 passed`
- `compileall`: PASS

## Risks Remaining

- High Conviction and Opportunity Scoring still need a closed-observation source before they can generate `shadow_paper` rows through this sync command.
- Existing historical rows without `execution_mode` remain legacy/non-reportable for P1/P2 metrics.
- `shadow_paper` observations are not evidence for promotion; candidate status still requires validated `paper_capital` evidence and human review.

## Next Operational Command

```bash
PYTHONPATH=/app/src python -m autobot.v2.cli shadow-paper-observations \
  --state-db /app/data/autobot_state.db \
  --registry-path /app/docs/research/strategy_hypotheses.json \
  --trend-shadow-db /app/data/trend_shadow_lab.db \
  --mean-reversion-shadow-db /app/data/mean_reversion_shadow_lab.db \
  --run-id p2_shadow_observations_20260702 \
  --output-dir /app/reports/paper/shadow_observations
```

## Deployment Status

Local validation completed. GitHub/VPS synchronization is performed after this report is committed.
