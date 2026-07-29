# AUTOBOT Block 2 — Gate-transition retry integrity

## Scope

Local-only hardening of `ExperimentRegistry.record_gate_result()`.
This is research-governance code: it records validation evidence, but cannot
run a strategy, start shadow, activate paper capital, promote or enable live.

## Change

- Gate transitions now use the registry's short, retry-safe write transaction.
- A replay is accepted only when its deterministic transition id, status,
  metrics, reasons and complete artifact identity set exactly match the
  persisted evidence.
- A different artifact set for an otherwise identical transition is rejected;
  a previously recorded stage with different evidence is also rejected.
- After an experiment becomes terminal, only an exact replay of its terminal
  stage may be considered. Replaying an older stage remains a terminal error.

The sealed `record_final_holdout_review()` workflow is deliberately unchanged.
It remains a separate fail-closed operation because it owns immutable holdout
evidence and must never be broadly retried without a dedicated review.

## Evidence

Commands run locally:

```text
python -m py_compile src/autobot/v2/research/experiment_registry.py
$env:PYTHONPATH='src'; python -m pytest tests/research/test_experiment_registry.py -q
```

Result: **28 passed**.

New coverage proves that:

- exact DATA_CHECK and NET_SMOKE replays return the existing state;
- an artifact variation under the same gate is rejected;
- terminal experiments continue to reject a replay of an old stage.

## Safety

All experiment rows and exports remain research-only with paper, live and
promotion permissions false. No order, private endpoint, shadow run,
paper-capital action, sizing/leverage change, UI change or VPS action occurred.

## VPS status

Hetzner remains unavailable. Deployment and runtime evidence are deferred; no
SSH, rebuild, restart, remote DB operation or collection was attempted.

## Decision

**GO (local only).** Ready for GitHub after the research regression suite.
