# AUTOBOT — Bloc 1 regime-trial registry — 2026-07-26

## Decision

`GO_RESEARCH_ONLY`.

Implementation commit: `142eaffeab7f4f5d8a3d26ee589d19a8c81d7d3e`.

A bounded market-regime segmentation is now an explicit, snapshot-bound
experiment trial. This closes a multiple-testing gap: selecting a regime split
can no longer be recorded only in a side JSONL log while leaving the
statistical trial count unchanged.

## Behaviour

- `ExperimentRegistry.record_regime_segmentation_trial()` records the
  segmentation ID, version, ordered labels, fingerprint and parent snapshot.
- The parent experiment must be non-terminal and use the same snapshot.
- Repeating the identical registration is idempotent.
- Regime-segmentation trials contribute to the conservative validation trial
  count and successor campaign floor alongside crossed candidate
  configurations.
- The authoritative helper is research-only and cannot start a runtime,
  create a paper fill, promote a strategy or alter a risk mandate.
- The older JSONL helper remains archival compatibility evidence only; a
  validation workflow must use the experiment-registry helper.

## Validation

- contract tests for regime enrichment and experiment registry: `24 passed`;
- bounded runner and regime-validation regression suite: `38 passed`;
- research suite: `660 passed, 1 skipped`;
- full suite: `1900 passed, 6 skipped, 2 deselected`;
- Python compilation and `git diff --check`: passed.

## Safety

- no strategy, alpha threshold, feature value or cost is changed;
- no network collector, scheduler or runtime order path is touched;
- no live, paper-capital, promotion, sizing or leverage flag changes;
- Grid remains retired/no-go.

## VPS deployment evidence

The implementation and evidence report were deployed through the controlled
image rebuild. GitHub, the VPS source checkout and the `autobot-v2` image all
resolved to `efa580dbc7a6c204144c183db26301b2b9cde137` during validation.

- container: `running`, `healthy`, read-only root filesystem, zero restarts;
- health endpoint: orchestrator running and WebSocket connected;
- runtime: one intentionally bounded observation instance;
- observation-only runtime enabled; paper trading, both paper execution
  adapters, live confirmation/router and auto-promotion disabled;
- private Kraken credential environment count: zero;
- recent critical/paper-order/live-order log count: zero.

## Remaining boundary

This establishes auditable counting when a validation workflow elects to use a
bounded segmentation. It does not authorize additional regime slicing, and it
does not claim that the currently collected derivative data is sufficient for
a funding/basis test.
