# High Conviction Discovery Deploy Non-Regression - 2026-06-18

Verdict: PASS

## Scope

Controlled VPS deployment of commit `0ef504c` containing the research-only High Conviction OHLCV Discovery brick.

This deployment restarted the AUTOBOT Docker service/container only. The VPS host was not rebooted.

## Deployed Commit

- Before deploy: `40809b4`
- After deploy: `0ef504c`
- Git update: fast-forward from `origin/master`

## Commands Run On VPS

```bash
cd /opt/Projet_AUTOBOT
git fetch origin master
git pull --ff-only origin master
python3 -m compileall -q src
docker compose build autobot
docker compose up -d autobot
docker compose ps
curl -fsS http://127.0.0.1:8080/health
docker exec -e PYTHONPATH=/app/src autobot-v2 python -m autobot.v2.cli high-conviction-discovery --help
docker logs --tail 250 autobot-v2
```

## Runtime Health

`/health` after restart:

```json
{
  "status": "healthy",
  "components": {
    "orchestrator": "running",
    "websocket": "connected",
    "instances": 14
  }
}
```

Docker status:

```text
autobot-v2 Up (healthy) 0.0.0.0:8080->8080/tcp
```

## Safety Flags

Read from VPS `.env` after deploy:

```text
PAPER_TRADING=true
LIVE_TRADING_CONFIRMATION=false
COLONY_AUTO_LIVE_PROMOTION=false
STRATEGY_ROUTER_LIVE_ENABLED=false
```

No `ENABLE_LIVE_TRADING=true` or `ENABLE_INSTANCE_SPLIT_EXECUTOR=true` flag was observed in the checked output.

## High Conviction Discovery Availability

The CLI command is available inside the rebuilt container:

```text
usage: cli.py high-conviction-discovery ...
```

This command remains research-only and cannot create Kraken orders.

## Logs

Checked recent logs for:

- `traceback`
- `critical`
- `fatal`
- `live order`
- `kraken order`
- `exception`

Result: no critical/runtime error found in the checked tail.

Observed non-critical logs:

- shadow engines initialized in `SHADOW`
- ATR warm-up messages after restart
- one `WS high_message_rate` warning with `drops=0`

## Trading Safety Confirmation

- Live trading was not enabled.
- Paper mode remains enabled.
- No sizing/risk/strategy flag was changed.
- No strategy promotion was performed.
- No duplication/spin-off executor was enabled.
- No Kraken live order was created by this deployment.
- The new High Conviction Discovery brick is available as a CLI research tool only.

## Conclusion

The VPS is running commit `0ef504c` with the High Conviction Discovery brick available. AUTOBOT restarted cleanly and returned healthy with WebSocket connected and live safety still locked.

