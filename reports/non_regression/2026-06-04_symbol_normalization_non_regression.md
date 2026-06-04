# Non-Regression - Research Symbol Normalization - 2026-06-04

## Verdict

PASS_WITH_WARNINGS

This change is research-only. It normalizes Kraken symbol aliases for dataset
building and validation reports, without changing paper execution, live trading,
strategy routing, risk management, Docker configuration, or persistent runtime
data.

## Changes

- Added `src/autobot/v2/research/symbol_normalization.py`.
- Extended `MarketDataRepository.load_autobot_state_db(..., canonicalize_symbols=True)`.
- Extended `DatasetBuildConfig` / `DatasetBuildResult` with canonicalization
  fields.
- Extended `python -m autobot.v2.cli build-dataset` with
  `--no-canonical-symbols`.
- Updated research CLI documentation.
- Added tests for Kraken aliases and canonical dataset output.

## What Must Not Have Changed

- Dashboard: not touched.
- Paper trading: not touched.
- Live safety: not touched.
- Strategy router / promotion gate: not touched.
- Risk management / sizing / leverage: not touched.
- Existing APIs: not touched.
- Docker/VPS runtime config: not touched.
- Persistent runtime DB data: read-only during smoke validation.

## Trading Safety

- No strategy can be promoted by this change.
- No Kraken order path is imported or invoked.
- No live trading flag or permission is changed.
- `build-dataset` safety notes still state that no runtime paper/live service is
  started and no live permission is granted.
- The 14 runtime instances remain a health/runtime fact only; they do not bypass
  promotion or validation gates.

## Validation Evidence

Commands:

```powershell
$env:PYTHONPATH='.codex_python_deps;src'
python -m py_compile src\autobot\v2\research\symbol_normalization.py src\autobot\v2\research\dataset_builder.py src\autobot\v2\research\market_data_repository.py src\autobot\v2\cli.py tests\research\test_symbol_normalization.py tests\research\test_dataset_builder.py tests\research\test_market_data_repository.py tests\test_v2_cli.py
python -m compileall -q src
python -m pytest tests\research\test_symbol_normalization.py tests\research\test_dataset_builder.py tests\research\test_market_data_repository.py tests\test_v2_cli.py -q
python -m pytest tests\research tests\paper tests\risk tests\test_v2_cli.py -q
```

Results:

- Targeted research/CLI tests: `22 passed in 0.59s`.
- Broader research/paper/risk/CLI tests: `117 passed in 1.17s`.
- Python compile and compileall: passed.

## VPS Runtime Check

Command:

```powershell
curl.exe -fsS http://204.168.251.201:8080/health
```

Result:

```json
{"status":"healthy","version":"2.0.0","components":{"orchestrator":"running","websocket":"connected","instances":14}}
```

No Docker restart was performed for this research-only change.

## Dataset Smoke

Command:

```powershell
python -m autobot.v2.cli build-dataset --run-id vps_2026_06_04_dataset_canonical_smoke --state-db <latest_vps_state_db> --timeframes 1m,5m,15m --output-dir data/research/vps_2026_06_04_dataset_canonical_smoke
```

Result:

- Raw samples: `135046`.
- Usable samples after exact duplicate removal: `80920`.
- Exact duplicates removed: `54126`.
- Normalized sample count: `25982`.
- Raw aliases normalized: `XBTZEUR`, `XETHZEUR`, `XLTCZEUR`,
  `XXBTZEUR`, `XXLMZEUR`, `XXRPZEUR`.
- Canonical symbol count: `14`.
- 1m bars: `80920`, gaps: `18129`, max gap: `6360s`.
- 5m bars: `24003`, gaps: `2338`, max gap: `6600s`.
- 15m bars: `9089`, gaps: `249`, max gap: `6300s`.
- Warnings: `raw_duplicate_samples_removed`,
  `volume_unavailable_from_market_price_samples`, `symbols_canonicalized`.

## Remaining Risks

- Runtime `market_price_samples` does not include real volume, so OHLCV exports
  still use `volume=0.0`.
- Data gaps remain and must be accounted for by validation runs.
- The alias map covers current observed EUR pairs and common Kraken aliases, but
  future pairs may need explicit mapping if Kraken emits non-obvious names.
- This does not yet add CCXT/historical backfill or a unified strategy
  interface.

## Recommendation

Proceed to the next roadmap step: standardize research dataset loading and then
add the repeatable `validate-strategies` runner using this canonicalized data.
