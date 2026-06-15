# Research Collection Schedule Non-Regression - 2026-06-15

## Verdict

`PASS_WITH_WARNINGS`

The daily research collector is scheduled independently from AUTOBOT trading.
It uses public Kraken market-data endpoints, receives no `.env` or API secrets,
and mounts only dedicated research output directories.

## Files Changed

- `deploy/systemd/run-autobot-research-collection.sh`
- `deploy/systemd/autobot-research-data.service`
- `deploy/systemd/autobot-research-data.timer`

## Runtime Boundaries

- No strategy, sizing, risk, routing, execution, paper, or live code changed.
- The main `autobot-v2` container is not restarted by this service.
- The research container cannot read the runtime database, logs, or `.env`.
- CPU is capped at 0.50 core and memory at 768 MB.
- A file lock prevents overlapping collection runs.
- The dashboard healthcheck is disabled on the one-shot research container;
  health remains owned by the main `autobot-v2` service.
- The timer runs daily at 02:15 Europe/Paris with up to five minutes jitter.

## Validation

- `python -m compileall -q` on the research collection modules: PASS.
- Focused pytest command: `5 passed`.
- Shell syntax checked with `bash -n` on the VPS: PASS.
- Deployed commit: `25cddb549ea1ae9f5054c64657edcfc11d586577`.
- Timer: enabled and active; next daily trigger is 02:15 Europe/Paris plus up
  to five minutes randomized delay.
- First isolated run started successfully and produced OHLCV CSV, quality JSON,
  quality Markdown, and collection manifests for the configured symbols.
- Main `/health`: healthy; orchestrator running; WebSocket connected; 14
  instances.
- Authenticated `/api/status`, `/api/capital`, and `/api/trading/debug`: HTTP
  200.
- No critical traceback was present in the main container logs during the
  deployment check.
- Trading flags remained `PAPER_TRADING=true`,
  `LIVE_TRADING_CONFIRMATION=false`, `STRATEGY_ROUTER_LIVE_ENABLED=false`, and
  `COLONY_AUTO_LIVE_PROMOTION=false`.

## Warning

The normal microstructure run lasts about one hour because it records 60 public
order-book samples at one-minute intervals. Kraken public endpoint errors are
reported as partial results and do not alter trading runtime.

The first manually started run inherited the image dashboard healthcheck and
therefore displayed `unhealthy` while collecting normally. Commit `25cddb5`
adds `--no-healthcheck`; subsequent scheduled research containers will no
longer expose that misleading status. The main `autobot-v2` container remained
healthy throughout.

## Trading Safety

- `PAPER_TRADING` remains unchanged.
- `LIVE_TRADING_CONFIRMATION` remains unchanged.
- No order API is available to the scheduled container.
- No strategy promotion or instance split is performed.
