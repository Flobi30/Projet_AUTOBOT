# AUTOBOT Block 5 — Official performance source boundary — 2026-07-16

## Decision

GO.  Official performance metrics now fail closed when the post-P0 trade ledger
is unavailable.  No UI redesign or execution behavior was changed.

## Finding

The dashboard performance helper retained an old fallback that could expose
the legacy `trades` table as the current paper-performance source when the
official `trade_ledger` table was missing.  Those legacy rows can lack
strategy attribution and complete cost evidence, so they must not inform PnL,
profit factor, allocation, promotion or reconciliation decisions.

## Change

- `trade_ledger` remains the sole official performance source.
- Legacy `trades` rows remain read-only audit evidence under `legacy`.
- If no official ledger exists, the response is
  `legacy_only_excluded`, `available=false`, `source=none`, with zero official
  metrics.

## Evidence

- Focused dashboard, reconciliation, official-paper and CLI suite: 59 passed.
- Full local regression: 1571 passed, 5 skipped.
- New integration test proves a positive legacy row cannot create official
  PnL or an official closed-trade count.

## Safety

This change is read-only at the API boundary.  It does not create a ledger
row, route an order, alter capital, enable paper execution, promote a strategy
or affect live trading.
