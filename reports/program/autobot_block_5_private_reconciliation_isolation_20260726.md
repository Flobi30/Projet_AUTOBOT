# Block 5 — Private reconciliation isolation, 2026-07-26

## Finding

The observation-only service correctly used a non-executable order adapter,
but still started `ReconciliationManagerAsync`. That manager queries private
open-order state and therefore produced `exchange_open_orders_unavailable` in
a container deliberately stripped of Kraken credentials.

## Change

`OrchestratorAsync` now starts private exchange reconciliation only when the
runtime is executable. In observation-only mode it records an explicit
non-execution state and leaves `reconciliation_manager` unset.

This does not relax reconciliation for paper or live: those modes retain the
existing manager, critical-divergence callback, persistent kill switch, and
fail-closed behavior.

## Evidence

- `python -m compileall -q src` passed;
- observation boundary, reconciliation safety, startup attestation, cold
  restart, and deployment safety suite: 42 passed;
- no paper/live flags, credentials, router, wallet, sizing, leverage, or
  strategy logic changed.

## VPS acceptance

After deployment, logs must contain:

`Observation-only runtime: private exchange reconciliation disabled`

and must not contain a new private reconciliation divergence from this
process. The existing global kill latch stays persisted for future executable
runtimes.
