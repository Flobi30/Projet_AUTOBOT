# AUTOBOT - Legacy synchronous runtime retirement - 2026-07-22

## Decision

**GO - retired execution path quarantined.**

The active application entrypoint is `main_async.py`. The former threaded
`Orchestrator` and `TradingInstance` classes remain importable only to preserve
legacy type annotations and historical tooling. Their constructors now fail
closed before they can initialise an order executor, Kraken websocket,
persistence store or signal handler.

## Implemented boundary

- Added a pure `legacy_runtime` retirement boundary with no environment
  override.
- `Orchestrator(...)` rejects before creating an order executor or websocket.
- `TradingInstance(...)` rejects before recovering or saving state, and before
  any legacy signal handler can exist.
- `main_async.py` remains the only supported production entrypoint; no async
  runtime code path was changed.

## Tests

```text
python -m py_compile src/autobot/v2/legacy_runtime.py \
  src/autobot/v2/orchestrator.py src/autobot/v2/instance.py

pytest tests/test_legacy_sync_runtime_retirement.py \
  tests/test_async_runtime_legacy_quarantine.py \
  tests/test_deployment_safety_invariants.py \
  tests/test_production_safety.py \
  tests/test_orchestrator_legacy_entry_guard.py -q
-> 14 passed

pytest -q
-> 1864 passed, 6 skipped
```

The new tests prove legacy construction never calls the legacy executor,
websocket or persistence factory. A separate production-entrypoint test proves
that importing `main_async` does not load the synchronous runtime modules.

## VPS deployment validation

Implementation commit:

```text
a9374463027d29bed4282dfd046634130d7bae7c
```

The VPS checkout and provenance-labelled image were aligned to that commit.

```text
/health: healthy; orchestrator running; WebSocket connected; 14 instances
runtime-generated/untracked VPS artifacts preserved: 13
research/resilience timers restored and active: 9
isolated VPS pytest (network none, read-only source): 9 passed
```

## Safety confirmation

- No order endpoint was called.
- Paper execution adapter/router, paper test trading and dynamic capital
  reallocation remain disabled.
- Automatic promotion, live confirmation, live routing and split execution
  remain disabled.
- No matching live or paper order submission log was observed after restart.
- Grid remains retired/no-go.

## Remaining work

The active async runtime is intentionally still observation-only. This change
removes an obsolete execution-capable path; it does not qualify any strategy,
start shadow trading, activate paper capital or change the paper/live plan.
