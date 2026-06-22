# Grid Retirement Deployment Non-Regression - 2026-06-22

## Verdict

`PASS`

Commit `364f3bc1755573ad893cc800ee38dfeb78b6a161` was deployed to the VPS with
a clean Docker rebuild and a controlled recreation of the `autobot` service.

## VPS Evidence

| Check | Result |
| --- | --- |
| Deployed commit | `364f3bc1755573ad893cc800ee38dfeb78b6a161` |
| Container | `autobot-v2` healthy |
| `/health` | `healthy` |
| Orchestrator | `running` |
| WebSocket | `connected` |
| Instances | `14` |
| Runtime strategy initialization | `ObservationOnlyStrategyAsync` for all observed startup instances |
| Dynamic Grid retirement flag | `True` |
| Dynamic Grid promotable | `False` |

## Trading Safety

- `PAPER_TRADING=true`
- `LIVE_TRADING_CONFIRMATION=false`
- `STRATEGY_ROUTER_LIVE_ENABLED=false`
- `COLONY_AUTO_LIVE_PROMOTION=false`
- `ENABLE_LIVE_TRADING` and `ENABLE_INSTANCE_SPLIT_EXECUTOR` are not set in
  the container environment.
- No Grid startup log, live-order log, Kraken-order log, traceback,
  `IndentationError`, or critical runtime error was found in the inspected
  startup window.

## Deployment Commands

```text
git fetch origin master
git merge --ff-only origin/master
docker compose build --no-cache autobot
docker compose up -d --force-recreate autobot
docker compose ps
curl -fsS http://127.0.0.1:8080/health
```

## Scope Confirmation

The deployment did not change live flags, paper behavior, sizing, risk,
strategy parameters, API credentials, positions, or instance duplication.
Grid remains available only for explicit archived research commands; standard
research and promotion paths exclude it.
