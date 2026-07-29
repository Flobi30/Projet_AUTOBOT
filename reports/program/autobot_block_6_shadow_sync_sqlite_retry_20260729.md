# AUTOBOT Block 6 — Shadow sync SQLite retry — 2026-07-29

## Decision

**GO — local research/shadow persistence hardening.** The VPS remains untouched
while Hetzner is unavailable.

## Finding

The scheduled shadow-observation sync shares `data/autobot_state.db` with the
observation runtime. It had a 30-second SQLite busy timeout, but a lock that
survived that wait could either abort the job or be converted into a skipped
trade inside the per-row exception handler. The sync also did not explicitly
rollback before attempting a repeated source transaction.

## Change

- Schema setup and each source sync now run in a short, explicitly committed
  transaction with bounded exponential retry for SQLite `locked`/`busy` only.
- Retry always rolls back first; rollback failure aborts the batch instead of
  risking a contaminated transaction.
- `sqlite3.OperationalError` is re-raised from per-trade processing so a
  temporary database lock is retried at the source-transaction boundary rather
  than silently reported as a bad trade.
- Existing trade IDs and High Conviction economic-duplicate checks remain the
  idempotency boundary.

## Validation

- `python -m pytest tests/paper/test_shadow_observation_sync.py
  tests/paper/test_paper_ledger_loader.py
  tests/research/test_daily_data_collection_runner.py tests/test_v2_cli.py
  tests/test_persistence_db_reliability.py -q` — **115 passed**.
- `python -m compileall -q src` — passed.
- New unit test: a busy `commit()` performs rollback then retries once.
- New integration test: a temporary source lock is retried and writes exactly
  one opening and one closing shadow-ledger row.

## Safety

- The module remains a batch-only `shadow_paper` synchronizer.
- No order, router, paper capital, promotion, live flag, sizing, leverage,
  private API, VPS, Docker, or runtime service was touched.
- Grid remains blocked; shadow observations remain excluded from promotion.

## Required VPS follow-up

After access returns, deploy through the controlled workflow and observe the
scheduled sync alongside the runtime. Confirm the expected bounded retry log
only if a temporary lock occurs; repeated locks remain a fail-closed operational
incident to investigate, not an instruction to increase retry limits.
