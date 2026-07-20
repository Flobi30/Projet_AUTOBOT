# AUTOBOT Block 5 — Paper Executor Provenance

## Decision

`GO — retain the paper engine as a non-authorizing, traceable simulation only.`

The legacy paper executor no longer accepts a market, limit or stop-loss
operation without a canonical `strategy_id`, `decision_id` and `signal_id`.
The check runs before a simulated trade is stored or an execution callback is
invoked.

## Scope

- Apply the shared canonical-order provenance policy to paper market, limit and
  stop-loss methods.
- Reject incomplete calls before reading prices, calculating fees or writing a
  local paper trade.
- Keep grid aliases rejected by the shared strategy policy.
- Preserve the current non-authorizing configuration: no paper capital,
  promotion or live activation is introduced.

## Validation

```text
$env:PYTHONPATH='src'; python -m pytest \
  tests/test_paper_trading.py \
  tests/test_position_exit_and_allocation.py \
  tests/test_signal_handler_async_unit.py -q
47 passed

python -m compileall -q src
git diff --check
```

The paper tests cover each order type with a missing decision and a missing
signal; each case produces no row in the paper-trade store.

## Remaining Work

This does not make the legacy paper fill model production-realistic. Partial
fill handling, reconciliation and transaction-cost attribution remain blocked
behind the existing Block 5/6 gates.
