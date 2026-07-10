# AUTOBOT Foundation

## Official pipeline

`MarketData -> Signal -> OpportunityScore -> PortfolioAllocation -> RiskCheck -> ExecutionCommand -> Fill -> Position -> PnL -> Ledger -> Dashboard`

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
- `OrderEvent`
- `FillEvent`
- `PositionSnapshot`
- `LedgerEntry`

Existing runtime classes remain compatible. New integrations must either use a
contract directly or add an explicit adapter with a contract test.

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

| Layers | Current status | Block target |
| --- | --- | --- |
| 1-4 Data, quality, temporal semantics, lineage | PARTIAL | Block 1 |
| 5-6 Feature registry and regime analysis | PARTIAL | Block 1 |
| 7-10 Hypotheses, adapters, memory, experiments | PARTIAL | Block 2 |
| 11-12 Statistical validation and multiple testing | PARTIAL | Block 2 |
| 13-17 Portfolio, sizing, costs, capacity, simulation | PARTIAL | Block 3 |
| 18-21 Governance, shadow, paper, independent risk | PARTIAL | Block 4 |
| 22-23 OMS/EMS, ledger, reconciliation and TCA | PARTIAL | Block 5 |
| 24 Monitoring, drift, security and resilience | PARTIAL | Block 6 |

`COMPLETE` means verified by integration tests and runtime evidence, not merely
that a file with a similar name exists.

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
