# Cost Profile Parity Non-Regression - 2026-06-14

## Verdict

`PASS_WITH_WARNINGS`

The cost-profile patch is locally validated and may proceed to review. It has
not been deployed.

## What Changed

- Added four named cost profiles and explicit profile metadata.
- Made `research_stress` the default for research runners.
- Preserved `research_legacy` for non-comparable historical results.
- Aligned research edge-gate spread accounting with simulated fills.
- Added cost-profile selection to research CLIs.
- Added observability-only profile metadata to paper summary and runtime edge context.

## What Did Not Change

- No order routing behavior was enabled or relaxed.
- Paper maker/taker fees remain 25/40 bps by default.
- Runtime cost-guard numeric fallbacks remain 40 bps entry, 40 bps exit and 6 bps round-trip slippage fallback.
- No sizing, leverage, risk limit, strategy logic, promotion gate, dashboard API, VPS configuration or persistent trading data changed.
- Live trading remains untouched and no fallback was made permissive.
- No deployment, restart, Kraken order, position close or instance split occurred.

## Tests

Passed:

```text
python -m compileall -q src

$env:PYTHONPATH='src'
python -m pytest tests/research tests/test_v2_cli.py tests/test_paper_trading.py tests/paper/test_paper_trading_engine.py tests/test_signal_handler_async_unit.py tests/test_strategy_router.py -q

210 passed in 2.50s
```

Coverage included canonical profile arithmetic, legacy labeling, CLI selection
and overrides, research report generation, edge-gate parity, paper fee defaults,
paper fills, signal-handler edge calculation and strategy-router safety.

## Warning

Standalone runs of `tests/test_live_blockers.py` and
`tests/test_startup_attestation.py` did not complete within 60 seconds in this
Windows environment and left pytest child processes, which were terminated.
These files were not changed by this patch. Their timeout should be tracked as
an existing test-harness issue; the focused router, paper and signal-handler
safety suites passed.

## Risks Remaining

- `paper_current_maker` is valid only for genuine limit/post-only fills; market-order research remains taker-priced.
- Historical paper databases contain mixed legacy fee eras and must not be compared without filtering/profile annotation.
- Observed adaptive execution costs are still runtime-memory evidence rather than a durable realized-cost series.
- No VPS/runtime verification was performed because deployment and restart were explicitly forbidden.

## Next Step

Review the patch, then rerun the same dataset under `research_stress`,
`paper_current_taker` and `research_legacy` to quantify how much prior research
was optimistic. Deployment remains a separate explicit decision.
