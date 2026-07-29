# AUTOBOT Block 5 - Legacy mutation method guards - 2026-07-29

## Decision

`GO_LOCAL_WAITING_FOR_VPS`

The active programme remains locked to research/shadow-only operation. This
local hardening closes two archived direct-mutation paths that could otherwise
be reached only by bypassing their retired constructors.

## Change

- `TradingInstance._cancel_all_orders` now rejects execution before reading
  object state, credentials or constructing a Kraken client.
- `TradingInstance._close_all_positions_market` has the same first-operation
  rejection before a market-close order can be prepared.
- The archived root `OrderManager` rejects private-client access centrally,
  including from an otherwise harmless sandbox instance.
- The synchronous and asynchronous `OrderExecutor` private-client helpers
  reject direct invocation before they can read credentials, generate a nonce
  or open a Kraken session.

The guards call the existing programme-wide observation-only boundary. They do
not introduce a paper executor, a live executor, a paper wallet, or a route to
any Kraken endpoint.

## Local proof

- `python -m compileall -q src`: passed.
- Focused retirement, executor, deployment-evidence and order-manager suites:
  `51 passed`.
- `git diff --check`: passed.
- The regression test constructs the archived trading instance with
  `object.__new__` and proves both mutating methods fail before any object
  attribute needs to exist.
- Equivalent direct-invocation tests cover both order-executor private helpers.

## Safety

- No order, paper order, paper-capital write, promotion or live path was run.
- No private Kraken endpoint, credential or secret was read or used.
- No sizing or leverage changed.
- No VPS, Docker, database, data or system service was touched.

## Required VPS follow-up after Hetzner is restored

Deploy the committed change through the normal fast-forward/rebuild workflow,
then run `deploy/verify-autobot-runtime-evidence.sh`. The verifier must still
report the programme lock as true and every paper/live authorization as false.
