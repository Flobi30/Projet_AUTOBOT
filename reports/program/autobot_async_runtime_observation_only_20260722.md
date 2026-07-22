# AUTOBOT - Async runtime observation-only strategy guard - 2026-07-22

## Decision

**GO - runtime signal-emission bypass removed.**

The deployed async application already creates `observation_only` instances.
This increment closes the remaining configuration bypass: an external caller
can no longer pass `trend`, `grid` or an unknown historical strategy to
`OrchestratorAsync.create_instance` and obtain a legacy signal emitter.

## Implemented boundary

- `TradingInstanceAsync` records the requested strategy only as diagnostic
  metadata.
- The only installed runtime strategy is `ObservationOnlyStrategyAsync`.
- The effective runtime strategy and reason are exposed in the instance status
  for auditability.
- The observation strategy reports that signal emission and execution are both
  disabled.
- A canonical strategy-artifact consumer remains a future, separately verified
  requirement; this guard neither starts shadow trading nor creates an order.

## Tests

```text
python -m py_compile src/autobot/v2/instance_async.py \
  src/autobot/v2/strategies/observation_async.py

pytest tests/test_runtime_observation_only_strategy.py \
  tests/test_async_runtime_legacy_quarantine.py \
  tests/test_orchestrator_legacy_entry_guard.py \
  tests/test_signal_handler_async_unit.py \
  src/autobot/v2/tests/test_main_async_config.py \
  src/autobot/v2/tests/test_price_validation.py -q
-> 74 passed

pytest -q
-> 1868 passed, 6 skipped
```

The dedicated tests prove that `trend`, `grid` and unknown requests install a
non-signalling observation strategy before signal-handler setup.

## VPS deployment validation

Implementation commit:

```text
570a43a6bde912ae86245bff5dabd4cca82ef178
```

```text
/health: healthy; orchestrator running; WebSocket connected; 14 instances
runtime-generated/untracked VPS artifacts preserved: 13
research/resilience timers active: 9
isolated VPS pytest (network none, read-only source): 17 passed
```

## Safety confirmation

- No live, paper-capital, promotion, sizing or leverage setting changed.
- Paper execution adapter/router, paper test trading and dynamic reallocation
  remain disabled.
- No order-submission or live-activation log was observed after restart.
- Grid remains retired/no-go.

## Remaining work

This guard intentionally prevents runtime strategy activation until a future
canonical artifact consumer can prove point-in-time data/feature parity. It
does not make any hypothesis profitable or eligible for paper capital.
