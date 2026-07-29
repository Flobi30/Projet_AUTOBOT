# AUTOBOT Block 2 — Experiment-registry SQLite creation safety

## Scope

Local-only reliability hardening for three append-only, research-only registry
primitives:

- experiment registration;
- immutable holdout reservation;
- final-holdout ownership claim.

The patch does not run an experiment, evaluate a strategy, change a statistical
result, create a shadow/paper order, allocate capital or alter any live flag.

## Change

- Registry writes now use short `BEGIN IMMEDIATE` transactions, rollback on
  failure and bounded exponential recovery for transient SQLite `locked`/`busy`
  errors.
- The read/validate/write sequences for experiment identity, holdout identity
  and exclusive final-review ownership are serialized across registry
  processes.
- Each operation re-reads its deterministic identity after a retry, preserving
  the existing idempotent result (`existing experiment`, `False` reservation,
  or `False` claim by the same experiment).
- Connections used by this write helper are closed after commit or rollback.

`record_final_holdout_review()` remains unchanged and fail-closed. Its sealed
evidence and final-review replay semantics require a separate review rather
than a broad retry wrapper.

## Evidence

Commands run locally:

```text
python -m py_compile src/autobot/v2/research/experiment_registry.py
$env:PYTHONPATH='src'; python -m pytest tests/research/test_experiment_registry.py -q
```

Result: **27 passed**.

New tests prove:

- a temporary lock retries once and a persistent lock remains visible;
- two independent registry instances concurrently registering the same
  experiment receive the same immutable experiment id;
- concurrent reservation of the same immutable holdout produces exactly one
  successful reservation;
- concurrent claims by the same experiment produce exactly one successful
  claim, and the manifest records one owner.

## Safety

The experiment schema and exports continue to force:

```text
research_only=true
paper_capital_allowed=false
live_allowed=false
promotable=false
```

No order, private Kraken endpoint, paper-capital action, promotion,
sizing/leverage change, shadow run, live action, UI change or VPS action was
performed.

## VPS status

Hetzner is unavailable for the reported maintenance/payment interval. No SSH,
deployment, rebuild, restart, remote database action or collection was
attempted.

## Decision

**GO (local only).** Ready for GitHub. Deployment evidence remains deferred.
