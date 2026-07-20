# AUTOBOT Block 1 — Official Kraken OHLCVT Archive Import

Decision: `GO` for the research-only importer. The imported archive data remains ineligible for runtime/shadow parity, paper capital, promotion, live trading, or any order path.

## Scope

Implementation commit: `613876883959c500fd412b01c09ff6a9be9fb7a0`.

Kraken's REST OHLC endpoint is bounded. Kraken also publishes official downloadable OHLCVT archives containing completed candles from market inception, plus quarterly updates. This change adds a controlled, operator-supplied archive import path rather than relying on a large or unreliable REST backfill.

- Official provenance: [Kraken downloadable OHLCVT data](https://support.kraken.com/articles/360047124832-downloadable-historical-ohlcvt-open-high-low-close-volume-trades-data)
- CLI: `python -m autobot.v2.cli import-kraken-ohlcvt-archive --run-id <id> --archive-path <zip> --symbols <pairs> --timeframes <frames>`
- Supported bounded timeframes: `1m`, `5m`, `15m`, `1h`, `4h`, `1d`.

## Safety and data contract

- The importer accepts an explicit local ZIP archive only; it does not use keys, private endpoints, execution services, or router modules.
- It retains exact selected raw CSV members plus member hashes and ZIP CRC evidence.
- It streams selected members in 1 MiB chunks, enforces archive/selected-byte budgets, and enforces a configurable per-member row ceiling.
- It writes `event_time`, `available_time`, `ingestion_time`, explicit Kraken base/quote mapping and `HISTORICAL_ARCHIVE_AVAILABLE_AT_INGESTION` provenance.
- Canonicalization preserves that provenance. Feature manifests therefore set `runtime_parity_proven=false` and emit `HISTORICAL_DATA_RUNTIME_PARITY_NOT_PROVEN` for archive rows.
- The generic runtime OHLCV capability scanner excludes archive-import rows. Historical archive evidence cannot silently make the runtime feed look ready.

## Validation

Commands run locally:

```text
python -m py_compile src/autobot/v2/research/kraken_ohlcvt_archive.py src/autobot/v2/research/canonical_feature_snapshot.py src/autobot/v2/research/canonical_ohlcv_store.py src/autobot/v2/research/data_capability_scanner.py src/autobot/v2/cli.py
python -m pytest tests/research/test_kraken_ohlcvt_archive.py tests/research/test_canonical_feature_snapshot.py tests/research/test_canonical_ohlcv_store.py tests/research/test_data_capability_scanner.py tests/research/test_historical_data_collector.py tests/test_v2_cli.py -q
python -m compileall -q src
python -m pytest -q
git diff --check
```

Results:

- Targeted boundary suite: `83 passed`.
- Full suite: `1723 passed, 6 skipped`.
- Compilation and diff checks: passed.
- Secret scan of changed paths: passed.

## Current operational state

At the time of implementation, the official full archive's Google Drive mirror returned a documented quota-exceeded response. No archive was downloaded, no VPS disk was consumed by the archive, and no synthetic substitute was used.

The importer is ready for a bounded selected-pair import when the official archive is accessible or supplied locally. That import remains a batch-research input only; forward capture and the existing parity gates remain required before shadow review.

## Residual risks

- Complete archives can be large, and operator selection of symbols/timeframes must remain bounded.
- Kraken archive rows represent completed candles, but archive retrieval itself is historical; it cannot demonstrate what the runtime observed at the original decision time.
- Missing candles are reported by quality checks and cannot be silently filled.
- No alpha is validated by this work. `PAPER_TRADING`, live flags, promotion flags, sizing, leverage and the grid no-go policy remain unchanged.
