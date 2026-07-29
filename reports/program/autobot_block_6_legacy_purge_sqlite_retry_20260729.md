# AUTOBOT Block 6 — Legacy Purge SQLite Retry — 2026-07-29

## Decision

**GO — local persistence reliability hardening.** No VPS operation is required
or attempted while Hetzner remains unavailable.

## Finding

The old `cleanup_old_data` maintenance path bypassed AUTOBOT's shared SQLite
write lock and bounded retry helper. A transient `database is locked` event
could therefore make the maintenance action fail immediately even though other
runtime writes use the configured busy timeout and retry policy.

## Change

- The legacy `trades`-table cleanup now runs through the shared
  `OrderRepository._with_write_retries` mechanism.
- It keeps the original deletion predicate and does not touch the canonical
  trade ledger, shadow ledger, paper capital, order router or execution flags.
- A hermetic asynchronous test injects one temporary SQLite lock and proves one
  commit occurs after retry.

## Required validation

Completed locally:

- persistence, lifecycle and cold-restart suite: **39 passed**;
- complete repository suite: **2057 passed, 6 skipped, 2 deselected**.

Run `git diff --check` and a changed-file secret scan before commit. A future
VPS deployment must validate the ordinary read-only health and evidence checks;
it does not need to invoke this maintenance path.
