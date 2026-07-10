# P18J Kraken Futures Derivatives Collector Non-Regression

Date: 2026-07-10  
Code commit: `bd06480`

## Scope

P18J adds a research-only Kraken Futures derivatives collector and extends the data capability scanner. It does not test a strategy and does not connect to runtime trading.

## Modified Files

- `src/autobot/v2/research/kraken_futures_derivatives_collector.py`
- `src/autobot/v2/research/data_capability_scanner.py`
- `src/autobot/v2/cli.py`
- `tests/research/test_kraken_futures_derivatives_collector.py`
- `tests/research/test_data_capability_scanner.py`
- `reports/research/kraken_futures_derivatives/p18j_local_smoke_20260710.md`
- `reports/research/p18j_post_scan/p18j_local_post_derivatives_scan_20260710.json`
- `reports/research/p18j_post_scan/p18j_local_post_derivatives_scan_20260710.md`

## Commands Run

```powershell
$env:PYTHONPATH='src'
python -m compileall -q src
python -m pytest tests\research\test_kraken_futures_derivatives_collector.py tests\research\test_data_capability_scanner.py tests\research\test_alpha_hypothesis_scheduler.py tests\research\test_alpha_hypothesis_runner.py tests\research\test_strategy_risk_mandates.py tests\test_v2_cli.py -q
python -m autobot.v2.cli collect-kraken-futures-derivatives --run-id p18j_local_smoke_20260710 --assets BTC,ETH --max-symbols 2 --max-candles 5 --raw-dir data/research/raw/kraken_futures --canonical-dir data/research/canonical/derivatives --manifest-dir data/research/manifests --report-dir reports/research/kraken_futures_derivatives --timeout-seconds 20
python -m autobot.v2.cli data-capability-scan --run-id p18j_local_post_derivatives_scan_20260710 --data-roots data/research,reports/research --state-db data/autobot_state.db --output-dir reports/research/p18j_post_scan
```

## Results

- compileall: OK
- pytest targeted: `71 passed`
- local Kraken Futures smoke: OK
- local scanner post-derivatives: OK

## Data Readiness

- historical funding: ready for BTC/ETH smoke
- mark candles: ready in bounded smoke sample
- trade candles: ready in bounded smoke sample
- current open interest: ready
- historical open interest: not ready
- current basis: ready, same-quote mark/index only
- basis history: not ready
- liquidation events: missing

`funding_basis` remains `WAITING_FOR_MORE_DATA`.  
`liquidation_cascade` remains `DATA_MISSING`.

## Safety Confirmation

- No live trading enabled.
- No paper capital enabled.
- No strategy promotion.
- No shadow activation.
- No order endpoint called.
- No private API or key read.
- No UI change.
- No sizing/leverage change.
- No runtime order path touched.
- Grid remains no-go.

## Remaining Risks

- Current open interest and current basis are snapshots, not history.
- Funding-basis must remain blocked until basis history is accumulated and validated.
- Liquidation-cascade remains unavailable without real liquidation event data.
- VPS smoke/deployment status is pending and must be appended after deployment.
