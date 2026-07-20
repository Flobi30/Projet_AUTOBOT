# AUTOBOT Block 5.4 - Unresolved Closes and Real-Execution Boundary - 2026-07-20

## Verdict

**GO - fail-closed safety hardening only.** No paper-capital, live,
promotion, sizing, leverage, derivative, or order-routing activation occurred.

## Scope

This increment removes two paths that could otherwise turn uncertain state
into irreversible economic action:

- a persisted close reservation is now recovered and treated as unresolved
  until canonical fill evidence is available;
- direct use of the asynchronous Kraken executor cannot create or cancel a
  real order unless every explicit execution authorization is present.

## Delivered behavior

### Unresolved close recovery

- Persisted positions in both `open` and `closing` state are restored after a
  restart. An unknown non-terminal recovered status is handled conservatively
  as `closing`.
- A recovered `closing` position is reported as the critical divergence
  `closing_position_unresolved` with
  `blocked_pending_canonical_fill`; reconciliation does not close it, assign
  PnL, or create a synthetic sell.
- A legacy executor response that claims success but reports zero executed
  volume remains `UNKNOWN` and keeps its close reservation for reconciliation.

### Real Kraken execution boundary

- `OrderExecutorAsync` blocks every `AddOrder` and `CancelOrder` before rate
  limiting, signing, nonce generation, or network I/O unless all of these are
  explicitly true:
  `PAPER_TRADING=false`, `LIVE_TRADING_CONFIRMATION=true`,
  `STRATEGY_ROUTER_LIVE_ENABLED=true`,
  `AUTOBOT_REAL_ORDER_EXECUTION_ENABLED=true`, and
  `PREFLIGHT_ONLY=false`.
- This is an executor-boundary guard, so a caller that bypasses the router
  cannot bypass it.
- If `PAPER_TRADING=true` but the paper executor cannot be imported, the
  orchestrator raises `paper_executor_unavailable` rather than silently
  constructing the Kraken executor.

## Validation

Source revisions tested:

- `f57fb3a0fdf158c52d4ab258e6da0a4196f5957a` - unresolved close recovery:
  targeted suite `80 passed`; full repository suite `1784 passed, 6 skipped`.
- `d52e91b4592a48533e283935184c5b5e11869f27` - real-execution boundary:
  targeted suite `63 passed`; full repository suite `1788 passed, 6 skipped`.

Both revisions also passed `python -m compileall -q src` and
`git diff --check`. The new execution-boundary tests prove that default
`AddOrder` and `CancelOrder` calls are rejected without touching the private
API and that the full explicit flag set is required for a mocked mutation.

## VPS evidence

The source revision `f57fb3a` was deployed before this increment; its checkout
and image label matched, the container was healthy, `/health` was healthy, and
the global kill switch was not tripped. The deployment accompanying this report
must fast-forward to the final GitHub revision and repeat the same controlled
smoke check.

In all observed deployments, the following safety settings remained unchanged:

- `LIVE_TRADING_CONFIRMATION=false`;
- `STRATEGY_ROUTER_LIVE_ENABLED=false`;
- `COLONY_AUTO_LIVE_PROMOTION=false`;
- `ENABLE_INSTANCE_SPLIT_EXECUTOR=false`.

The pre-existing `PAPER_TRADING=true` setting was not changed. No paper-capital
route, promotion, real order, or real order-path activation occurred. Generated
runtime entries on the VPS worktree remain user data and must be preserved.

## Residual risks / next gate

- An uncertain external fill still needs canonical fill projection before it
  can finalise a recovered `closing` position economically.
- Partial-fill monotonicity and deterministic order-event recovery should be
  audited next.
- This guard makes current execution fail closed; no live authorization has
  been granted or enabled by this work.
- No strategy has qualified for paper-capital or live review.
