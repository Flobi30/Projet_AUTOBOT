# AUTOBOT Block 4 - Legacy promotion quarantine - 2026-07-20

## Verdict

**GO - governance hardening only.** The legacy shadow manager can no longer
promote an instance or mutate capital, regardless of its displayed profit
factor, age, or trade count.

## Finding

`ShadowTradingManager` was no longer used by the asynchronous orchestrator, but
its public compatibility methods could still return a live-promotion decision
and transition an instance to `PROMOTED` while altering `paper_capital`. That
contradicted AUTOBOT's research/shadow-only program and the explicit ban on
automatic promotion.

## Delivered behaviour

- `should_promote_to_live()` now always returns `False` after validating the
  referenced instance. Numeric performance remains research evidence only.
- `transfer_capital()` now always returns `False` after validating the
  referenced instance. It never changes capital, timestamps, or state.
- A high PF, a completed legacy validation period, and a high trade count cannot
  create `PROMOTED` through this legacy API.
- The current strategy-artifact workflow remains the only path that can express
  a future human-review recommendation; it remains non-authorizing.
- The embedded manual test runner now uses portable ASCII result markers.

## Validation

- Embedded legacy manager runner: `35 passed, 0 failed`.
- Targeted shadow, production-safety, adapter-safety, and governance suite:
  `62 passed`.
- Full repository suite: `1790 passed, 6 skipped`.
- `python -m compileall -q src`: passed.
- `git diff --check`: passed.

## Safety invariants

- No paper capital was activated.
- No live trading was activated.
- No strategy was promoted.
- No sizing, leverage, order-routing, or dashboard behaviour changed.
- Grid and other retired strategies remain outside runtime execution.

## Residual risks / next gate

This closes a legacy mutation path; it does not qualify any strategy. The next
research gate remains a common statistical summary connected to the real
validation runner, with data-driven holdout requirements preserved.
