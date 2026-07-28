# AUTOBOT Block 0.1 — Versioned Research-Memory Seed

## Decision

`GO_LOCAL_ONLY` — runtime research memory is now clearly separated from its
historical migration seed. No trading flag, capital setting, strategy policy,
order path or VPS runtime state changed.

## Change

- Moved the historical JSON from `reports/research/` to
  `docs/research/legacy_alpha_research_memory_seed.json`.
- Renamed the scheduler reference to
  `VERSIONED_RESEARCH_MEMORY_SEED_PATH` to make its immutable migration-only
  purpose explicit.
- The default append-only runtime store remains
  `data/research/alpha_research_memory.sqlite3`, which is ignored by Git.
- Added an explicit ignore rule for a stale
  `reports/research/alpha_research_memory.json` runtime artifact.

## Invariants

- A new default SQLite store imports the static seed once only.
- Reopening the runtime store does not import duplicate events.
- The static seed is never a runtime write target.
- All imported records remain research-only, non-promotable, paper-disabled
  and live-disabled.

## Local validation

```text
$env:PYTHONPATH='src'; python -m pytest
  tests/research/test_alpha_hypothesis_scheduler.py
  tests/research/test_bounded_research_coordinator.py
  tests/test_v2_cli.py -q
72 passed

python -m compileall -q src
PASS
```

VPS validation is pending SSH restoration. This change has not been deployed.
