# AUTOBOT Block 5 — Execution-evidence to TCA adapter

## Decision

**GO — hermetic research/shadow adapter only.**

The isolated simulator can now feed a complete `TransactionCostAnalysis` from
the immutable `FillEvent.execution_evidence` it already emits. This is not an
order, paper, runtime or exchange integration.

## Design

- `build_tca_from_execution_evidence(intent, fill, signal_price, decision_price)`
  is a pure adapter in the research OMS module.
- It requires the caller to provide the signal and decision prices explicitly.
  Those prices are never guessed from mutable metadata or current market data.
- It re-verifies client-order identity, market identity, immutable intent
  fingerprint and fee evidence before creating TCA.
- Spot evidence produces an analytical funding value of zero only because the
  immutable evidence declares funding `NOT_APPLICABLE`.
- Derivative evidence marked `UNAVAILABLE` is rejected: no analytical record
  can silently treat unmodeled funding as zero.
- Legacy fills without `ExecutionEvidence` remain rejected by this adapter.

## Validation

```text
$env:PYTHONPATH='src'; python -m pytest \
  tests/research/test_execution_simulator.py \
  tests/research/test_oms_ledger.py \
  tests/research/test_contract_shadow_pipeline.py \
  tests/test_contracts.py \
  tests/test_shadow_paper_adapter_safety.py -q
59 passed

git diff --check
passed
```

The test chain uses an actual `ResearchExecutionSimulator` result and proves
that its bound market, arrival/fill prices and fees/slippage components reach
TCA unchanged. Separate tests reject legacy evidence, cross-market evidence
and unknown derivative funding.

## Safety state

The adapter has no route, executor, exchange-client, paper-wallet or runtime
persistence import. Paper capital, live trading and automatic promotion remain
disabled; Grid remains retired.

## Residual boundary

The adapter is intentionally not scheduled automatically. A later research
pipeline may call it only after it can supply point-in-time signal and decision
prices from an immutable signal record. Runtime/paper ledger integration remains
out of scope pending its separate OMS/reconciliation gate.
