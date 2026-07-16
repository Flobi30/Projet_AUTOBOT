# AUTOBOT Block 2 — Bounded Research Coordinator (2026-07-16)

## Verdict

`GO` — the coordinator is deployed and its isolated VPS smoke test has
validated the fail-closed boundary.

- Implementation commit: `07baef2c37f3eef8f05318907614ec5f479b4953`.
- Deployed source and documentation commit:
  `9c227cac097ef909e78eea01cebb70dba379b43a`.

## Scope

This increment connects the typed research scheduler to one bounded,
research-only smoke experiment. It does not connect research to the runtime
trading process.

- No paper capital, live trading, promotion, shadow activation, sizing,
  leverage, UI change or order path is introduced.
- Scheduler command text is never parsed or executed.
- The coordinator calls typed scheduler and runner APIs directly.
- Only the pre-approved generic cross-sectional templates are eligible for an
  unattended smoke gate.
- One feature snapshot receives at most one unattended attempt. Further work
  requires a new snapshot or explicit human-reviewed research.

## Safety boundaries

The coordinator requires a verified point-in-time feature manifest with proven
runtime parity. It registers immutable experiment evidence before calculation.

It fails closed when:

- the scheduler has no runnable smoke candidate;
- the candidate is not in the strict hypothesis/template allowlist;
- provenance or parity is invalid;
- a material experiment has already advanced;
- the feature snapshot was already claimed;
- the runner raises an error.

The experiment registry now records append-only execution and snapshot claims,
which prevent concurrent or repeated automatic work on the same evidence.

## Daily isolation

The daily service now starts the coordinator only after canonical OHLCV and
feature artifacts exist. Its container is isolated with:

- no network;
- read-only root filesystem;
- no runtime state database or secret mount;
- only `data/research` writable;
- no access to paper/live/order services.

The daily service lock and the SQLite snapshot claim provide two independent
guards against duplicate runs.

## Local validation

- Targeted coordinator/registry/CLI/service suite: `86 passed`.
- Full suite: `1541 passed, 5 skipped`.
- Python syntax compilation: passed for touched Python modules.
- `git diff --check`: passed.

The Windows shell cannot syntax-check the systemd script because no WSL
distribution is installed. `bash -n` remains required during the VPS smoke.

## VPS validation

- GitHub source, VPS source and the rebuilt runtime container were aligned on
  `9c227cac097ef909e78eea01cebb70dba379b43a`.
- `bash -n deploy/systemd/run-autobot-research-collection.sh` passed before
  the rebuild.
- The manual coordinator smoke used the latest canonical feature manifest:
  `daily_2026_07_16T00_20_07Z_canonical_features_feature_snapshot.json`.
- The isolated coordinator container had no network, a read-only root
  filesystem, no runtime state database and only `data/research` writable.
- It emitted
  `data/research/reports/bounded_research_coordinator/manual_2026_07_16_coordinator.json`
  with decision `NO_RUNNABLE_CANDIDATE` and reason
  `scheduler_selected_no_runnable_smoke`.
- No candidate was executed. This is the expected result while all candidates
  are rejected, data-blocked or otherwise outside the unattended allowlist.
- The runtime remained healthy after the smoke: orchestrator running,
  WebSocket connected and 14 instances.
- The paper execution adapter, live confirmation, strategy-router live flag,
  automatic promotion and instance-split executor were all confirmed false.

## Residual risk

The coordinator deliberately does not claim to find an alpha. A rejected or
insufficient-data smoke result is the expected safe outcome until a strategy
survives later research gates. The next increment must investigate the
candidate/data blockers rather than weakening this coordinator gate.
