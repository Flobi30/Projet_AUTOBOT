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

- Shell syntax checked with `bash -n` on the VPS.
- Focused daily-collection and CLI tests executed locally.
- A short public-data smoke run executed in the isolated container.
- Timer state, service logs, persistent outputs, dashboard health, and trading
  safety flags verified after installation.

## Warning

The normal microstructure run lasts about one hour because it records 60 public
order-book samples at one-minute intervals. Kraken public endpoint errors are
reported as partial results and do not alter trading runtime.

## Trading Safety

- `PAPER_TRADING` remains unchanged.
- `LIVE_TRADING_CONFIRMATION` remains unchanged.
- No order API is available to the scheduled container.
- No strategy promotion or instance split is performed.
