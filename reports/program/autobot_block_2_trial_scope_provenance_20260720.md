# AUTOBOT Block 2 - Trial-scope provenance - 2026-07-20

## Verdict

**GO - research-validation provenance only.** Every funding/basis statistical
report now identifies the exact scope that supplied its multiple-testing
trial-count floor.

## Delivered behaviour

- `AlphaHypothesisRunnerConfig` can receive a normalized
  `validation_trial_scope_id`.
- Funding/basis statistical validation persists `trial_scope_id` beside the
  assumed trial count in both successful and fail-closed reports.
- The `STRESS_MONTE_CARLO` gate exposes that identity in its metrics.
- Bounded research and the CLI pass the explicit template-family campaign
  identifier created by the prior campaign-scope change.
- A standalone funding/basis run falls back to the explicit
  `hypothesis_funding_basis` scope; it does not imply a campaign it cannot
  prove.

## Safety boundary

This is report provenance only. It cannot activate shadow, paper capital,
live trading, promotion, sizing, leverage, or an order path.

## Validation

- Statistical, funding/basis, runner, registry, manifested-experiment,
  coordinator, and CLI tests: `95 passed`.
- Tests prove the explicit campaign scope survives the statistical report and
  gate metrics, including the walk-forward fail-closed path.
- `python -m compileall -q src`: passed.
- `git diff --check`: passed.

## Residual risk / next gate

The current shared OOS trade-evidence contract remains limited to the
funding/basis adapter. Other strategy families remain research-only and must
not borrow this gate until they provide equivalent point-in-time OOS evidence.
