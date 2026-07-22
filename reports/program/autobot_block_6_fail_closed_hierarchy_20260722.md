# AUTOBOT - Block 6: fail-closed hierarchy drill

## Decision

`GO` for this research/shadow safety proof. The drill documents and verifies
the order in which a future independently reviewed execution boundary must
reduce risk. It does not call that boundary.

Implementation commit: `40f9d0418c1927e525cf2105eb791176f9b2984a`.

## Contract

`FailClosedRecoveryPlan` is a side-effect-free control-plane contract. It
never routes an order, cancels an order, changes a runtime flag, or authorizes
paper capital or live trading.

The hermetic `fail-closed-drill` covers these escalation levels:

1. `BLOCK_NEW_SIGNALS`
2. `BLOCK_NEW_ORDERS`
3. `CANCEL_OPEN_ORDERS`
4. `REDUCE_POSITIONS`
5. `HALT`

`RISK_LIMIT_BREACH` is an explicit terminal incident. It produces the complete
future action sequence but remains non-executable until a separate human
approved paper scope exists. Unknown orders and reconciliation divergence halt
after blocking and planned cancellation; they do not invent a position change.

## Evidence

Local validation:

```text
python -m compileall -q src
pytest tests/research/test_resilience_readiness.py \
       tests/research/test_runtime_resilience_audit.py \
       tests/research/test_runtime_resilience_deployment.py \
       tests/test_v2_cli.py \
       tests/test_contracts.py \
       tests/test_production_safety.py \
       tests/test_orchestrator_execution_bypass_guards.py \
       tests/test_signal_handler_async_unit.py -q
```

Result: `104 passed`.

VPS validation used the AUTOBOT image with network disabled, root filesystem
read-only, dropped Linux capabilities and only a temporary in-memory `/tmp`.
The full fail-closed drill passed, followed by the same `104` focused tests.

At validation time, the checkout and image both resolved to
`40f9d0418c1927e525cf2105eb791176f9b2984a`; the container was healthy, its
WebSocket connected and all four research timers active.

## Safety invariants

- `order_submission_attempted=false` in every drill result;
- paper capital, live and automatic promotion remain disabled;
- the drill contains no router, paper engine or signal-handler import;
- Grid remains retired from execution;
- the layer remains `PARTIAL`: this is a proof of future control ordering, not
  permission to execute cancellation or reduction actions.
