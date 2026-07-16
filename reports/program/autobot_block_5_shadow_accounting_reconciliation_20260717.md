# AUTOBOT Block 5 — shadow accounting and reconciliation — 2026-07-17

## Decision

`GO` for a hermetic, research/shadow ledger improvement.  It does not enable
the historical paper engine and does not contact Kraken or any order endpoint.

## Change

- The append-only shadow ledger now reconstructs positions, net cash flow by
  quote asset and realized PnL solely from recorded fills and their cost
  evidence.
- A caller may reconcile baseline-adjusted cash balances in addition to open
  positions and open orders.  A mismatch returns `RECONCILIATION_REQUIRED` and
  sets the halt flag.
- No starting balance is inferred by the ledger.  It must be supplied by an
  independent observation, preserving a meaningful reconciliation boundary.
- Fill cost evidence now has to agree with the fee recorded on `FillEvent`.
- Recovery from an `UNKNOWN` order state remains idempotent and test-covered.

## Safety

- The ledger accepts shadow intents only.
- Cash/PnL reconstruction is local SQLite accounting, not an exchange balance
  claim.
- Paper capital, live execution, automatic promotion, sizing and leverage
  remain disabled.

## Residual limit

The historical runtime database remains legacy evidence only.  It cannot be
silently converted into canonical contracts; the future paper path requires
complete contract evidence from inception and human review.
