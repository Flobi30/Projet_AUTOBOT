# AUTOBOT Block 5 — research execution-evidence contract

## Decision

**GO — research-only.** This bounded change makes the market and cost evidence
used by the isolated shadow simulator survive in the immutable `FillEvent`
contract. It does not activate, import, route to, or persist through paper or
live execution.

## Scope

- Added `ExecutionEvidence` to the stable contracts boundary.
- Added optional `FillEvent.execution_evidence` while retaining backwards
  compatibility for existing six-field fills.
- The research simulator now emits exact market identity, point-in-time source
  provenance, reference/arrival price, bid/ask, snapshot fingerprints, cost
  model fingerprint, scenario and cost components with every accepted fill.
- Funding is explicitly `UNAVAILABLE` when the spot simulator does not model
  it; it is never recorded as a false zero.
- The evidence contract itself is hard-coded research-only and rejects any
  paper/live authorization flag.
- Updated the 24-layer coverage matrix for execution simulation and future TCA
  work.

## Invariants

- All timestamps are aware UTC and preserve event → available → ingestion
  ordering.
- A fill cannot predate the usable market evidence or disagree with its fee
  evidence.
- Snapshot and cost fingerprints must be SHA-256 digests.
- Cost components are finite and non-negative.
- `MODELED` funding must have an explicit value; `UNAVAILABLE` funding must
  remain `None`.
- The contract stays side-effect free. No router, paper engine, exchange API,
  ledger loader or runtime persistence path changed.

## Validation

Local checks executed after the patch:

```text
$env:PYTHONPATH='src'; python -m pytest tests/test_contracts.py tests/research/test_execution_simulator.py tests/research/test_contract_shadow_pipeline.py tests/research/test_oms_ledger.py tests/test_shadow_paper_adapter_safety.py -q
53 passed
```

Additional hermetic regression batches:

```text
tests/research in four bounded batches: 671 passed, 1 skipped
tests/paper + tests/risk: 90 passed
tests/ root files in four bounded batches: 528 passed
src/autobot/v2/tests excluding legacy test_order_executor.py: 612 passed, 5 skipped, 2 deselected
python -m py_compile src/autobot/v2/contracts.py src/autobot/v2/research/execution_simulator.py: passed
python -m json.tool docs/architecture/layer_coverage.json: passed
git diff --check: passed
```

The legacy `src/autobot/v2/tests/test_order_executor.py` intentionally forces
live-authorisation test flags and exceeds the terminal’s bounded result window
before a final verdict. It is unrelated to this research-only contract and is
not treated as passed. It must be isolated or refactored before any future
execution-authority work; no runtime or safety flag was changed here.

## Residual risk and next boundary

`ExecutionEvidence` is intentionally not yet written into the runtime paper
ledger. The next step must first define an independent append-only OMS/TCA
ledger contract and replay/reconciliation semantics; bridging this evidence to
paper/runtime without that audit would create an unsafe second source of truth.

Serialising a legacy `FillEvent` now includes an explicit
`execution_evidence: null`; its contract fingerprint therefore differs from a
pre-change fingerprint. Legacy records remain historical, and no fingerprint
is silently reused as if it proved the new execution evidence.

## Safety state

No paper capital, live trading, promotion, sizing, leverage or runtime order
path was changed. Grid remains retired/no-go.
