# AUTOBOT Block 5 — Shadow Ledger / TCA VPS Validation — 2026-07-27

## Verdict

`GO` for the research-only Block 5 deployment. The deployment does not authorize
paper capital, promotion, live trading, or any order path.

## Provenance

- GitHub/VPS source commit: `03fbf69d8dca1ab3b38b0ca832229d15240d354b`
- Container image revision: `03fbf69d8dca1ab3b38b0ca832229d15240d354b`
- Container: `autobot-v2`, `running`, `healthy`, read-only root filesystem,
  restart count `0`.

## Delivered behavior

- Research fills bind immutable execution evidence to the exact intent, approved
  risk decision, market identity and cost fingerprint.
- Ledger reconstruction does not double-count spread, slippage or latency already
  embedded in the simulator fill price.
- Spot funding is explicit `NOT_APPLICABLE`; unknown derivative funding blocks TCA
  instead of being treated as zero.
- A pure research adapter builds TCA only from immutable simulator fill evidence
  and caller-supplied signal and decision prices. It is not connected to the
  runtime, paper executor, exchange client, or order router.

## Local verification before deployment

- Targeted execution-simulator and OMS-ledger tests: `59 passed`.
- Research suite: `677 passed, 1 skipped`.
- Paper/risk/deployment/execution-safety suite: `112 passed`.
- Full `tests` suite: `1295 passed, 1 skipped`.
- `src/autobot/v2/tests`: `622 passed, 5 skipped, 2 deselected`.
- `python -m compileall -q src tools`, JSON validation, `git diff --check`, and
  static secret/order-endpoint scan passed.

## VPS smoke evidence

- `/health`: healthy; orchestrator running; WebSocket connected.
- `AUTOBOT_OBSERVATION_ONLY_RUNTIME=true`.
- `PAPER_TRADING=false`.
- `PAPER_EXECUTION_ROUTER_ENABLED=false`.
- `PAPER_EXECUTION_ADAPTER_ENABLED=false`.
- `PAPER_TEST_TRADING_ENABLED=false`.
- `LIVE_TRADING_CONFIRMATION=false`.
- `STRATEGY_ROUTER_LIVE_ENABLED=false`.
- `COLONY_AUTO_LIVE_PROMOTION=false`.
- Private Kraken credential environment entries: `0`.
- Recent order/critical-log matches: `0`.

## Operational note

The restarted observation runtime reported one BTC/EUR observation instance.
The deployed diff contains no change under `config/`, `deploy/`,
`docker-compose.yml`, or `.env.example`; the reduction from the previously
observed multi-instance runtime is therefore an existing runtime/configuration
state, not a side effect of this Block 5 deployment. It remains observation-only
and is intentionally not expanded by this change.

## Residual risks and next gate

- The authoritative runtime OMS/ledger migration remains intentionally pending;
  this deployment only strengthens the hermetic research ledger and TCA path.
- Runtime-generated reports and research memory are intentionally outside Git and
  require separate retention policy ownership.
- No paper or live transition is authorized. The next work must remain
  research/shadow and evidence-driven.
