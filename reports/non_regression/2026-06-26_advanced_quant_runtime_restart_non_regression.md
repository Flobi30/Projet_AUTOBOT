# Advanced Quant Runtime Restart Non-Regression - 2026-06-26

## Verdict

`PASS`

## Action Performed

AUTOBOT runtime was recreated to run on the rebuilt image containing the advanced quant research-only code.

Command:

```text
docker compose up -d --no-deps --no-build --force-recreate autobot
```

## What Changed

- The running `autobot-v2` container now uses image `sha256:05718b9901e20bfceef9fecf8eac715912a325e534e33e210c73854daa04bd11`.
- The image matches the latest rebuilt `projet_autobot-autobot` image.
- The runtime process restarted cleanly.

## What Did Not Change

- No live trading flag was enabled.
- No paper/live execution logic was edited.
- No sizing or risk flag was changed.
- No strategy was promoted.
- No instance split executor was enabled.
- No Kraken live order was created.
- No source code changed during this restart.

## Evidence

`/health`:

- status: `healthy`
- orchestrator: `running`
- websocket: `connected`
- instances: `14`

Docker:

- container: `autobot-v2`
- status: `Up ... (healthy)`
- image: `projet_autobot-autobot`
- image id: `sha256:05718b9901e20bfceef9fecf8eac715912a325e534e33e210c73854daa04bd11`

Safety flags:

- `PAPER_TRADING=true`
- `LIVE_TRADING_CONFIRMATION=false`
- `STRATEGY_ROUTER_LIVE_ENABLED=false`
- `COLONY_AUTO_LIVE_PROMOTION=false`

Recent startup logs:

- no `traceback`
- no `critical`
- no `fatal`
- no live-order pattern
- no Kraken-order pattern

## Risk

Low. The restart only loaded the already-built image. The new advanced quant layer remains research-only and does not authorize live, paper official execution, strategy promotion, or instance split execution.

## Recommendation

Let the daily research runner produce the next report from the new image. The next review should focus on PF by strategy/pair, cost profiles, drawdown, trade count, PF gate reached, market confidence, Monte Carlo survival, cost survival, liquidity risk, and overfitting risk.

