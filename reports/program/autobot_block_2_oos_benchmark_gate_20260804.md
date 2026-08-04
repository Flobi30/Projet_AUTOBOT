# AUTOBOT Block 2 - OOS benchmark gate - 2026-08-04

## Verdict

**GO - research-validation hardening only.** A specialised walk-forward cannot
report `KEEP_RESEARCH` unless its closed, attributed out-of-sample trades beat
three explicit net references measured over the same bounded OOS evidence.

## Delivered behaviour

- Funding/basis and volatility-reversal walk-forward reports now include an
  immutable `OOSBenchmarkReport`.
- The references are: no-trade, one buy-and-hold position per symbol over the
  bounded OOS window, and a deterministic same-symbol/placebo sample with the
  candidate trade count, notionals, explicit costs and holding durations.
- Candidate PnL must reconcile exactly with its closed entry/exit prices and
  explicit fees, spread, slippage and latency costs before any comparison.
- A missing closed-bar reference, incomplete OOS evidence, or a candidate that
  fails to beat every reference blocks the walk-forward decision.
- Reports remain strictly research-only: this change creates no signal, order,
  fill, paper-capital, promotion or live path.

## Validation

- `python -m compileall -q src`: passed.
- Focused OOS benchmark, funding/basis, volatility-reversal and runner suite:
  `29 passed`.
- Direct contract suite after the final review change: `16 passed`.
- The broader research and CLI suite was executed after the focused tests; no
  failing test output was observed during collection and execution. Its final
  aggregate result will be rechecked in the isolated VPS test image before
  deployment.
- `git diff --check`: passed (only repository line-ending notices).

## Residual limits

This is a conservative comparator, not a portfolio/capacity simulation or a
profitability claim. Small samples, trial-count controls, sealed holdouts,
stress validation and every existing capital gate remain mandatory.

## Next gate

Run the hermetic full test image, then deploy this research-only validation
change to the VPS and confirm the program execution lock, paper/live flags and
observation-only runtime are unchanged.
