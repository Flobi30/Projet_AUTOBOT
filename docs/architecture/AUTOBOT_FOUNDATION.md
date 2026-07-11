# AUTOBOT Foundation

## Official pipeline

`MarketData -> Signal -> OpportunityScore -> PortfolioAllocation -> OrderIntent -> RiskCheck -> ExecutionCommand -> Fill -> Position -> PnL -> Ledger -> Dashboard`

The dashboard is read-only with respect to trading truth. A strategy may create
signals, but it may not create fills, modify capital, or bypass risk checks.

## Versioned boundary contracts

`autobot.v2.contracts` defines side-effect-free contracts used for all new
cross-layer work:

- `CanonicalMarketEvent`
- `FeatureValue`
- `AlphaSignal`
- `TargetPortfolio`
- `OrderIntent`
- `RiskDecision`
- `ExecutionCommand`
- `OrderEvent`
- `FillEvent`
- `PositionSnapshot`
- `LedgerEntry`

`OrderIntent` is deliberately non-executable. Only a distinct `RiskDecision`
can produce an `ExecutionCommand`; a fast cache never carries a prior risk
approval. Existing runtime classes remain compatible. New integrations must
either use a contract directly or add an explicit adapter with a contract test.

## Source-of-truth rules

| Fact | Owner |
| --- | --- |
| Market event and market identity | canonical data layer |
| Feature value and availability time | feature registry |
| Signal and strategy version | research/strategy layer |
| Target weights and exposure | portfolio allocator |
| Approval, reduction or rejection | risk layer |
| Order lifecycle and fills | order state machine/executor |
| Positions, PnL and audit history | append-only ledger and reconciliation |
| Displayed health and metrics | monitoring/dashboard reader |

No component may infer quote currency, symbol mapping, or event availability
time. These facts must be explicit in the relevant contract.

## 24-layer coverage baseline

The machine-readable matrix is `docs/architecture/layer_coverage.json`.
Every row identifies an owner, boundary contract, test and evidence path.
`VERIFIED` means an integration test and runtime evidence, not merely a file
with a similar name. The initial status is deliberately conservative.

## Runtime artifact policy

Version control keeps code, configuration schemas, compact final reports and
reproducibility manifests. Runtime-generated files remain local to the VPS:

- SQLite WAL/SHM files and databases;
- container/server backups and cleanup archives;
- large daily walk-forward outputs and raw snapshots;
- transient paper diagnostics and scheduler outputs.

A compact Markdown/JSON summary must be committed only when it supports a
research decision, deployment proof or reproducibility requirement.

## Safety baseline

Blocks 0-5 are research and shadow only. They must not enable live trading,
paper capital, automatic promotion, sizing/leverage changes or runtime order
submission.
