# AUTOBOT Block 1 — Official Kraken Q1 2026 OHLCVT Research Snapshot

Date: 2026-07-26  
Decision: `GO_RESEARCH_DATA_ONLY` — no shadow, paper-capital, promotion, live, order, sizing or leverage change.

## Scope

This run imported a bounded, operator-supplied Q1 2026 archive from Kraken's official
[downloadable OHLCVT archive documentation](https://support.kraken.com/articles/360047124832-downloadable-historical-ohlcvt-open-high-low-close-volume-trades-data).
It is an historical research source only. It does **not** establish data availability
or feature parity with AUTOBOT's runtime.

Two importer defects were found and corrected before the successful import:

- archive market selection now requires an exact explicit Kraken market alias, preventing
  false matches such as `AIXBTEUR`, `TBTCEUR` or `WBTCEUR` being attributed to BTC/EUR;
- the importer now supports Kraken's documented seven-column headerless OHLCVT CSV format
  without relaxing validation for unknown headerless files.

Relevant commits:

- `a12d49d939f79d08dbeb1ed8bdaf12c965bf2cdc` — exact archive-member mapping;
- `fb87c9f3a9e43404052141b2f1ad68c20c4fc1ae` — official headerless OHLCVT adapter.

## Imported archive evidence

| Property | Value |
|---|---|
| Import snapshot | `kraken_ohlcvt_9df5e8e62ed4c5e1` |
| Selected-content fingerprint | `9df5e8e62ed4c5e1bcd5b7b1dd19612b5210e070da718a357f8487dbdd008074` |
| Symbols | BTC/EUR, ETH/EUR |
| Timeframes | 5m, 15m, 1h |
| Period | 2026-01-01 through 2026-03-31 UTC |
| Rows | 73,428 |
| Duplicate rows removed | 0 |
| Observed gaps | 8 |
| Import status | `COMPLETE_WITH_GAPS` |
| Runtime parity | `false` |
| Paper / live / promotion | all `false` |

The individual member hashes, row counts, gaps and source paths are retained in the
runtime-writable manifest:

```text
data/research/manifests/official_q1_2026_btc_eth_kraken_official_ohlcvt_archive.json
```

## Canonical OHLCV snapshot

The imported files were canonicalized in a separate research directory and never merged
into AUTOBOT runtime market data.

| Property | Value |
|---|---|
| Snapshot | `ohlcv_v2_c31f64486accf7a1` |
| Fingerprint | `c31f64486accf7a159a11432593a9b53499b9fb5a010648ec0cfb58b0911074d` |
| Canonical rows | 73,428 |
| Duplicate rows | 0 |
| Quarantined rows | 0 |
| Gaps carried forward | 8 |
| New-data classification | `significant_new_period` |
| Paper / live / promotion | all `false` |

## Feature snapshot and parity checks

The shared versioned feature registry materialized `return_1_bps`, `momentum_3_bps`,
`volatility_20_bps` and `atr_14_bps` from the canonical snapshot in an isolated,
network-disabled container.

| Property | Value |
|---|---|
| Feature snapshot | `features_v2_4bd3c2db66a90d14` |
| Feature fingerprint | `4bd3c2db66a90d1492f288f36ac652e7ea16b6e5cf99df2762c7c6b02f1b42b1` |
| Registry fingerprint | `fd0d6dec7d4fe4fda5764ca43a1bf79c8ea4d9b05c9e20754014f7752931f259` |
| Feature values | 293,712 |
| Ready values | 293,484 |
| Initial lookback waits | 228 |
| Missing values | 0 |
| Deterministic batch/shadow calculation check | `parity_ok=true` on 12,288 sampled rows |
| Material bundle verification | passed, six feature files |
| Runtime parity proven | `false` |

The feature snapshot intentionally carries the blocker
`HISTORICAL_DATA_RUNTIME_PARITY_NOT_PROVEN`. A direct capability scan of the archive
also confirms `spot_ohlcv` remains unavailable for runtime eligibility. Historical
archive data therefore cannot unlock a shadow artifact or cause a strategy retry by
itself.

## Tests and execution isolation

Local non-regression suite after both importer fixes:

```text
python -m pytest tests/research/test_kraken_ohlcvt_archive.py \
  tests/research/test_canonical_ohlcv_store.py \
  tests/research/test_canonical_feature_snapshot.py \
  tests/research/test_data_capability_scanner.py -q
# 42 passed

python -m compileall -q src
git diff --check
```

The VPS archive import and canonicalization ran in disposable containers with:

- no private Kraken API, credentials, orders, router or execution modules;
- read-only root filesystem and `no-new-privileges`;
- dropped Linux capabilities and bounded CPU/RAM/PID budgets;
- only explicitly mounted research input/output directories;
- separate canonical output from runtime data;
- feature materialization with network disabled.

After the code deployments, GitHub, VPS source and Docker image were aligned on
`fb87c9f3a9e43404052141b2f1ad68c20c4fc1ae`. The AUTOBOT container was healthy,
its WebSocket connected and its 14 instances running. Safety flags remained disabled:

```text
LIVE_TRADING_CONFIRMATION=false
STRATEGY_ROUTER_LIVE_ENABLED=false
COLONY_AUTO_LIVE_PROMOTION=false
PAPER_EXECUTION_ADAPTER_ENABLED=false
```

## Limits and next gate

This is a single Q1 2026 historical quarter with eight detected gaps. It is insufficient
to establish multi-regime coverage, a continuous six-month history, runtime/shadow
parity or a material change to any previously rejected strategy. It must not be combined
with later runtime data as if the missing period were continuous.

Next work is therefore an audit of the 24-layer gate evidence and a bounded search for
additional official historical periods. A strategy may be reconsidered only through the
existing manifested experiment protocol after a materially distinct, pre-registered
dataset/thesis condition is met. The valid outcome remains `WAITING_FOR_MORE_DATA` when
that evidence is unavailable.
