# High Conviction Walk-Forward Deployment Non-Regression - 2026-06-22

## Verdict

`PASS_WITH_WARNINGS`

The High Conviction portfolio-aware walk-forward runner is deployed and has
completed an isolated VPS replay. It remains research-only and does not meet
the paper-candidate criteria.

## Scope

- Deployed commits: `bdb1112` (walk-forward runner) and `1bed803` (research
  report output permission hardening).
- No live, paper runtime, strategy router, sizing, risk, or instance split
  behavior changed.
- The production `autobot-v2` service was rebuilt only for `bdb1112`; the
  `1bed803` systemd-script update was fast-forwarded without a restart.

## VPS Evidence

- `autobot-v2`: healthy after deployment.
- `/health`: orchestrator running, WebSocket connected, 14 instances.
- `PAPER_TRADING=true`.
- `LIVE_TRADING_CONFIRMATION=false`.
- `STRATEGY_ROUTER_LIVE_ENABLED=false`.
- `COLONY_AUTO_LIVE_PROMOTION=false`.
- No critical traceback or live-order log was found in the post-deploy log
  sample.

## Automatic Research Collection

- `autobot-research-data.timer` is enabled and active.
- The next daily collection invokes the High Conviction walk-forward report
  after public OHLCV and spread/depth collection.
- The collection service retains an isolated output boundary: it mounts only
  research data and reports, never the runtime database, logs, `.env`, or
  private API credentials.
- The output-directory ownership hardening prevents a previous root-created
  report directory from blocking the unprivileged collection container.

## Isolated VPS Replay

Run: `high_conviction_walk_forward_2026_06_22_manual`

- Execution: one-off read-only container, `--network none`, no Kraken access,
  no runtime database mount, and no order-capable component.
- Dataset: 62,678 deduplicated OHLCV bars; 151,459 overlapping bars removed.
- Walk-forward folds: 5. Each out-of-sample fold started with 500 EUR.
- Profiles: `paper_current_taker` and `research_stress`.
- Policies: `conservative` and `dynamic_scaling`.

Best observed scenario:

| Cost profile | Policy | Exit | Net PnL | PF | Trades | Positive folds | Worst fold DD |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| `paper_current_taker` | `dynamic_scaling` | `fixed_tp_sl` | +22.25 EUR | 1.64 | 24 | 2 / 5 | 3.96% |

The equivalent conservative result was +22.11 EUR. Under `research_stress`,
the best result was +21.28 EUR with PF 1.61. Trailing exits were negative
under every tested cost/policy combination.

## Warnings Blocking Promotion

- 24 closed trades is below the required 50.
- Only 2 of 5 out-of-sample folds are positive.
- BCHEUR represents about 69% of positive PnL in the best result.
- `paper_candidate_allowed=false` and `live_promotion_allowed=false`.

## Tests

```text
python -m py_compile <touched runner, CLI, collector and test modules>  PASS
python -m compileall -q src                                      PASS
pytest targeted High Conviction / daily collector suite          16 passed
pytest research + CLI + strategy safety suite                    236 passed
docker compose config -q                                         PASS
bash -n deploy/systemd/run-autobot-research-collection.sh        PASS
```

## Next Action

Continue collecting daily public research data and allow the automatic
walk-forward reports to build a larger out-of-sample sample. Do not promote to
paper official unless the configured minimum trade count, fold stability,
drawdown, and symbol-diversification criteria are all met.
