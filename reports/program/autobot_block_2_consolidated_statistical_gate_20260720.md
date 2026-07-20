# AUTOBOT Block 2 - Consolidated statistical gate - 2026-07-20

## Verdict

**GO - research-validation hardening only.** Funding/basis research can no
longer report `KEEP_RESEARCH` from its stress stage unless one consolidated,
non-promotional statistical summary independently accepts all of the supplied
out-of-sample evidence.

## Delivered behaviour

- The funding/basis statistical validation now derives a
  `StatisticalGateSummary` from the same fixed OOS trade records, explicit
  trial count, net PnL, cost attribution, PSR proxy, DSR proxy, and robustness
  report.
- The runner consumes that summary in `STRESS_MONTE_CARLO` and blocks the gate
  when the summary is not `SHADOW_REVIEW_ELIGIBLE`, even if a legacy validation
  decision would otherwise read `KEEP_RESEARCH`.
- The report persists the complete gate payload and its blockers as a research
  artifact. A favourable verdict remains research-only and can only make a
  later human shadow review conceivable.
- A missing walk-forward result retains the existing fail-closed
  `walk_forward_gate_not_passed` behaviour.

## What this does not do

- It does not generalize the funding/basis contract to unrelated strategy
  families; they need a common OOS trade-evidence contract first.
- It does not materialize a final holdout where the point-in-time data is still
  insufficient.
- It does not activate shadow, paper capital, live, promotion, sizing, leverage
  or an order path.

## Validation

- Statistical summary, funding/basis validation, walk-forward, and alpha-runner
  suite: `27 passed`.
- The added contract test proves a mocked legacy `KEEP_RESEARCH` result is
  converted to `REJECTED` when the consolidated statistical gate is blocked.
- `python -m compileall -q src`: passed.
- `git diff --check`: passed.

## Residual risks / next gate

The DSR/PSR diagnostics remain explicitly labelled proxies, not profitability
claims. The next validation improvement should count trials across a shared
research campaign rather than only within a single hypothesis, while preserving
the physical holdout gate and the research-only boundary.
