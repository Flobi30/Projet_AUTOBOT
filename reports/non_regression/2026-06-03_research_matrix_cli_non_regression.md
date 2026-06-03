# Non-Regression - Research Matrix CLI - 2026-06-03

Verdict: PASS

## Scope

This change extends the unified AUTOBOT V2 CLI with a `matrix` command.

The command wraps the existing research-only validation matrix and can optionally
write the already available diagnostic reports:

- registry recommendations;
- loss attribution;
- setup quality;
- strategy/regime report;
- strategy/regime baselines;
- strategy/regime walk-forward report;
- strategy scorecard.

## Files Changed

- `src/autobot/v2/cli.py`
  - Adds `matrix` as a first-class subcommand.
  - Reuses `MatrixRunConfig` and `run_validation_matrix`.
  - Reuses existing report writers instead of duplicating validation logic.
  - Emits explicit safety notes in JSON output.
  - Does not mutate `docs/research/strategy_hypotheses.json`.
  - Does not start runtime services or submit orders.

- `tests/test_v2_cli.py`
  - Adds coverage for `cli.main(["matrix", ...])`.
  - Verifies a one-symbol matrix run succeeds.
  - Verifies optional loss attribution and scorecard artifacts are written.
  - Verifies scorecard live promotion remains blocked.
  - Verifies registry mutation is explicitly not performed.

## What Must Not Have Changed

- Dashboard: unchanged.
- Runtime paper executor: unchanged.
- Kraken/live execution: unchanged.
- Strategy router: unchanged.
- Risk sizing/risk thresholds: unchanged.
- Existing APIs: unchanged.
- Docker/VPS behavior: unchanged.
- Persistent runtime data: unchanged.

## Trading Safety

- No live trading flag was changed.
- No CLI command can submit a real Kraken order.
- `matrix` is research-only and calls only validation/reporting modules.
- Registry recommendations are written as reports only; the strategy registry is
  not mutated by this command.
- Scorecard output preserves `live_promotion_allowed=false`.
- No sizing, leverage, cost guard, execution, or risk threshold behavior was
  changed.

## Validation

Commands executed:

```powershell
& 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m py_compile src\autobot\v2\cli.py tests\test_v2_cli.py
```

Result: PASS

```powershell
$env:PYTHONPATH='.codex_python_deps;src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\test_v2_cli.py -q
```

Result: `7 passed in 0.25s`

```powershell
$env:PYTHONPATH='.codex_python_deps;src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\research tests\risk tests\paper tests\test_v2_cli.py -q
```

Result: `103 passed in 0.88s`

```powershell
& 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m compileall -q src
```

Result: PASS

## Runtime / VPS

No VPS restart was performed because this is an isolated research CLI addition.
It does not alter runtime services, Docker configuration, dashboard APIs, paper
execution, live execution, or persisted databases.

## Risks Remaining

- The unified CLI now exposes the matrix runner, but it does not yet provide a
  single preset for the full VPS top-14 validation workflow.
- The matrix command relies on the existing matrix/report modules for strategy
  behavior and evidence quality; it does not improve strategy expectancy by
  itself.
- Full production runtime health should still be checked after any future deploy
  or runtime-facing change.

## Recommendation

Proceed to the next roadmap step: add a documented preset or automation wrapper
for the standard AUTOBOT research workflow so the same audit matrix can be run
consistently from fresh VPS paper/state data.
