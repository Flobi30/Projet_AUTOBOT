# AUTOBOT — Bloc 3/4 shadow provenance and timing — 2026-07-26

## Decision

`GO_RESEARCH_ONLY`.

Implementation commit: `b4b5b04e6821d30247da9d5404b4168c7d79f21c`.

This hardening addresses three research-shadow failure modes found during an
independent architecture audit. It does not enable a runtime shadow strategy,
paper capital, live trading or an order path.

## Changes

- Shadow replay now starts its submission/latency window only after both the
  intent and its approved `RiskDecision` exist. A market snapshot available
  before risk approval cannot be filled retroactively.
- A partial fill explicitly records a `CANCELLED` remainder at the end of the
  bounded replay window. The simulator therefore cannot leave a synthetic
  working order ambiguous or reopen it using changed market evidence.
- Every non-cash target persisted to the shadow observation ledger must bind
  source signal ID, artifact strategy ID, source snapshot, exact feature
  versions and every investable market identity to the verified feature
  vectors. The same checks apply to manually constructed observations.

## Validation

- focused simulator, ledger, shadow-governance and contract pipeline suite:
  `61 passed`;
- final focused simulator/ledger/contract suite: `34 passed`;
- research suite: `663 passed, 1 skipped`;
- full suite: `1903 passed, 6 skipped, 2 deselected`;
- Python compilation and `git diff --check`: passed.

## Safety

- simulation remains research/shadow-only;
- all execution commands remain impossible in this path;
- no runtime router, executor or paper engine is imported;
- no data collector, strategy, threshold, sizing, leverage or risk flag is
  changed;
- no paper/live/promotion flag changes; Grid remains retired/no-go.

## Remaining boundaries

The simulator still consumes an already-created `RiskDecision`; the next
bounded improvement is to make that decision carry immutable evidence from
the pre-trade mandate gate. The generic `TargetPortfolio` contract also still
permits research-only legacy/current exposure representations; only a
ledgered non-cash shadow observation is executable-like enough to require the
new strict provenance checks.

## VPS deployment evidence

Deployment report commit: `fdf49a173d23146be9420fa7ecbdf6de60594b18`.

- GitHub `master`, VPS source checkout and the `projet_autobot-autobot` image
  were verified at the same commit.
- `autobot-v2` was `running` and `healthy`, with a read-only root filesystem
  and zero restart count.
- `/health` reported the orchestrator running, WebSocket connected and one
  intentionally bounded observation-only instance.
- `AUTOBOT_OBSERVATION_ONLY_RUNTIME=true`; every paper execution flag, every
  live flag and automatic promotion remained `false`.
- The running container had no private Kraken credential environment variable.
- The five-minute critical/order log scan found zero matching events.

This deployment did not start a strategy, an execution adapter, paper capital,
or a live order path.
