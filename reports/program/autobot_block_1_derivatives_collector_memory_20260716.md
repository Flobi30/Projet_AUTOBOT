# AUTOBOT Block 1 — Derivatives collector memory boundary — 2026-07-16

## Decision

REWORK completed locally; VPS validation is required before the scheduled
funding refresh is considered recovered.  This is a research-data-only change.

## Evidence

The public Kraken Futures funding refresh was reproducibly killed by the
container memory cgroup with exit status 137.  Kernel evidence recorded an
OOM kill at approximately 522 MiB RSS while the job limit was 512 MiB.

The cause was not an order or runtime path: each scheduled refresh reloaded
all immutable funding exports before deduplicating them into the compact
history.  The immutable archive had grown to approximately 120 MiB.

## Change

Canonical compaction is now incremental after the initial backfill:

- bootstrap: all immutable exports are read once to create the compact history;
- scheduled refresh: read only the compact history plus the file written by
  the current run;
- immutable exports remain preserved for audit and are not silently deleted;
- the history remains atomically published and deduplicated by its canonical
  keys.

This applies consistently to funding, candles, ticker snapshots and basis.

## Tests

- Collector, scanner and CLI targeted suite: 63 passed.
- Full local regression: 1570 passed, 5 skipped.
- `python -m compileall -q src`: passed.
- Regression test proves that an unselected old immutable export is not read
  by an incremental refresh.

## Safety

The job still uses only public Kraken Futures market-data endpoints.  It has
no secrets, no runtime database mount, no paper/live activation, no order
endpoint and no strategy activation.
