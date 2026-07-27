# AUTOBOT Block 5 — Shadow ledger cost integrity

## Decision

**GO — research/shadow only.**

This patch corrects the accounting boundary between the isolated execution
simulator and the append-only shadow OMS ledger. It does not create an order
path, activate paper capital, change a runtime flag, or alter sizing/leverage.

## Problem addressed

The research simulator expresses spread, slippage and latency through the
simulated fill price. The historical ledger reconstruction then also subtracted
those same price-impact components as cash costs. That double-counted execution
impact in reconstructed research PnL/cash, even though it was not a real
exchange ledger.

## Delivered boundary

- `ExecutionEvidence` distinguishes:
  - `NOT_APPLICABLE` funding for spot fills;
  - `MODELED` funding with an explicit value;
  - `UNAVAILABLE` funding for a derivative fill whose funding was not modeled.
- An evidence-carrying `FillEvent` is rejected unless its exact registered
  market, intent fingerprint, approved risk-decision identity and modeled
  fee/spread/slippage/latency values match the append-only ledger input.
- For evidence-carrying fills, reconstruction debits only explicit fees and
  modeled funding. Spread, slippage and latency remain represented once in the
  fill price.
- A derivative fill with unavailable funding is marked `INCOMPLETE`; it cannot
  create a TCA record that silently treats funding as zero.
- Historical fills without execution evidence preserve their legacy arithmetic
  for audit compatibility but are explicitly reported as `INCOMPLETE`, never as
  promotion-grade cost evidence.

## Explicit non-goals

- No runtime paper-ledger bridge.
- No reconciliation against a private exchange API.
- No paper capital, live execution, promotion, risk increase or Grid runtime.
- No claim that the simulator equals future executable performance.

## Validation

```text
$env:PYTHONPATH='src'; python -m pytest \
  tests/research/test_execution_simulator.py \
  tests/research/test_oms_ledger.py \
  tests/research/test_contract_shadow_pipeline.py \
  tests/test_contracts.py \
  tests/test_shadow_paper_adapter_safety.py -q
56 passed

python -m py_compile \
  src/autobot/v2/contracts.py \
  src/autobot/v2/research/execution_simulator.py \
  src/autobot/v2/research/oms_ledger.py
passed

python -m json.tool docs/architecture/layer_coverage.json
passed

git diff --check
passed
```

The focused tests prove: no double cash debit for evidence-carrying spot fills,
the persisted payload remains immutable, market/intent/risk/cost mismatches are
rejected, and unavailable derivative funding prevents false TCA completeness.

## Residual risks

- The research simulator has no modeled historical derivative funding charge
  yet; such fills remain cost-incomplete rather than being promoted.
- This is a hermetic research ledger. Any future runtime/paper integration
  requires a separate OMS and reconciliation audit.
- The VPS deployment is intentionally deferred until the isolated daily
  research collector finishes, so its image and data collection provenance are
  not interrupted.

## Safety state

`PAPER_TRADING=false`, live confirmation remains false, automatic promotion is
disabled, no private Kraken credentials are injected, and Grid remains retired.
