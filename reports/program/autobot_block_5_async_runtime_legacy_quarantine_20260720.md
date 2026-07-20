# AUTOBOT Block 5.2 - Async Runtime Legacy Quarantine - 2026-07-20

## Verdict

**GO - research/shadow safety hardening only.** No paper-capital, live,
promotion, sizing, leverage, derivative or order-routing activation occurred.

## Scope

The production async runtime no longer imports the synchronous legacy instance,
orchestrator or reconciliation engines merely to obtain shared configuration,
model or divergence types. Those passive contracts now live in side-effect-free
modules, while the legacy modules retain compatibility re-exports for callers
that explicitly use them.

## Delivered behavior

- `InstanceConfig` is owned by `instance_config.py`.
- `InstanceStatus`, `LeverageLevel`, `Trade` and `Position` are owned by
  `instance_models.py`.
- `Divergence` is owned by `reconciliation_models.py`.
- `main_async` and its async runtime dependency closure import only these
  passive contracts, not the synchronous legacy engines.
- A subprocess boundary test proves that importing `main_async` does not load
  `orchestrator`, `instance` or `reconciliation`.
- Explicit legacy imports remain source-compatible and re-export the identical
  shared contract objects; the legacy engines were not rewritten or activated.

## Validation

Source revision tested: `d7eb2f0ee4c3e338f82910f4b3b2a469a5e45060`.

- Focused async-runtime quarantine suite: `59 passed`.
- Full repository suite: `1775 passed, 6 skipped`.
- `python -m compileall -q src`: passed.
- `git diff --check`: passed.
- Diff scan found no credential material.

## VPS evidence

The VPS checkout and AUTOBOT image label matched the tested revision. The
container was `running` and `healthy`; `/health` was healthy. The four isolated
research timers were active after deployment.

- `LIVE_TRADING_CONFIRMATION=false`.
- `STRATEGY_ROUTER_LIVE_ENABLED=false`.
- `COLONY_AUTO_LIVE_PROMOTION=false`.
- `ENABLE_INSTANCE_SPLIT_EXECUTOR=false`.
- The pre-existing `PAPER_TRADING=true` setting was not changed and no
  paper-capital route, promotion or order path was activated.
- Filtered recent logs contained no traceback, critical error, live order or
  live-trading activation.

Generated runtime entries on the VPS worktree were preserved and were neither
reset, cleaned nor committed.

## Residual risks / next gate

- The synchronous legacy modules remain present for compatibility and should be
  removed only after their explicit callers are migrated and independently
  tested.
- External-fill reconciliation still needs an execution-safety audit against
  the canonical lifecycle graph before any future paper review.
- No strategy has qualified for paper-capital or live review.
