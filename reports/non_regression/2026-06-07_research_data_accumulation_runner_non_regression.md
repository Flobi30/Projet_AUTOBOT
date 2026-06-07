# Non-Regression - Research Data Accumulation Runner - 2026-06-07

Verdict: PASS

## Scope

This change adds a daily, research-only data accumulation workflow. It collects public Kraken OHLCV and public spread/depth snapshots, then derives microstructure and data-readiness reports.

No runtime trading service is started or modified.

## Files Modified

- `config/research_data_collection.yaml`
- `requirements.txt`
- `requirements/runtime.in`
- `requirements/runtime.txt`
- `src/autobot/v2/cli.py`
- `src/autobot/v2/research/daily_data_collection_runner.py`
- `src/autobot/v2/research/data_readiness_dashboard.py`
- `src/autobot/v2/research/microstructure_profile.py`
- `src/autobot/v2/research/spread_depth_recorder.py`
- `tests/research/test_daily_data_collection_runner.py`
- `tests/research/test_data_readiness_dashboard.py`
- `tests/research/test_microstructure_profile.py`
- `tests/test_v2_cli.py`

## What Changed

- Added a reproducible YAML config for daily research data collection.
- Added `collect-research-daily` CLI command.
- Added a runner that orchestrates OHLCV collection, spread/depth recording, manifest writing, Markdown report generation, microstructure profiling, and data-readiness reporting.
- Added microstructure profiling from local spread/depth CSV snapshots.
- Added a research data-readiness dashboard that blocks paper-candidate readiness when bid/ask/depth evidence is missing or history is too short.
- Hardened spread/depth recording to continue after public Kraken errors and report them instead of failing the entire daily run.
- Declared PyYAML explicitly for the YAML config reader.

## What Did Not Change

- Live trading was not enabled.
- Paper trading runtime was not modified.
- Sizing, leverage, risk management and order execution were not changed.
- Strategy router, promotion gate and strategy registry were not changed.
- No strategy was added, optimized, promoted, or duplicated.
- No Docker/VPS runtime restart was performed.
- No persistent trading data was modified.

## Safety Confirmation

- Public endpoints only: enforced by config and implemented via existing public Kraken OHLC/Depth collectors.
- No private keys: runner does not read environment variables or private Kraken credentials.
- No orders: runner imports only research collectors/report builders and cannot create Kraken orders.
- Runtime isolated: no paper/live orchestrator, router, executor or risk-manager path is invoked.
- `live_promotion_allowed` remains `false` in generated daily results and readiness rows.

## Commands Run

```powershell
python -m compileall -q src
```

Result: PASS

```powershell
$env:PYTHONPATH='src'; python -m pytest tests\research\test_daily_data_collection_runner.py tests\research\test_microstructure_profile.py tests\research\test_data_readiness_dashboard.py tests\test_v2_cli.py::test_cli_collect_research_daily_is_research_only -q
```

Result: PASS, `5 passed in 0.32s`

```powershell
$env:PYTHONPATH='src'; python -m pytest tests\research tests\test_v2_cli.py -q
```

Result: PASS, `149 passed in 2.00s`

## Smoke Result

The daily runner was tested with fake public Kraken fetchers:

- `TRXEUR` OHLCV collection succeeded.
- `BADPAIR` OHLCV collection returned a public error and was reported without crashing the global run.
- `TRXEUR` spread/depth collection succeeded.
- `BADPAIR` spread/depth collection returned a public error and the microstructure operation was marked `partial`.
- Manifest, Markdown daily report, microstructure profile and readiness dashboard were generated.
- Environment variables named like Kraken credentials were set in the test and verified not to leak into outputs.

## Limits

- The default config samples spread/depth for 60 minutes (`samples_per_run=60`, `sample_interval_seconds=60`), so it should be scheduled rather than run interactively when a long capture is desired.
- Bid/ask/depth evidence is captured as snapshots, not a full tick-level order-book history.
- Data readiness can only become paper-candidate-ready when enough OHLCV history and microstructure coverage exist.
- No research/paper parity run was launched by this change.

## Daily Command To Schedule

```powershell
$env:PYTHONPATH='src'
python -m autobot.v2.cli collect-research-daily --config config/research_data_collection.yaml --run-id daily_YYYY_MM_DD
```

Use a unique `run-id` per day. This command is research-only and does not require private Kraken keys.

## Recommendation

Proceed to daily accumulation. After several daily runs, use the generated readiness dashboards and microstructure profiles to decide when a longer batch validation is meaningful.
