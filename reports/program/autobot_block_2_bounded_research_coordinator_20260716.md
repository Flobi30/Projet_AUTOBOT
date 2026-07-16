# AUTOBOT Block 2 — Bounded Research Coordinator (2026-07-16)

## Verdict

`GO_LOCAL` — the coordinator is ready for controlled VPS deployment and smoke validation.

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

## Deployment gate

Before marking this increment `GO`, verify on the VPS:

1. GitHub, VPS source and container code are aligned.
2. `bash -n deploy/systemd/run-autobot-research-collection.sh` passes.
3. The coordinator runs in its isolated container or exits fail-closed with a
   report.
4. The report confirms all execution flags remain false.
5. The runtime container health and existing safety flags remain unchanged.

## Residual risk

The coordinator deliberately does not claim to find an alpha. A rejected or
insufficient-data smoke result is the expected safe outcome until a strategy
survives later research gates.
