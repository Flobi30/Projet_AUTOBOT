# AUTOBOT Block 5 — Automatic Exit OMS Consistency — 2026-07-20

## Verdict

**GO — research/shadow safety hardening only.**  This change does not enable
paper capital, live execution, promotion, sizing, leverage or a new order
path.

## Scope

The automatic take-profit, stop-loss and trailing-stop path now treats an
ambiguous executor result as a reconciliation problem rather than inventing a
position close or PnL.

## Delivered behavior

- The persisted automatic-exit lifecycle is `NEW -> SENT -> ACK ->
  PARTIAL|FILLED`.
- A position is not closed and no closing ledger row is written unless both
  `ACK` and `FILLED` persist successfully.
- Executor exceptions/timeouts, a missing or non-positive fill price, and an
  overfill move the order to non-terminal `UNKNOWN` and keep duplicate-exit
  protection active.
- A partial fill is recorded only after `ACK`; it remains non-terminal and
  cannot close the whole position or trigger a second automatic SELL.
- A failed `ACK`, `FILLED` or partial-fill persistence leaves the position
  unchanged and the order non-terminal for reconciliation.

## Validation

Local source revision tested: `bedf6d56cd49a7f3304856f7db1f05ed65e0247f`.

- Targeted automatic-exit suite: `9 passed`.
- OMS/paper/persistence/signal regression set: `77 passed`.
- Full repository suite: `1763 passed, 6 skipped`.
- `python -m compileall -q src`: passed.
- `git diff --check`: passed.

## VPS evidence

At the tested source revision:

- VPS checkout and AUTOBOT image revision matched the tested commit.
- `autobot-v2` was running and `/health` reported `healthy`.
- All four isolated research timers were active.
- Live confirmation, strategy-router live execution, automatic promotion and
  instance-split execution remained false/disabled.
- Filtered recent runtime logs contained no traceback, critical error, live
  order or live-trading activation.

The ephemeral SQLite restore drill also passed: source and restore integrity,
schema and row counts matched; temporary backup and restore data were removed.

## Residual risks / next gate

- `instance_async.close_position()` still mutates legacy in-memory position
  state before it has a confirmed idempotent persistence result.  A dedicated
  reconciliation-safe close transaction is required before any paper review.
- The external stop-loss callback is a legacy fill notification and must be
  reconciled as an already-executed fill; it must not be redirected to a new
  market SELL.
- Runtime state-transition validation remains a separate Block 5.1 task,
  because legacy signal recovery and direct handlers still use inconsistent
  state sequences.

No strategy is promoted by this evidence.
