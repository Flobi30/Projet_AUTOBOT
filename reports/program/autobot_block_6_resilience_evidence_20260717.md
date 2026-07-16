# AUTOBOT Block 6 — Resilience Evidence

## Decision

`GO` for continued research/shadow operation only.

This evidence does **not** authorize paper capital, live trading, strategy
promotion, leverage, sizing changes, or order submission. The expected
readiness state remains `NOT_READY_FOR_HUMAN_PAPER_REVIEW` because the
24-layer coverage matrix still contains `PARTIAL` layers and no strategy has
earned a human paper mandate.

## VPS evidence

At commit `16b0b7e59377705edd22258a446477df88f72592`:

- `autobot-v2` was healthy and the WebSocket was explicitly connected;
- the isolated five-minute runtime-resilience timer was enabled and active;
- its latest run completed successfully with `RESILIENCE_HEALTHY`;
- SQLite integrity was `ok`, no fail-closed incident was present and no order
  submission was attempted;
- the measured free disk capacity was 61.6 GB;
- a disposable SQLite backup/restore drill succeeded with matching schema and
  table row counts; the temporary backup and restore were removed afterwards.

The runtime audit is read-only with respect to `autobot_state.db`. The
scheduled monitor is isolated from exchange networking, secrets and order
routing.

## Controls verified

- bounded retry and SQLite busy-timeout paths;
- fail-closed handling for stale data, WebSocket/API uncertainty, locked or
  corrupt SQLite, disk exhaustion, restart, unknown order and reconciliation
  divergence;
- disabled-by-default retained-backup service, pending approved encrypted
  off-VPS storage and retention policy;
- research/shadow incident runbook;
- a non-authorizing readiness-dossier primitive that refuses to declare
  readiness while required layers remain partial or unsafe.

## Residual risks and next decision

1. The retained encrypted/off-VPS backup policy is intentionally unconfigured;
   only ephemeral restore evidence exists.
2. The current programme must not claim paper readiness while coverage layers
   remain partial and no alpha passes the research gates.
3. Continue collecting canonical derivatives data and run bounded, reproducible
   research. If no strategy survives net-cost and out-of-sample validation, the
   correct outcome is to remain non-executing.

## Test evidence

- Focused resilience, runtime-audit, deployment, CLI and shadow-ledger suite:
  `64 passed`.
- Full repository non-regression suite: `1630 passed, 6 skipped, 1 existing
  dependency deprecation warning`.
- Python compilation, diff-whitespace check, GitHub push, controlled VPS
  rebuild and VPS health smoke are required before this report is accepted.
