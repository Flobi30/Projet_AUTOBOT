# AUTOBOT Block 2 — Statistical Evidence Trial Binding (2026-07-29)

## Decision

`GO_LOCAL_ONLY` — a passed `STRESS_MONTE_CARLO` transition now requires one
internally consistent, fingerprinted statistical evidence payload.

## Finding

The append-only experiment artifact already bound an effective trial count to
the registry floor.  The serialized DSR, PSR, robustness report and
consolidated statistical gate were only required to exist, however.  A caller
could therefore provide diagnostics calculated with a different sample or DSR
trial count while declaring a higher count on the outer artifact.

## Change

- Passed stress evidence now requires canonical PSR, DSR, robustness and
  statistical-gate mappings.
- Their sample counts must equal `trade_count`; DSR and gate trial counts must
  equal the immutable artifact's `assumed_trial_count`.
- The consolidated gate must be research-only, blocker-free and exactly
  `SHADOW_REVIEW_ELIGIBLE`; robustness remains
  `observation_ready_not_promoted`.
- The exact serialized evidence is fingerprinted before the append-only
  transition is identified and written. Retries must reproduce that fingerprint.
- Both funding/basis and volatility-reversal runner paths now carry the full
  consolidated statistical-gate mapping into the registry.

## Verification

```text
python -m compileall -q src tests
python -m pytest tests/research/test_experiment_registry.py \
  tests/research/test_shadow_governance.py \
  tests/research/test_strategy_artifact_cli.py \
  tests/research/test_alpha_hypothesis_runner.py \
  tests/research/test_funding_basis_statistical_validation.py \
  tests/research/test_volatility_reversal_statistical_validation.py \
  tests/research/test_statistical_gate_summary.py -q
git diff --check
```

Results:

- compilation: PASS;
- targeted Block 2 regression: `83 passed`;
- diff check: PASS.

New adversarial coverage rejects a DSR trial-count mismatch and a tampered
statistical-evidence fingerprint before the stress transition can be recorded.

## Safety and deployment

- research registry and research runner evidence only; no runtime router,
  executor, paper engine or exchange import added;
- no VPS/SSH action while Hetzner is unavailable;
- no paper capital, live execution, promotion, sizing or leverage change;
- Grid remains retired from execution.

## Residual risk

This binds the serialized diagnostics to a single immutable transition. It
does not turn PSR/DSR proxies into guarantees of future profitability, nor does
it replace the deferred human shadow review, data coverage or VPS runtime
evidence.
