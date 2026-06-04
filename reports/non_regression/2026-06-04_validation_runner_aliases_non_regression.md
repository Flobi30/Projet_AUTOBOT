# Non-Regression - Validation Runner Symbol Aliases - 2026-06-04

## Verdict

PASS_WITH_WARNINGS

The validation runner now canonicalizes Kraken aliases when loading
`autobot_state_db` market samples. This keeps direct SQLite validations aligned
with the canonical research dataset builder.

## Changes

- `src/autobot/v2/research/validation_runner.py`
  - `load_bars_for_validation()` now passes `canonicalize_symbols=True` for
    `autobot_state_db`.
- `tests/research/test_validation_runner.py`
  - Added a regression test proving `BTCZEUR` loads `XXBTZEUR` and `XBTZEUR`
    rows as canonical `BTCZEUR`.

## What Must Not Have Changed

- Dashboard: not touched.
- Paper trading: not touched.
- Live trading: not touched.
- Strategy router / promotion gate: not touched.
- Risk management / sizing / leverage: not touched.
- Docker/VPS configuration: not touched.
- Runtime DB contents: read-only.

## Trading Safety

- No Kraken order path is invoked.
- No strategy registry mutation is performed.
- No live trading permission is granted.
- This change only affects research validation data loading.

## Validation Evidence

Commands:

```powershell
$env:PYTHONPATH='.codex_python_deps;src'
python -m py_compile src\autobot\v2\research\validation_runner.py tests\research\test_validation_runner.py
python -m pytest tests\research\test_validation_runner.py tests\research\test_validation_matrix.py tests\research\test_symbol_normalization.py tests\research\test_market_data_repository.py tests\research\test_dataset_builder.py tests\test_v2_cli.py -q
python -m pytest tests\research tests\paper tests\risk tests\test_v2_cli.py -q
python -m compileall -q src
```

Results:

- Targeted validation tests: `30 passed in 0.69s`.
- Broader research/paper/risk/CLI tests: `118 passed in 0.98s`.
- Compile checks: passed.

## VPS Runtime Check

Command:

```powershell
curl.exe -fsS http://204.168.251.201:8080/health
```

Result:

```json
{"status":"healthy","version":"2.0.0","components":{"orchestrator":"running","websocket":"connected","instances":14}}
```

## Snapshot Smoke

Read-only smoke on the latest local VPS state DB snapshot:

```json
{
  "bar_count": 28455,
  "symbols": ["BTCZEUR"],
  "raw_symbols": ["XBTZEUR", "XXBTZEUR"]
}
```

## Remaining Risks

- This does not add external historical backfill.
- This does not solve runtime data gaps or missing volume.
- Alias coverage should be extended if future Kraken symbols appear outside the
  current map.

## Recommendation

Proceed to a repeatable standard validation runner that builds canonical
datasets and launches the standard matrix/report bundle in one command.
