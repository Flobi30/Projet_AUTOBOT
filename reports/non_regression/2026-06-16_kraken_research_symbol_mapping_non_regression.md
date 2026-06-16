# Kraken Research Symbol Mapping Non-Regression - 2026-06-16

Verdict: `PASS`

## Scope

Research-only fix for Kraken public symbol resolution used by:

- OHLCV collection
- spread/depth collection
- daily research collection runner
- research CLI `collect-history`

No trading runtime, no paper execution, no live execution, no sizing, no risk, no strategy logic, and no promotion gate behavior were modified.

## Active AUTOBOT pairs detected

Detection path for this workspace run:

1. `TRADING_PAIRS` / `TRADING_SYMBOL` environment if present
2. fallback central AUTOBOT active universe

Runtime env was empty locally, so the fallback active universe was used:

- `BTCZEUR`
- `ETHZEUR`
- `SOLEUR`
- `LTCZEUR`
- `XLMZEUR`
- `XRPZEUR`
- `TRXEUR`
- `ADAEUR`
- `LINKEUR`
- `DOTEUR`
- `BCHEUR`
- `ATOMEUR`
- `AVAXEUR`
- `AAVEEUR`

## Canonical Kraken mapping

| AUTOBOT symbol | Kraken OHLCV / public REST pair | Runtime symbol | Useful aliases |
| --- | --- | --- | --- |
| `BTCZEUR` | `XXBTZEUR` | `XXBTZEUR` | `BTCZEUR`, `BTCEUR`, `XBTEUR`, `XBT/EUR` |
| `ETHZEUR` | `XETHZEUR` | `XETHZEUR` | `ETHZEUR`, `ETHEUR`, `ETH/EUR` |
| `SOLEUR` | `SOLEUR` | `SOLEUR` | `SOLEUR`, `SOLZEUR`, `SOL/EUR` |
| `LTCZEUR` | `XLTCZEUR` | `XLTCZEUR` | `LTCZEUR`, `LTCEUR`, `LTC/EUR` |
| `XLMZEUR` | `XXLMZEUR` | `XXLMZEUR` | `XLMZEUR`, `XLMEUR`, `XLM/EUR` |
| `XRPZEUR` | `XXRPZEUR` | `XXRPZEUR` | `XRPZEUR`, `XRPEUR`, `XRP/EUR` |
| `TRXEUR` | `TRXEUR` | `TRXEUR` | `TRXEUR`, `TRXZEUR`, `TRX/EUR` |
| `ADAEUR` | `ADAEUR` | `ADAEUR` | `ADAEUR`, `ADAZEUR`, `ADA/EUR` |
| `LINKEUR` | `LINKEUR` | `LINKEUR` | `LINKEUR`, `LINKZEUR`, `LINK/EUR` |
| `DOTEUR` | `DOTEUR` | `DOTEUR` | `DOTEUR`, `DOTZEUR`, `DOT/EUR` |
| `BCHEUR` | `BCHEUR` | `BCHEUR` | `BCHEUR`, `BCHZEUR`, `BCH/EUR` |
| `ATOMEUR` | `ATOMEUR` | `ATOMEUR` | `ATOMEUR`, `ATOMZEUR`, `ATOM/EUR` |
| `AVAXEUR` | `AVAXEUR` | `AVAXEUR` | `AVAXEUR`, `AVAXZEUR`, `AVAX/EUR` |
| `AAVEEUR` | `AAVEEUR` | `AAVEEUR` | `AAVEEUR`, `AAVEZEUR`, `AAVE/EUR` |

Source of truth: Kraken public `AssetPairs` REST endpoint.

## What changed

### New

- `src/autobot/v2/research/kraken_symbol_mapping.py`
  - central public Kraken pair registry
  - active AUTOBOT symbol detection
  - preflight validation
  - alias-aware resolution

### Updated

