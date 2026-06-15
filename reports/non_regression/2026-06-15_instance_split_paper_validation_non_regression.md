# Instance Split Paper Validation Non-Regression - 2026-06-15

## Verdict

**PASS**

The duplication path is now fail-closed and remains disabled by default. The
isolated paper-only mechanics harness passed without starting AUTOBOT runtime,
accessing Kraken, or creating any order.

## Files changed

- `src/autobot/v2/orchestrator_async.py`
  - wires the runtime spin-off path to `InstanceSplitPolicy`;
  - exits immediately while `ENABLE_INSTANCE_SPLIT_EXECUTOR=false`;
  - requires persisted lifetime lineage and complete validation evidence when enabled;
  - forces `paper_mode` from runtime and `live_promotion_allowed=false`.
- `src/autobot/v2/instance_split_policy.py`
  - requires `paper_validated`; candidate and shadow statuses are insufficient.
- `src/autobot/v2/persistence.py`
  - preserves lineage during orphan cleanup;
  - fixes the reversed parent/child column binding in lineage inserts.
  - exposes a fail-closed durable parent split count.
- `src/autobot/v2/research/instance_split_validation_harness.py`
  - adds an isolated mechanics-only split simulation;
  - validates capital conservation, child state isolation, durable lineage, and lifetime uniqueness.
- `src/autobot/v2/cli.py`
  - adds the research-only `split-validation` command.
- `.env.example`
  - documents `ENABLE_INSTANCE_SPLIT_EXECUTOR=false` explicitly.
- Tests updated/added for policy, runtime gating, persistence, harness, and CLI.

## What did not change

- No strategy logic changed.
- No paper fill, sizing, risk, leverage, or order-routing behavior changed.
- No live flag or Kraken integration changed.
- No strategy was promoted.
- No runtime instance was created.
- No duplication executor was enabled.
- No dashboard or API contract changed.

## Mechanical validation result

Run: `instance_split_mechanics_2026_06_15`

- first validated paper split: PASS;
- capital conserved at transfer: PASS;
- child capital changes independently from parent: PASS;
- lineage persisted in isolated SQLite: PASS;
- second split by the same parent blocked after reload: PASS;
- live promotion disabled: PASS;
- order path absent: PASS.

The synthetic child return series validates state isolation only. It is not a
profitability test and cannot qualify a strategy for paper or live execution.

## Commands and results

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_instance_split_policy.py tests/test_instance_split_planner.py tests/test_p0_spin_off_and_market_selector.py tests/test_persistence_lineage_retention.py tests/research/test_instance_split_validation_harness.py -q
```

Result: `15 passed`.

```powershell
python -m compileall -q src
```

Result: PASS.

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/research tests/test_v2_cli.py tests/test_instance_split_policy.py tests/test_instance_split_planner.py tests/test_p0_spin_off_and_market_selector.py tests/test_persistence_lineage_retention.py -q
```

Result: `183 passed`.

## Trading safety

- `ENABLE_INSTANCE_SPLIT_EXECUTOR` remains OFF by default.
- Runtime returns before database evaluation while the flag is OFF.
- Live mode is rejected even if the executor flag is enabled.
- Only `paper_validated` strategies can satisfy the split policy.
- Positive net paper PnL, PF >= 1.25, at least 100 trades, at least 7 validation days,
  drawdown <= 12%, scorecard >= 75, sufficient available capital, and no blocking
  failure mode are still required.
- One parent can create at most one child over its persisted lifetime.
- If lineage cannot be verified, duplication is blocked.

## Remaining staged validation

Before any production-like paper activation:

1. A real strategy must first reach `paper_validated` with official evidence.
2. Build the runtime evidence bridge from the official paper ledger and scorecard.
3. Run duplication in a dedicated paper sandbox with a disposable parent.
4. Observe child startup, market subscription, ledger isolation, restart recovery,
   resource usage, and parent/child capital accounting for multiple days.
5. Keep live disabled and require a separate human review afterward.

The project may proceed to commit/deploy this safety patch. It must not enable
the duplication executor yet.
