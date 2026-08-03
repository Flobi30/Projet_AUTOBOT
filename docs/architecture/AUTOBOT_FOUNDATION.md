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

## Multi-signal portfolio shadow review

`portfolio_shadow_review` is the research-only gate between a set of accepted
`AlphaSignal` values and any later order-oriented boundary. It creates one
deterministic `TargetPortfolio`, requires every accepted component to pass the
same pessimistic cost scenario, then requires fresh, explicit-market capacity
evidence for every final target exposure.

Its only positive result, `PORTFOLIO_SHADOW_READY`, is still non-executable:
it cannot create an `OrderIntent`, a fill, a paper allocation or a live
permission. An invalid input signal remains an auditable target rejection;
missing capacity or one component failing pessimistic costs blocks the entire
target rather than allowing a partial unreviewed portfolio through.

## Feature-drift evidence

The shadow safety policy accepts a feature-drift score only when it is derived
from `VerifiedFeatureVector` values. `assess_verified_feature_drift` requires
one explicit market, timeframe, feature version, feature-registry fingerprint
and fixed histogram bins; every vector must have been available by the stated
assessment time. Missing evidence produces `WATCH`, while an adverse score can
only reduce, disable new entries or quarantine an artifact. It can never relax
risk, promote a strategy, enable paper capital or enable live trading.

## Hermetic OMS time ordering

The research/shadow OMS ledger requires a strictly chronological contract
sequence: the risk decision cannot predate its registered intent; each new
order event must follow the previous order event; and each fill must follow an
acknowledged, partial or recovered-unknown state. Out-of-order evidence is
rejected before it can influence state reconstruction, reconciliation or TCA.
This remains a hermetic research model, not the runtime order router.

## Runtime resilience WebSocket evidence

The isolated runtime-resilience audit cannot declare a WebSocket healthy from a
plain `connected` string. A connected observation carries a UTC observation
time and is accepted only within the configured freshness window (60 seconds by
default). Missing, future or stale evidence produces the existing fail-closed
`WEBSOCKET_DISCONNECTED` incident; `unknown` remains partial observability.
The monitor is still read-only, network-isolated from exchanges and unable to
enable paper capital, live execution or any order path.

The controlled deployment-evidence verifier separately re-checks the exact
container identity, image, health endpoint and connected WebSocket immediately
before it emits its non-secret evidence record. It refuses a container swap or
a health change during slower authorization checks rather than reusing earlier
startup evidence.

## Offline shadow-provenance boundary

`offline-shadow-provenance-bind` is the only supported v1 batch hand-off from
one registered `SHADOW_ELIGIBLE`/`SHADOW` artifact to one published,
material-verified canonical feature vector. It re-reads the artifact registry
in SQLite read-only mode, re-verifies the feature publication, requires the
decision time to equal the vector availability time and refuses a stale,
mismatched or over-mandate bind. Its result is metadata for a *blocked*
shadow-preview test only: it cannot start the runtime, create an order, enable
paper capital, promote a strategy or enable live trading.

`DerivativesSpotResearchContext` now provides the corresponding multi-source
research boundary for one explicit Kraken Futures perpetual and one explicit
AUTOBOT spot market. It requires a material-verified, forward-only derivative
bundle, a manifest-sealed futures-to-spot mapping, the same base asset and one
common observation time. It never converts a perpetual USD price to EUR; the
spot vector remains the only future source of EUR PnL, costs and capacity.
`bind_offline_derivatives_spot_shadow_provenance` is the corresponding
batch-only artifact hand-off. It accepts the context only when its two exact
vectors, their versions, the sealed mapping and the artifact's combined data
identity agree. The runtime preview independently reconstructs that context
before producing its still-blocked result. The shadow ledger can record the
same two vectors as research evidence, but paper/live permissions and the
risk decision remain false.

## Shadow-artifact readiness audit

`strategy-artifact-readiness-audit` is a read-only companion to the artifact
registration command. It reports each experiment's latest gate, terminal
state, immutable final-holdout evidence, registered artifact statuses and the
remaining blockers. It opens both SQLite registries in read-only mode and
intentionally reports a missing or legacy schema instead of initializing or
migrating it. A result named `EVIDENCE_READY_HUMAN_GOVERNANCE_REQUIRED` means
only that research evidence is complete enough for a human to consider an
immutable shadow artifact; it is not an authorization. A current shadow-only
risk mandate and an explicit human approval reference remain mandatory, while
paper capital, live, automatic promotion, runtime start and order creation all
remain false. Deployment evidence is recorded in
`reports/program/autobot_shadow_artifact_readiness_20260722.md`.

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

## Material research-data retry gate

`research-retry-eligibility` is a read-only evidence gate for a *possible new*
research campaign. It compares the explicit missing-data reasons from a
terminal record with a deterministic funding/basis/OI capability signature. It
does not alter research memory, the experiment registry, scheduler state,
claims, trials or holdouts; it cannot start a runner. A prior performance
rejection remains blocked even if later data coverage grows. Only a terminal
`DATA_MISSING`/`INSUFFICIENT_DATA` record with a demonstrated required
capability transition can make a separately named campaign eligible for
registration. The successor must carry the prior trial-count floor and pass
the normal data, net-cost, walk-forward, stress and final-holdout gates.

Changing a campaign label, report name, run id or data path alone never makes
a retry eligible. The gate does not enable shadow, paper capital, live,
promotion, sizing, leverage or an order path.

When a later research campaign is legitimately registered as a successor, its
`ExperimentSpec` must bind the predecessor experiment id, a strictly different
material-data signature and a predecessor candidate-trial floor. The registry
accepts only a terminal `INSUFFICIENT_DATA` predecessor with the same hypothesis
and template; a performance rejection is never a successor source. Campaign
validation includes the inherited floor, so changing campaign id cannot reduce
the multiple-testing correction.

The former threaded `Orchestrator` and `TradingInstance` modules are retained
only for passive import and historical type compatibility. Their constructors
are permanently `retired_from_execution` and fail before initializing a Kraken
client, websocket, persistence store or signal handler. `main_async.py` and
`OrchestratorAsync` are the sole supported runtime entrypoints.

The active async runtime is likewise observation-only. Its instance factory
records any requested historical strategy name but replaces it with the
non-signalling observation strategy. A future canonical shadow-artifact
consumer must be implemented and separately verified before a runtime strategy
can emit signals; configuration alone cannot bypass that gate.

## Registry-bound statistical validation

Every passed `STRESS_MONTE_CARLO` transition must carry a
`StatisticalValidationArtifact`.  The artifact is built from the append-only
experiment registry after its bounded candidate plan has been recorded.  Its
effective multiple-testing count may be stricter than the registry floor, but
it can never be lower.  The registry re-computes the floor and rejects a
mismatched experiment, scope, fingerprint or count before recording the gate.

This is evidence for research only.  It cannot create a strategy artifact,
start shadow runtime, increase risk, enable paper capital, promote a strategy
or enable live trading.

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

`PROGRAM_EXECUTION_LOCKED` is the code-level enforcement of that scope.  It
keeps the active runtime observation-only and rejects private order mutations
even if a legacy deployment supplies every former paper/live environment flag.
Lifting it is a separately reviewed source change, never an environment-only
operation.