- `src/autobot/v2/research/historical_data_collector.py`
  - preflights symbols before collection
  - uses Kraken-resolved public pair instead of raw AUTOBOT symbol
  - writes `kraken_ohlcv_symbol` and `runtime_symbol` into manifests/reports

- `src/autobot/v2/research/spread_depth_recorder.py`
  - same central mapping / preflight behavior

- `src/autobot/v2/research/daily_data_collection_runner.py`
  - optional runtime-active symbol merge
  - shared preflight once per run
  - collector + depth recorder reuse the same resolved mapping

- `src/autobot/v2/cli.py`
  - `collect-history` can now omit `--symbols` and use detected active AUTOBOT pairs
  - top-14 preset now comes from the same central source

- `config/research_data_collection.yaml`
  - `include_runtime_active_symbols: true`

## Extensibility behavior

The system is no longer limited to a hardcoded 14-pair fix.

If new pairs are added later:

1. they are detected from `TRADING_PAIRS` / `TRADING_SYMBOL` when `include_runtime_active_symbols: true`;
2. Kraken public preflight runs before collection;
3. if Kraken mapping exists, collection proceeds automatically;
4. if Kraken mapping is missing, the run fails clearly with:
   - `Kraken public symbol mapping missing for active symbols: ...`

Unknown pairs are no longer ignored silently.

## Commands run

### Compile

```powershell
python -m compileall -q src
```

Result: `PASS`

### Tests

```powershell
$env:PYTHONPATH='src'; python -m pytest tests\research\test_kraken_symbol_mapping.py tests\research\test_historical_data_collector.py tests\research\test_historical_data_collector_long_range.py tests\research\test_spread_depth_recorder.py tests\research\test_daily_data_collection_runner.py tests\test_v2_cli.py -q
```

Result: `40 passed`

```powershell
$env:PYTHONPATH='src'; python -m pytest tests\research tests\test_v2_cli.py -q
```

Result: `173 passed`

## Short read-only collection smoke

### OHLCV

```powershell
$env:PYTHONPATH='src'; python -m autobot.v2.cli collect-history --run-id kraken_active_pairs_smoke_2026_06_16 --timeframes 5m --output-dir data/research/historical/kraken_active_pairs_smoke_2026_06_16 --max-pages 1 --no-parquet
```

Result:

- `14/14` active pairs collected successfully
- no `Unknown asset pair` error
- output manifest:
  - `data/research/historical/kraken_active_pairs_smoke_2026_06_16/kraken_active_pairs_smoke_2026_06_16_manifest.json`

### Spread / depth

```powershell
$env:PYTHONPATH='src'; python - <<'PY'
from pathlib import Path
from autobot.v2.research.kraken_symbol_mapping import detect_active_autobot_symbols
from autobot.v2.research.spread_depth_recorder import SpreadDepthRecorderConfig, record_spread_depth

result = record_spread_depth(
    SpreadDepthRecorderConfig(
        run_id='kraken_active_pairs_depth_smoke_2026_06_16',
        symbols=detect_active_autobot_symbols(),
        output_dir=Path('data/research/microstructure/kraken_active_pairs_depth_smoke_2026_06_16'),
        depth_count=1,
        samples=1,
        sleep_seconds=0.0,
        export_csv=True,
        continue_on_error=False,
    )
)
print({'snapshots': len(result.snapshots), 'errors': len(result.errors)})
PY
```

Result:

- `14` snapshots
- `0` errors
- no `Unknown asset pair` error

## Risks / limits

- This fixes public Kraken pair resolution for research collection only.
- It does not change strategy quality, paper execution, or live safety.
- Readiness remains `not_ready_for_cost_sensitive_intraday` because bid/ask/depth history is still limited or absent in OHLCV files.
- Existing unrelated untracked `reports/` artifacts and local `__pycache__` changes were not touched.

## Live / trading safety

Confirmed unchanged:

- no Kraken private endpoint required
- no API key read by this mapping logic
- no paper/live orders created
- no strategy promoted
- no risk/sizing change
- no live flag change
