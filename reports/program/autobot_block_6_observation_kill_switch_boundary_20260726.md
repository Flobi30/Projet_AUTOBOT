# Block 6 — Observation-only kill-switch boundary, 2026-07-26

## Trigger

The hardened observation container exposed a persisted kill switch with the
legacy reason `reconciliation_required/exchange_open_orders_unavailable`.
That latch originated before the runtime was made non-executable.  It must
continue to block any paper or live runtime, but cannot safely prevent an
incapable observation process from collecting public research data forever.

## Decision

The persisted latch is **not cleared, acknowledged, overwritten, or hidden**.
Instead, startup attestation now treats it as a preserved safety condition only
when the caller explicitly selects observation-only mode.  This exception is
unavailable to every executable mode.

## Invariants

- the global kill-switch database retains `tripped=true`;
- paper or live startup still fails on the same state;
- observation mode still has no wallet, private Kraken credentials, or order
  execution path;
- a future executable deployment requires a deliberate recovery acknowledgement
  after independent reconciliation.

## Tests

- `python -m compileall -q src` passed;
- startup attestation, cold restart, observation-boundary, and deployment
  safety suite: 35 passed;
- added regression test proves the persisted latch remains tripped after a
  successful observation-only attestation.

## Deployment gate

Accept only after the VPS reports a healthy observation-only container and the
attestation log identifies the preserved latch without any private/execution
initialisation.
