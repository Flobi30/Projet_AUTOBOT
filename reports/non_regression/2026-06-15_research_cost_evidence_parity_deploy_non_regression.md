# Research Cost Evidence Parity Deployment Non-Regression - 2026-06-15

## Verdict

**PASS**

Commit `ef5de45988cbad1da1a14668c445fe93043721b5` was pushed to
`origin/master` and deployed to the AUTOBOT VPS.

## Deployment

- Previous VPS commit: `28fa3e1f3937a27b8ea20d2dfa3542b1da831167`.
- Deployed commit: `ef5de45988cbad1da1a14668c445fe93043721b5`.
- Update method: `git pull --ff-only origin master`.
- Image build: `docker compose build --no-cache autobot`.
- Image validation: `python -m compileall -q src` inside an ephemeral
  container.
- Service update: `docker compose up -d autobot`.

Existing untracked VPS backup directories were preserved. No persistent
trading database, credentials or configuration flags were edited.

## Tests

Local validation before deployment:

```powershell
python -m compileall -q src
$env:PYTHONPATH='src'; python -m pytest tests/research tests/test_v2_cli.py -q
```

Result: `163 passed in 2.46s`.

The rebuilt container successfully compiled the deployed Python source. The
research CLI exposes the new options when invoked with `PYTHONPATH=src`:

- `--min-mfe-to-cost`;
- `--min-exit-capture-bps`;
- canonical `--cost-profile` choices.

## Runtime Verification

After deployment and stabilization:

- container: running and healthy;
- restart count: 0;
- `/health`: healthy;
- orchestrator: running;
- WebSocket: connected;
- instances: 14;
- critical/traceback log matches: 0;
- live/real order log matches: 0.

## Trading Safety

- `PAPER_TRADING=true`;
- `LIVE_TRADING_CONFIRMATION=false`;
- `STRATEGY_ROUTER_LIVE_ENABLED=false`;
- `COLONY_AUTO_LIVE_PROMOTION=false`;
- `ENABLE_LIVE_TRADING` unset;
- `ENABLE_INSTANCE_SPLIT_EXECUTOR` unset.

No live order was created. No strategy was promoted. No sizing, risk,
execution, position, capital, dashboard or duplication behavior was changed.
The deployed patch only affects research validation cost context and evidence
reporting.

## Next Action

Keep AUTOBOT running in paper mode and accumulate longer OHLCV plus observed
spread/depth data. A 24-hour check is suitable for collection health; strategy
profitability still requires substantially longer and cleaner evidence.
