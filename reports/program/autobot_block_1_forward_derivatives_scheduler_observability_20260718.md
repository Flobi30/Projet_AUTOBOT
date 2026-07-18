# AUTOBOT Block 1 — Forward Derivatives Scheduler Observability — 2026-07-18

## Decision

`GO` for a bounded research-observability increment. This does not make a
derivatives hypothesis runnable, does not change a rejected experiment, and
does not authorize shadow, paper capital, promotion or live trading.

## Change

- The alpha-hypothesis scheduler can now receive one explicit forward-capture
  derivatives feature manifest and reports its verified status separately from
  historical research capability.
- The daily research service selects only the latest
  `derivatives_forward_*_derivatives_feature_snapshot.json` artifact and passes
  it as scheduler/coordinator observability evidence. It never passes that
  artifact as runner market data.
- An invalid manifest is represented as `INVALID` with fail-closed flags rather
  than being interpreted as data readiness.
- A forward snapshot remains informational: historical data may support an
  offline research gate, while only accumulated forward-capture evidence can
  later contribute to runtime-parity review.

## Verification

- Focused scheduler, coordinator, derivatives-feature and deployment suite:
  `45 passed`.
- Full repository non-regression suite: `1717 passed, 6 skipped`.
- Python compilation and `git diff --check`: passed.

## Safety

- The scheduler and coordinator remain research-only and isolated from order
  routing, paper execution and private exchange APIs.
- The forward manifest cannot change a candidate status, override a terminal
  rejection or bypass the experiment registry.
- Paper capital, live trading, automatic promotion, sizing and leverage remain
  disabled and unchanged.

## Remaining Gate

Continue forward collection until a material window is available. Existing
rejected funding/basis configurations remain terminal until a genuinely new
data fingerprint or pre-registered thesis is supplied. This change only makes
that waiting state explicit in the daily evidence trail.
