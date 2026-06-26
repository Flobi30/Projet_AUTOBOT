# Post-Restart Advanced Quant Research Lab - 2026-06-26

## Scope

Controlled restart of AUTOBOT runtime onto the rebuilt advanced quant research image.

## Deployed Revision

- Git HEAD before restart: `8382ee21d84cfd8d1b29c2dd90cde7ebc72db606`
- Research code commit included: `5a9973f6e041fa12df8df806afb41982aac516fa`
- Container image after restart: `sha256:05718b9901e20bfceef9fecf8eac715912a325e534e33e210c73854daa04bd11`
- Named image after restart: `sha256:05718b9901e20bfceef9fecf8eac715912a325e534e33e210c73854daa04bd11`
- Container created: `2026-06-26T18:46:55Z`

## Restart Command

```text
docker compose up -d --no-deps --no-build --force-recreate autobot
```

No rebuild, no flag change, no config edit, and no order command was executed.

## Health After Restart

`/health` returned:

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

## Safety Flags

- `PAPER_TRADING=true`
- `LIVE_TRADING_CONFIRMATION=false`
- `STRATEGY_ROUTER_LIVE_ENABLED=false`
- `COLONY_AUTO_LIVE_PROMOTION=false`

No `ENABLE_LIVE_TRADING=true` or `ENABLE_INSTANCE_SPLIT_EXECUTOR=true` flag was observed.

## Logs

Recent startup log scan found no matching patterns for:

- `traceback`
- `critical`
- `fatal`
- `live order`
- `real order`
- `kraken order`
- `submitted live`
- `error`

## Conclusion

Restart verification status: `PASS`.

AUTOBOT is now running on the rebuilt image containing the advanced quant research-only layer. Runtime remains paper-only and live safety remains blocked.

