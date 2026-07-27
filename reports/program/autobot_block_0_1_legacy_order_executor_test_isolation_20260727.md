# AUTOBOT Block 0.1 — legacy order-executor test isolation

## Decision

**GO.** The legacy synchronous `OrderExecutor` unit suite is now hermetic and
fast without changing the executor, the router, or any production safety flag.

## Change

- Removed test-only mutation of process-wide paper/live authorization flags.
- Mocked the executor module's imported authorization seams locally for the
  legacy API-protocol unit tests.
- Retained a mocked Kraken client in every private API test.
- Replaced wall-clock rate-limit waiting with a mocked sleep assertion.
- Kept circuit-breaker coverage while setting `max_retries=1` only in that
  test and disabling its local rate-limit delay.

## Why

The old suite both depended on the caller's observation-only environment and
set live authorization flags to `true`. Its retry/backoff loop took more than
the bounded terminal result window, preventing a complete regression verdict.
Real authorization behavior remains covered by dedicated observation and real
execution guard tests.

## Validation

```text
$env:PYTHONPATH='src'; python -m pytest src/autobot/v2/tests/test_order_executor.py -q
10 passed in 4.32s

$env:PYTHONPATH='src'; python -m pytest src/autobot/v2/tests/test_order_executor.py tests/test_real_execution_guard.py tests/test_observation_execution_boundary.py tests/test_production_safety.py -q
29 passed
```

## Safety

No production module changed. No environment flag, real key, private Kraken
call, paper capital, live order, sizing, leverage or promotion changed.
