# AUTOBOT Blocks 1 and 6 — VPS operational validation — 2026-07-16

## Verdict

GO.  The two operational blockers found during the foundation audit are
resolved and verified on the VPS.  AUTOBOT remains research/shadow only.

## Commits

- `e7d94ccf23321a7bf56609f1e8dcbb380c5ee9fb` — early decision-learning
  observation after a restart.
- `4a20c108081c17b999af9a94e8ca573ca65ac923` — bounded derivatives history
  compaction.

GitHub, VPS checkout and runtime image were verified on `4a20c108`.

## Startup freshness proof

After a controlled container restart, the cold-path decision-learning refresh
recorded 30 market samples after 30 seconds.  The independent read-only
resilience audit then reported:

- `RESILIENCE_HEALTHY`;
- SQLite integrity `ok`;
- WebSocket `connected`;
- no incidents;
- fresh market data, 85 seconds old at audit time.

## Funding collector proof

The scheduled public funding refresh previously failed with exit 137 because
the collector exceeded its 512 MiB memory cgroup limit while reloading the
entire immutable archive.  After incremental compaction, the same six-asset
funding refresh completed with systemd `status=0/SUCCESS` under the unchanged
512 MiB limit.  No OOM evidence appeared after the successful run.

## Runtime state

- container `autobot-v2`: healthy;
- `/health`: orchestrator running, WebSocket connected, 14 instances;
- runtime resilience timer: active;
- more than 57 GiB free disk;
- `PAPER_EXECUTION_ADAPTER_ENABLED=false`;
- `LIVE_TRADING_CONFIRMATION=false`;
- `STRATEGY_ROUTER_LIVE_ENABLED=false`;
- `COLONY_AUTO_LIVE_PROMOTION=false`;
- `ENABLE_INSTANCE_SPLIT_EXECUTOR=false`.

## Safety confirmation

No paper capital, live trading, promotion, sizing, leverage or order path was
enabled or invoked.  The derivatives collector used public market-data
endpoints only; it has no private API, secret or runtime-state database mount.

## Next gate

The data plane is operationally stable enough to continue research.  The
existing funding/basis material experiment remains `INSUFFICIENT_DATA` and
does not qualify any strategy for shadow promotion.
