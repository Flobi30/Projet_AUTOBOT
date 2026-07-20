# AUTOBOT Block 5 - Persistence-First Position Close - 2026-07-20

## Verdict

**GO - research/shadow safety hardening only.** This change does not enable
paper capital, live execution, promotion, sizing, leverage, derivatives, or a
new order path.

## Scope

Closing a position now has a durable, fail-closed boundary. The runtime must
persist a `closing` reservation before a protective SELL is submitted and must
persist the position close, the closing trade and the instance-capital state
before it mutates in-memory PnL or capital.

## Delivered behavior

- An open position is atomically reserved as `closing`; a second automatic or
  legacy direct SELL cannot start while that reservation remains active.
- A known executor rejection or zero fill releases the reservation only after
  its OMS rejection is persisted.
- A successful close persists the position, exactly one closing trade and the
  instance state in one short SQLite transaction with the existing bounded
  retry/backoff policy.
- A retry after an uncertain commit is idempotent: it reuses the already
  persisted closing trade instead of creating a duplicate.
- A failed durable close leaves the position `closing`, does not manufacture
  local PnL/capital and moves the order to reconciliation-required `UNKNOWN`.
- Partial fills, overfills and missing fills remain non-terminal and do not
  close the full position or write an official closing ledger row.
- The historical async direct SELL path now follows the same reservation and
  durable-close rule; it no longer substitutes a locally calculated PnL when
  persistence fails.

## Validation

Source revision tested: `4c74062d6080540baee20568168a8d59e5991a5e`.

- Focused persistence, automatic-exit, signal-handler and safety suite:
  `70 passed`.
- Full repository suite: `1771 passed, 6 skipped`.
- `python -m compileall -q src`: passed.
- `git diff --check`: passed.
- Diff scan found no API key, password, private-key or secret material.

## VPS evidence

At the deployed revision, the VPS checkout and the AUTOBOT image label matched
the tested commit. The container was `running` and `healthy`; `/health`
reported a running orchestrator, connected WebSocket and 14 instances.

- All four isolated research timers were active after deployment.
- `LIVE_TRADING_CONFIRMATION=false`.
- `STRATEGY_ROUTER_LIVE_ENABLED=false`.
- `COLONY_AUTO_LIVE_PROMOTION=false`.
- `ENABLE_INSTANCE_SPLIT_EXECUTOR=false`.
- Filtered recent logs contained no traceback, critical error, live order or
  live-trading activation.
- Runtime disk and memory headroom were healthy at the time of the smoke check.

The runtime worktree still contains generated runtime entries. They were
preserved and not reset, cleaned or committed as part of this deployment.

## Residual risks / next gate

- Legacy synchronous `instance.py` and the wider runtime order-state graph
  still require a dedicated migration/audit; they remain outside this async
  persistence-first change.
- A `closing` position deliberately requires reconciliation before any further
  automatic exit. This is safer than attempting another SELL after an
  uncertain execution result.
- No strategy has enough validated evidence for paper-capital or live review.

