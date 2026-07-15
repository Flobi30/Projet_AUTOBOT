# AUTOBOT Block 4 - Immutable Risk Mandate Binding - 2026-07-15

## Decision

`GO` for further research-only hardening. No shadow service was started. No
paper capital, live route, automatic promotion, leverage or sizing change was
enabled.

## Change

Shadow-capable strategy artifacts now carry immutable, non-authorizing risk
mandate evidence in addition to their point-in-time feature evidence and final
holdout evidence.

- The mandate fingerprint is derived from the complete versioned mandate, not
  from a caller-provided label.
- The artifact and its order-intent reference require the mandate strategy id
  and fingerprint to match exactly.
- The artifact-registration CLI resolves a named mandate from a supplied
  versioned mandate file and rejects a caller-supplied fingerprint mismatch.
- The mandate reference cannot authorize paper capital or live trading.
- The research pre-trade gate fails closed when a mandate is expired, malformed
  or lacks a timezone-aware expiry.

The shadow runtime remains a non-executable preview. This work adds no router,
broker, paper engine or exchange import to the research governance path.

## Evidence

- Functional commit: `d0664602f0fdee2d49951afc930595d4b4464297`.
- Focused contracts, governance, risk, CLI, simulator, ledger and runtime
  preview suite: `107 passed`.
- Expanded research/contracts/runtime-preview suite: `462 passed`.
- Python compilation and diff checks: passed.
- Isolated immutable VPS release suite: `1596 passed` in 70.63 seconds.
- The same four pre-existing pytest warnings remain in non-async tests marked
  with `asyncio` in `src/autobot/v2/tests/test_order_router.py`.
- VPS deployment rebuilt `autobot-v2`; source at the functional commit,
  `/health` healthy, WebSocket connected and 14 instances observed.
- Safety gates remain disabled: paper execution adapter, live confirmation,
  live strategy routing, automatic promotion and instance splitting.

## Residual scope

The immutable reference proves which zero-capital research/shadow mandate was
reviewed. It does not authorize execution and it is not a substitute for the
independent runtime risk engine, reconciliation, human approval or future
paper review. Existing strategies remain research/shadow-only and grid remains
retired.
