# Non-Regression - Validation CSV Symbol Filter - 2026-06-04

## Verdict

PASS_WITH_WARNINGS

The validation runner now filters multi-symbol CSV inputs to the requested
symbol and canonicalizes matching aliases. This prevents a matrix cell for one
symbol from accidentally replaying other markets.

## Changes

- `src/autobot/v2/research/validation_runner.py`
  - CSV validation loads all bars, filters them to the requested canonical
    symbol, canonicalizes matching aliases, and re-sorts chronologically.
- `tests/research/test_validation_runner.py`
  - Added a regression test for a multi-symbol CSV containing `TRXEUR`,
    `XXBTZEUR`, and `BTCZEUR`.

## What Must Not Have Changed

- Dashboard: not touched.
- Paper trading: not touched.
- Live trading: not touched.
- Strategy router / promotion gate: not touched.
- Risk management / sizing / leverage: not touched.
- Docker/VPS configuration: not touched.
- Persistent runtime data: not touched.

## Trading Safety

- No execution path is invoked.
- No Kraken order can be submitted by this change.
- No strategy registry mutation is performed.
- No live trading permission is granted.

## Validation Evidence

Commands:

```powershell
$env:PYTHONPATH='.codex_python_deps;src'
python -m py_compile src\autobot\v2\research\validation_runner.py tests\research\test_validation_runner.py
python -m pytest tests\research\test_validation_runner.py tests\research\test_validation_matrix.py tests\test_v2_cli.py -q
python -m pytest tests\research tests\paper tests\risk tests\test_v2_cli.py -q
python -m compileall -q src
```

Results:

- Targeted runner/matrix/CLI tests: `20 passed in 0.51s`.
- Broader research/paper/risk/CLI tests: `119 passed in 0.98s`.
- Compile checks: passed.

## Smoke Evidence

Read-only smoke on the canonicalized 1m VPS research CSV:

```json
{
  "bar_count": 9485,
  "symbols": ["BTCZEUR"],
  "start": "2026-05-28T09:49:00+00:00",
  "end": "2026-06-04T09:53:00+00:00"
}
```

## VPS Runtime Check

Command:

```powershell
curl.exe -fsS http://204.168.251.201:8080/health
```

Result:

```json
{"status":"healthy","version":"2.0.0","components":{"orchestrator":"running","websocket":"connected","instances":14}}
```

## Remaining Risks

- CSV rows from external sources still need quality validation before trusting
  results.
- This does not add a one-command full standard workflow yet.
- Data gaps and missing real volume remain visible dataset warnings.

## Recommendation

Proceed to a single standard validation workflow command that builds canonical
datasets and launches the standard matrix/report bundle in a repeatable way.
