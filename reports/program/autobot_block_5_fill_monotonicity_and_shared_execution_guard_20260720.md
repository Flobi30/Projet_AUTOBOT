# AUTOBOT Block 5.5 - Fill Monotonicity and Shared Execution Guard - 2026-07-20

## Verdict

**GO - fail-closed OMS hardening only.** No paper-capital, live, promotion,
sizing, leverage, derivative, or order-routing activation occurred.

## Scope

The previous execution guard covered only the asynchronous executor. The legacy
synchronous executor remained importable and could therefore bypass that
defence. Separately, persisted partial fills could be overwritten by a smaller
cumulative value, weakening recovery evidence.

## Delivered behavior

- A side-effect-free shared authorization module now protects both Kraken
  executors. `AddOrder` and `CancelOrder` are rejected before client creation,
  signing, nonce generation, rate limiting, or network I/O unless every
  explicit real-execution confirmation is set.
- The synchronous legacy executor is covered even though the production async
  runtime does not import it. This makes the quarantine a defence-in-depth
  boundary rather than an import-convention assumption.
- Persisted cumulative fills are finite, non-negative, and monotonic. A later
  partial observation cannot reduce a prior filled quantity.
- Repeating the same cumulative partial fill is idempotent; only a larger
  cumulative quantity appends a new `PARTIAL -> PARTIAL` observation.
- `PARTIAL` requires a positive quantity strictly below the requested quantity.
- `FILLED` requires an explicit cumulative quantity equal to the requested
  quantity within a small deterministic tolerance. Missing, underfilled, or
  overfilled terminal claims remain non-terminal for reconciliation.

## Validation

Source revision tested: `81af764a98b17be292ef04f6e96b7482a651d80c`.

- Targeted execution, persistence, close, reconciliation and legacy-executor
  suite: `75 passed`.
- Full repository suite: `1790 passed, 6 skipped`.
- `python -m compileall -q src`: passed.
- `git diff --check`: passed.
- The new tests prove that both executor implementations block a default real
  mutation without constructing a client, and that partial fill regressions,
  terminal underfills, and terminal fills without quantity are rejected.

## VPS evidence

The final controlled deployment of the GitHub revision containing this report
rebuilds the AUTOBOT image from source revision `81af764a` and verifies that the
checkout and image label match. It preserves generated runtime data and checks
the container, `/health`, WebSocket, instances, global kill state, research
timers, safety flags, and recent critical logs.

The deployment must leave these settings unchanged:

- `LIVE_TRADING_CONFIRMATION=false`;
- `STRATEGY_ROUTER_LIVE_ENABLED=false`;
- `COLONY_AUTO_LIVE_PROMOTION=false`;
- `ENABLE_INSTANCE_SPLIT_EXECUTOR=false`.

The pre-existing `PAPER_TRADING=true` setting is not authorization for
paper-capital and is not changed by this work.

## Residual risks / next gate

- A canonical, append-only projection of independently verified external fill
  evidence is still required before a recovered `closing` position may be
  finalised economically.
- The current safe result for uncertain orders is to block new entries and
  require reconciliation; it intentionally does not guess PnL or position
  state.
- No strategy has qualified for paper-capital or live review.
