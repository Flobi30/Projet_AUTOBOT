# AUTOBOT Block 3 - Canonical Microstructure Cost and Capacity Evidence

Date: 2026-07-20

## Decision

GO for continued forward research collection and read-only cost/capacity
profiling. The layer remains PARTIAL. No strategy is eligible for shadow,
paper capital, promotion, or live execution from this evidence.

## Delivered

- Added a read-only canonical microstructure profiler.
- It reads only canonical Kraken EUR spot top-of-book snapshots.
- It validates explicit market mapping, UTC temporal order, quote currency,
  top-of-book consistency, and source-id conflicts.
- It deduplicates exact economic duplicates across snapshots.
- It reports observed spread, top-of-book depth, latency, cross-session
  coverage, and explicit reasons for insufficient evidence.
- It never writes an execution cost configuration or a capacity/sizing
  decision.
- Added CLI command: python -m autobot.v2.cli profile-canonical-microstructure

## Coverage Gate

Default per-symbol requirements are deliberately conservative:

- 96 observations;
- 12 distinct UTC hours;
- 24-hour minimum observation span.

The only research-ready status is RESEARCH_CALIBRATION_READY. It still has:

- runtime_parity_proven=false;
- execution_eligible=false;
- no automatic cost-model update;
- no order, paper-capital, promotion, or live authority.

Invalid or conflicting source rows produce
DATA_QUALITY_REVIEW_REQUIRED at report level instead of a misleading ready
status.

## Local Evidence

Implementation commit: 46a347470e805d26df662f8b1d7f65e868df0105.

Validated locally:

- focused boundary, cost, portfolio, simulator, and CLI tests: 74 passed;
- full regression: 1736 passed, 6 skipped;
- python -m compileall -q src;
- git diff --check;
- staged-diff secret scan: clean;
- layer coverage JSON parses successfully.

## VPS Evidence

Git checkout and runtime image revision were both:

46a347470e805d26df662f8b1d7f65e868df0105.

After provenance rebuild:

- container health: healthy;
- health endpoint: healthy;
- orchestrator: running;
- WebSocket: connected;
- instances: 14;
- forward microstructure timer: enabled and active;
- no matching traceback, critical, live-order, or live-activation log in the
  final ten-minute filter.

Read-only smoke:

- 28 accepted canonical observations;
- 14 symbols;
- profile status: WAITING_FOR_MORE_DATA;
- every symbol status: WAITING_FOR_MORE_DATA;
- runtime parity: false;
- execution eligibility: false.

Safety flags remained unchanged:

- LIVE_TRADING_CONFIRMATION=false;
- STRATEGY_ROUTER_LIVE_ENABLED=false;
- COLONY_AUTO_LIVE_PROMOTION=false;
- ENABLE_INSTANCE_SPLIT_EXECUTOR=false.

PAPER_TRADING=true was pre-existing runtime configuration. This block did not
activate paper capital, create an order, change sizing or leverage, or enable
any promotion.

## Residual Risks and Next Gate

- Public REST top-of-book samples are not runtime-feed parity evidence.
- The present sample does not yet meet coverage requirements and must not
  influence a cost configuration automatically.
- Top-of-book depth is not a full order-book or market-impact model.

Next safe work: continue the bounded timer collection, then audit the
research-only cost and capacity bridge against a sufficiently covered canonical
profile. No strategy or capital path should be changed before that gate.
