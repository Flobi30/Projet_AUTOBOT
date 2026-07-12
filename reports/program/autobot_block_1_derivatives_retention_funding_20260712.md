# AUTOBOT Block 1 — Derivatives Retention and Funding Refresh — 2026-07-12

## Decision

`GO` for bounded, public, research-only derivatives collection.

This is an incremental Block 1 gate.  It does **not** make the
`funding_basis` family eligible for shadow, paper, promotion, or live use.

## Delivered

- The 15-minute ticker collection now retains raw audit runs for seven days
  only after canonical data and the manifest have been written successfully.
- A separate daily `funding_refresh` systemd timer refreshes historical Kraken
  Futures funding without rewriting current ticker, basis, or open-interest
  observations.
- A funding-only refresh can reuse ticker/basis state only while that state is
  less than one hour old.  Stale state fails closed instead of being labelled
  current.
- Both jobs share one non-blocking lock and run with public endpoints only,
  no secrets, no order endpoint, a read-only container root, dropped Linux
  capabilities, and bounded CPU/RAM.

## Evidence

- GitHub / VPS commit: `618f08edb1f490073b50aef2cfa064cd73ca4ee7`
- Targeted isolated tests: `20 passed`
- Research non-regression suite: `350 passed`
- Python compilation inside the isolated test image: passed
- systemd unit verification: passed (apart from an unrelated host `snapd`
  compatibility warning)
- VPS funding-refresh smoke: successful at `2026-07-12T13:12:05+00:00`
  - funding history: `53,980` canonical rows
  - funding coverage: `2025-07-02T08:00:00+00:00` to
    `2026-07-12T13:00:00+00:00`
  - mapped assets: BTC, ETH, SOL, XRP, ADA, LINK
  - current OI/predicted funding/basis state: present and fresh
  - basis method: `MARK_INDEX_SAME_QUOTE`
- Runtime after deployment:
  - `autobot-v2`: healthy
  - `/health`: healthy; orchestrator running; WebSocket connected; 14 instances
  - CPU: 7.02%; memory: 87.69 MiB of 3 GiB; VPS disk: 15% used

## Safety Confirmation

- `LIVE_TRADING_CONFIRMATION=false`
- `PAPER_EXECUTION_ADAPTER_ENABLED=false`
- `STRATEGY_ROUTER_LIVE_ENABLED=false`
- `COLONY_AUTO_LIVE_PROMOTION=false`
- No private Kraken endpoint, order endpoint, paper-capital activation,
  promotion, sizing, leverage, or runtime order-path change was introduced.
- Grid remains retired/no-go.

## Remaining Gates

- Open-interest and basis histories are still too short for the configured
  forward-history gate.  `funding_basis` remains `WAITING_FOR_MORE_DATA`.
- Derivatives point-in-time feature snapshots must be bound to reproducible
  experiments before any alpha family can be assessed.
- The tracked runtime research-memory/report artefacts on the VPS remain a
  separate cleanup/migration item; they were preserved and never reset during
  this deployment.

## Next Action

Bind point-in-time derivatives features to the experiment registry and
validation gates, while preserving research-only and shadow-only boundaries.
