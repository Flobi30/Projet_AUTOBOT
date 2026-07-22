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

## Offline shadow-provenance boundary

`offline-shadow-provenance-bind` is the only supported v1 batch hand-off from
one registered `SHADOW_ELIGIBLE`/`SHADOW` artifact to one published,
material-verified canonical feature vector. It re-reads the artifact registry
in SQLite read-only mode, re-verifies the feature publication, requires the
decision time to equal the vector availability time and refuses a stale,
mismatched or over-mandate bind. Its result is metadata for a *blocked*
shadow-preview test only: it cannot start the runtime, create an order, enable
paper capital, promote a strategy or enable live trading. Multi-source
spot/derivatives hand-offs remain blocked until they can prove one coherent
common observation time.

## Legacy runtime signal provenance inventory

`audit-runtime-signal-provenance` performs a static AST-only inventory of
`TradingSignal` constructors. It neither imports a strategy nor reads runtime
state, and it cannot start shadow, paper or live execution. The audit treats
literal key presence as *unverified* because a valid shadow preview still
requires an immutable artifact, one exact published feature vector and a
current mandate.

The 2026-07-22 baseline found 14 constructors: ten belong to retained Grid
research sources and remain inventory only; the two actionable trend BUY
producers lack canonical provenance (`trend.py`) or build dynamic local
metadata (`trend_async.py`). They remain blocked by the direct-entry quarantine.
The next integration may only consume a separately verified canonical hand-off;
it must not fill missing runtime metadata by guessing values.

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
