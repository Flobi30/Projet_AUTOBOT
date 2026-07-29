# AUTOBOT Block 5 — Immutable Intent Idempotency — 2026-07-29

## Decision

**GO — local OMS hardening.** The implementation is confined to the
hermetic research/shadow ledger; production routing, paper capital and live
trading remain unchanged and disabled.

## Finding

The research OMS ledger already deduplicated an existing `client_order_id`,
but an `INSERT OR IGNORE` could silently accept a different in-memory intent
with the same client id. The stored intent was still the source of truth for
later fills, but the caller received an insufficiently explicit result.

## Change

- A repeated `client_order_id` is idempotent only when its canonical
  `OrderIntent` payload is byte-for-byte identical.
- A different payload for the same client id raises a fail-closed error.
- A risk decision must bind to the complete immutable registered intent, not
  merely the same `decision_id`.

## Safety

- Research/shadow ledger only; it accepts only `execution_mode=shadow`.
- No execution route, exchange call, paper fill, sizing or risk policy was
  changed.
- Deployment remains pending while Hetzner maintenance blocks controlled VPS
  verification.

## Required validation

Run focused OMS/ledger, reconciliation and contract tests, then the full
hermetic suite, diff check and secret scan before commit. Run the prescribed
VPS rebuild and smoke only after maintenance is over.
