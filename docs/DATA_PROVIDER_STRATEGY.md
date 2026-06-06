# AUTOBOT Data Provider Strategy

## Objective

AUTOBOT must not decide whether a strategy is viable from runtime `market_price_samples` alone. Those samples are useful for operational diagnostics and paper/runtime replay, but they are not a complete research dataset because they normally lack real volume, bid/ask spread, order-book depth, and long historical coverage.

## Primary Research Source

Use public Kraken OHLCV history first:

- Source: Kraken public REST OHLC endpoint, optionally CCXT later if the dependency is intentionally added.
- Timeframes: `1m`, `5m`, `15m`, `1h`.
- Storage: `data/research/historical/` as CSV and Parquet when local dependencies support Parquet.
- Purpose: multi-month/multi-regime strategy validation, batch replay, walk-forward, and baseline comparison.

No Kraken private key is required for OHLCV collection.

## Runtime Complement

Keep `market_price_samples` as a complementary runtime source:

- useful for comparing research vs official paper decisions;
- useful for detecting what AUTOBOT actually saw;
- useful for paper/live parity diagnostics;
- not sufficient by itself for strategy promotion.

When exported to OHLCV, `market_price_samples` should be marked clearly:

- volume is absent or zero;
- bid/ask is absent unless explicit metadata exists;
- depth is absent unless explicit metadata exists;
- gaps and duplicate timestamps must be reported.

## Cost-Sensitive Data Gap

Grid/scalping-style strategies are highly sensitive to costs. OHLCV close prices alone cannot fully prove execution quality. Before any strategy is considered for official paper promotion, AUTOBOT should also collect or estimate:

- bid/ask spread;
- order-book depth or liquidity bucket;
- stale data events;
- latency assumptions;
- minimum order constraints.

## Why Databento Is Not Priority Now

Databento can be useful for institutional-grade historical market data, but it is not the first bottleneck for AUTOBOT right now:

- AUTOBOT trades Kraken spot crypto, so Kraken public OHLCV is the closest low-friction baseline.
- The immediate weakness is parity between research replay and official paper, not vendor-grade data breadth.
- Adding a paid/complex external provider before fixing cost parity, ledger parity, and validation workflow would increase system complexity.
- Public Kraken OHLCV plus local spread/order-book capture is enough to determine whether current grid/trend/mean-reversion logic has any realistic edge.

Databento can be revisited later if AUTOBOT needs deeper historical order-book or cross-venue data for a specific validated research question.

## Acceptance Before Strategy Promotion

A dataset is usable for research only if:

- OHLC values are valid and chronological;
- gaps are reported and either acceptable or excluded;
- duplicate candles are removed or flagged;
- volume status is explicit;
- bid/ask and depth availability is explicit;
- period coverage is documented per symbol;
- costs are included in every validation run.

A dataset is not sufficient for live readiness unless:

- strategy performance survives costs;
- official paper behavior reconciles with research;
- enough out-of-sample windows are tested;
- no strategy is promoted automatically;
- live execution remains blocked until human approval.
