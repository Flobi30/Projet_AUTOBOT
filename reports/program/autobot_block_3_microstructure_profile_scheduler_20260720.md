# AUTOBOT Block 3 - Isolated Canonical Microstructure Profile Scheduler

Date: 2026-07-20

## Decision

GO for ongoing research-only profiling. The automatic report remains evidence
only. It cannot modify cost assumptions, capacity, strategy status, paper
capital, promotion, or live execution.

## Delivered

- A daily systemd timer for canonical microstructure profiling.
- An isolated container job with no network access.
- Read-only mount of the full research-data input tree.
- A nested writable mount limited to
  data/research/reports/canonical_microstructure_profiles.
- Immutable-image provenance check against the checked-out Git commit.
- Locking, resource limits, no-new-privileges, dropped Linux capabilities,
  read-only root filesystem, and temporary filesystem only.
- No environment file, runtime database, API key, order router, or paper/live
  surface is mounted or imported.

## Local Evidence

Implementation commit: 08aecf0eb57c9ecc878fe0d732dcd57b3ec3cbef.

Validated locally:

- shell syntax check for the service script;
- deployment isolation tests;
- targeted cost, capacity, canonical-data, and profile tests: 26 passed;
- full regression: 1737 passed, 6 skipped;
- Python compile check;
- JSON architecture matrix parse;
- diff validation and staged secret scan.

## VPS Evidence

The systemd profile service and timer were installed and enabled. A manual
service smoke completed with Result=success and ExecMainStatus=0.

Git checkout and image revision were both:

08aecf0eb57c9ecc878fe0d732dcd57b3ec3cbef.

The smoke report contained:

- 364 accepted observations;
- 14 EUR spot symbols;
- status WAITING_FOR_MORE_DATA;
- all per-symbol statuses WAITING_FOR_MORE_DATA;
- runtime parity false;
- execution eligibility false.

The result is expected: the coverage gate still requires cross-session
evidence. No observed spread or depth value is automatically injected into the
cost model.

Runtime verification after deployment:

- container health: healthy;
- health endpoint: healthy;
- orchestrator: running;
- WebSocket: connected;
- instances: 14;
- forward collector timer: enabled and active;
- profile timer: enabled and active;
- no matching traceback, critical, live-order, or live-activation log in the
  final ten-minute filter.

Safety flags remained unchanged:

- LIVE_TRADING_CONFIRMATION=false;
- STRATEGY_ROUTER_LIVE_ENABLED=false;
- COLONY_AUTO_LIVE_PROMOTION=false;
- ENABLE_INSTANCE_SPLIT_EXECUTOR=false.

PAPER_TRADING=true is pre-existing runtime configuration. This block did not
activate paper capital, submit an order, alter sizing or leverage, or promote
any strategy.

## Residual Risks

- Public REST top-of-book observations are not runtime-feed parity proof.
- Top-of-book depth is not a full book/market-impact model.
- The data does not yet satisfy the profile coverage gate.
- The service intentionally fails on a code/image provenance mismatch.

Next safe work: continue collection while auditing remaining batch-only
research controls and the non-authorizing OMS/ledger migration boundary. No
strategy or capital path should change from this report.
