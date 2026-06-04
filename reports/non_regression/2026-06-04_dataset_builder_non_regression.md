# Non-Regression - Research Dataset Builder - 2026-06-04

## Verdict

`PASS_WITH_WARNINGS`

The change adds a research-only dataset builder that aggregates AUTOBOT
`market_price_samples` into OHLCV bars and writes CSV/optional Parquet-ready
research datasets. It does not alter runtime paper execution, live trading,
strategy routing, risk checks, dashboard APIs, Docker configuration, or
persistent VPS data.

Warning: a smoke run on the fresh VPS snapshot detected many data gaps and
mixed Kraken symbol aliases (`BTCZEUR`, `XBTZEUR`, `XXBTZEUR`, etc.). This is
valuable evidence for the next roadmap step, but it means the exported datasets
should not yet be treated as final research truth without symbol normalization
and gap policy review.

## What Changed

Files modified or added:

- `src/autobot/v2/research/dataset_builder.py`
- `src/autobot/v2/research/market_data_repository.py`
- `src/autobot/v2/research/__init__.py`
- `src/autobot/v2/cli.py`
- `tests/research/test_dataset_builder.py`
- `tests/test_v2_cli.py`
- `docs/research/CLI_WORKFLOWS.md`
- `reports/non_regression/2026-06-04_dataset_builder_non_regression.md`

Logic added:

- New `build-dataset` CLI command.
- Read-only loading from `market_price_samples`.
- OHLCV aggregation for configurable timeframes such as `1m`, `5m`, `15m`.
- Exact duplicate sample removal.
- Same-timestamp price collision counting.
- Data-gap reporting per exported timeframe.
- CSV exports by default; Parquet export is optional and dependency-gated.
- Markdown and JSON dataset quality reports.
- Stable JSON metadata serialization/deserialization for market-data CSV files.

Endpoints/routes touched: none.

Critical runtime modules impacted: none.

## What Did Not Change

- Dashboard: unchanged.
- Paper trading runtime: unchanged.
- Live safety: unchanged.
- Strategy router: unchanged.
- Risk management: unchanged.
- Existing APIs: unchanged.
- Docker/VPS behavior: unchanged.
- Persistent VPS data: unchanged.
- Strategy registry/promotion gates: unchanged.
- Sizing, leverage, order execution, cost guard: unchanged.

## Test Evidence

Focused syntax check:

```powershell
python -m py_compile src\autobot\v2\research\dataset_builder.py src\autobot\v2\research\market_data_repository.py src\autobot\v2\cli.py tests\research\test_dataset_builder.py tests\test_v2_cli.py
```

Result:

- Passed.

Focused dataset/CLI tests:

```powershell
$env:PYTHONPATH='.codex_python_deps;src'
python -m pytest tests\research\test_dataset_builder.py tests\research\test_market_data_repository.py tests\test_v2_cli.py -q
```

Result:

- `18 passed in 0.62s`

Broader research/paper/risk/CLI tests:

```powershell
$env:PYTHONPATH='.codex_python_deps;src'
python3.12 -m pytest tests\research tests\paper tests\risk tests\test_v2_cli.py -q
```

Result:

- `113 passed in 1.63s`

Compile check:

```powershell
python3.12 -m compileall -q src
```

Result:

- Passed.

## VPS Runtime Evidence

Public health check:

```powershell
curl.exe -fsS http://204.168.251.201:8080/health
```

Result:

- `status`: `healthy`
- Orchestrator: `running`
- Websocket: `connected`
- Instances: `14`

No Docker restart was performed. The VPS runtime was not modified.

## Real Snapshot Smoke Run

Command:

```powershell
$env:PYTHONPATH='.codex_python_deps;src'
python -m autobot.v2.cli build-dataset `
  --run-id vps_2026_06_04_dataset_smoke `
  --state-db data\vps_autobot_state_2026-06-04_2026-06-04_121159.db `
  --timeframes 1m,5m,15m `
  --output-dir data\research\vps_2026_06_04_dataset_smoke
```

Result:

- Source samples: `135046`
- Usable samples: `135046`
- Exact duplicates removed: `0`
- Same-timestamp collisions: `0`
- `1m` bars: `135046`, gaps: `22628`, max gap: `6360s`
- `5m` bars: `36097`, gaps: `2349`, max gap: `6600s`
- `15m` bars: `13127`, gaps: `249`, max gap: `6300s`
- Exported under ignored local `data/research/...`

Important data-quality warnings:

- `volume_unavailable_from_market_price_samples`
- `data_gaps_detected`
- Mixed aliases appear in the same dataset family, including `BTCZEUR`,
  `XBTZEUR`, `XXBTZEUR`, `ETHZEUR`, `XETHZEUR`, `XLMZEUR`, `XXLMZEUR`,
  `XRPZEUR`, `XXRPZEUR`, `LTCZEUR`, `XLTCZEUR`.

## Trading Safety Confirmation

- No strategy was promoted.
- No strategy registry mutation was performed.
- No live trading flag was changed.
- No real Kraken order path was modified.
- No fallback permissive was introduced.
- No sizing, leverage, risk, or execution rule was relaxed.
- The command only builds research datasets and reports.

## Remaining Risks

- Symbol canonicalization must be added before treating multi-symbol research
  datasets as final.
- Runtime samples do not contain true volume, so exported OHLCV volume is `0.0`
  and explicitly labelled unavailable.
- The dataset has many gaps; future validation should either filter sparse
  periods, mark them by symbol/timeframe, or fetch longer external OHLCV history.
- This does not solve the separate runtime issue where official paper trades
  stopped after `2026-05-21`.

## Next Action

Proceed to symbol normalization/data-quality policy and then run the standard
matrix from cleaned OHLCV CSVs. In parallel, investigate why runtime remains in
`observe_only` / `router_selected_no_trade` and no fresh official paper trades
reach `trade_ledger`.
