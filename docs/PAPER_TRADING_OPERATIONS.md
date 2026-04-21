# PAPER_TRADING_OPERATIONS

Operational support pass for safer day-to-day paper trading.

## 1) Pre-launch validation helper

Validate `.env` and paper safety gates before starting:

```bash
python tools/paper_ops.py validate --env-file .env
```

What it checks:
- Required paper gates: `DEPLOYMENT_STAGE=paper`, `PAPER_TRADING=true`
- Recommended paper defaults (`LIVE_TRADING_CONFIRMATION=false`, `AUTOBOT_SAFE_MODE=true`, etc.)
- Marker lockout (`data/compromised_secret.marker`)
- Basic pair/capital sanity
- Risky override warning: `AUTOBOT_FORCE_ENABLE_ALL=true`

## 2) Start guidance artifact

Print operator runbook commands directly:

```bash
python tools/paper_ops.py start-guide
```

This gives an explicit sequence:
1. validate env,
2. run `PREFLIGHT_ONLY=true` attestation,
3. launch paper mode,
4. monitor logs + status endpoint,
5. generate end-of-session summary.

## 3) Post-run session summary helper

Summarize the latest log session from `autobot_async.log`:

```bash
python tools/paper_ops.py session-summary --log-file autobot_async.log --hours 24 --format text
```

Operator-friendly Markdown output:

```bash
python tools/paper_ops.py session-summary --log-file autobot_async.log --hours 24 --format markdown
```

Machine-readable JSON output:

```bash
python tools/paper_ops.py session-summary --log-file autobot_async.log --hours 24 --format json
```

Optional runtime status snapshot enrichment (if you exported an API status JSON):

```bash
curl -s http://127.0.0.1:8080/api/status > session_status.json
python tools/paper_ops.py session-summary --log-file autobot_async.log --hours 24 --format markdown --status-file session_status.json
```

Report now includes:
- warnings/errors totals and top recurring lines,
- kill-switch mentions,
- attestation + preflight state,
- instance creation clues (names/symbols),
- ranking/opportunity/scaling/allocation/universe/health clue counters,
- session health level (`stable` / `degraded` / `critical`),
- explicit “what to inspect next” hints.

## 4) Feature-flag activation guidance (paper mode)

Print a concrete paper flag matrix:

```bash
python tools/paper_ops.py flags-guide
```

It outputs required and recommended paper gates plus baseline feature toggles that keep operations predictable.

## 5) Lightweight diagnostics/observability usage

Use the helper outputs with existing logs/endpoints:

```bash
tail -f autobot_async.log
curl -s http://127.0.0.1:8080/api/status
python tools/paper_ops.py session-summary --hours 6
```

No trading logic is altered by this pass; helpers are operator-side tooling only.
