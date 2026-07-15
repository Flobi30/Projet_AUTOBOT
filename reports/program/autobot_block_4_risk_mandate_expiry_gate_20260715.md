# AUTOBOT Block 4 - Risk Mandate Expiry Gate - 2026-07-15

## Decision

`GO` for further research-only hardening. No execution mode changed and no
paper capital, live trading, promotion, leverage or sizing was enabled.

## Change

Immutable risk evidence is now time-bounded at the exact point where a future
shadow `OrderIntent` is built:

- mandate references require a timezone-aware ISO-8601 expiry;
- a new shadow intent is rejected when its artifact mandate has expired at the
  intent creation time;
- old artifacts remain readable for audit and reconciliation, but cannot be
  used as evidence for a fresh shadow intent after expiry.

This is a contract-only fail-closed check. It does not call an order router,
paper engine, exchange endpoint or runtime scheduler.

## Evidence

- Functional commit: `1060ee888c29389aca7ae9f5b769e7d9f7b97c84`.
- Expanded research/contracts/runtime-preview suite: `463 passed`.
- Python compilation and diff checks: passed.
- Isolated immutable VPS release suite: `1597 passed` in 70.68 seconds.
- The same four pre-existing pytest warnings remain in non-async tests marked
  with `asyncio` in `src/autobot/v2/tests/test_order_router.py`.
- VPS deployment rebuilt `autobot-v2`; source at the functional commit,
  `/health` healthy, WebSocket connected and 14 instances observed.
- Safety gates remain disabled: paper execution adapter, live confirmation,
  live strategy routing, automatic promotion and instance splitting.

## Residual scope

This expiration check protects new research/shadow intents only. It does not
change the legacy runtime execution path, which remains blocked for new direct
entries, nor does it authorize official paper execution or live trading.
