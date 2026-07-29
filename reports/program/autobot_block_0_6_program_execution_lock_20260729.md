# AUTOBOT — Program execution lock — 2026-07-29

## Decision

`GO_LOCAL / REWORK_FOR_VPS_VALIDATION`.

The programme remains strictly research/shadow-only.  This report does not
authorize paper capital, live trading, strategy promotion, sizing, leverage,
private Kraken calls or an order path.

## Delivered boundary

Runtime code revision: `138944c3ec2cbbe77204a643ee5ff25ee8423bb8`.

`PROGRAM_EXECUTION_LOCKED` is a source-level programme lock.  It makes all
former paper and live environment flags non-authorizing:

- `paper_execution_authorized()` remains false;
- `observation_only_runtime()` remains true;
- the active orchestrator receives an `ObservationOnlyOrderExecutor` even if
  legacy paper arguments are supplied directly;
- `AddOrder` and `CancelOrder` return the existing machine-readable
  `REAL_ORDER_MUTATION_BLOCKED` response before a private request can occur.

Lifting this boundary requires a separate reviewed source change and human
paper review.  It cannot be done by editing `.env`, Docker Compose or a VPS
environment variable.

## Verification

| Check | Result |
| --- | --- |
| Runtime boundary, router and configuration tests | `76 passed` |
| Full suite | `2024 passed, 6 skipped, 2 deselected` |
| Python compilation | passed |
| `git diff --check` | passed before commit |
| Secret-pattern scan | no matching source files |

The tests include a complete legacy paper configuration and complete legacy
live configuration.  Both remain observation-only; the orchestrator discards
the supplied credentials and does not create `data/paper_trades.db`.

## VPS gate

No VPS command, deployment, restart, database write, collector, paper order
or live order was attempted for this increment.  Hetzner maintenance had
removed SSH reachability at the latest check, so GitHub/VPS/container
alignment is unproven until normal access is restored.

Once SSH is restored, deploy only with `bash deploy/rebuild-autobot-image.sh`,
then collect fresh runtime evidence with
`bash deploy/verify-autobot-runtime-evidence.sh`.  The required smoke must
still show observation-only runtime and paper/live/promotion all disabled.
