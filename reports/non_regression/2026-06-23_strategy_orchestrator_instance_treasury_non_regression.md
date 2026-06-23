# Strategy Orchestrator and Instance Treasury Non-Regression - 2026-06-23

## Verdict

`PASS_WITH_WARNINGS`

The change adds a research-only multi-strategy orchestrator, virtual instance
treasury simulation, and daily research-report hook. It does not change the
runtime strategy router, risk manager, paper executor, live controls, sizing,
or real instance creation path.

## Changed Files

| File | Change | Runtime impact |
| --- | --- | --- |
| `src/autobot/v2/research/strategy_orchestrator.py` | New standard signal contract, meta scoring, pair/regime attribution, realized-equity treasury simulation, and virtual split plan | Research only |
| `src/autobot/v2/research/daily_data_collection_runner.py` | Optional daily orchestrator report after public research collection | Research container only |
| `src/autobot/v2/research/__init__.py` | Lazy exports for the research API | None |
| `src/autobot/v2/cli.py` | `strategy-orchestrator-research` CLI command | Research only |
| `config/research_data_collection.yaml` | Enables the daily research report with 500 EUR virtual treasury defaults | Research only |
| `deploy/systemd/run-autobot-research-collection.sh` | Mounts the new report directory into the isolated research container | No trading runtime mount added |
| `tests/research/test_strategy_orchestrator.py` | Contract, treasury, gate, CLI, Grid archive, and split-safety tests | Test only |
| `tests/research/test_daily_data_collection_runner.py` | Verifies the daily report hook | Test only |

## What Did Not Change

- No runtime `StrategyRouter`, `SignalHandlerAsync`, risk manager, order router,
  paper executor, Kraken client, or dashboard contract was changed.
- No paper or live order path was added.
- No strategy was promoted or registry status mutated.
- Grid remains archived and is not imported by the new orchestrator.
- `ENABLE_INSTANCE_SPLIT_EXECUTOR` remains unused for execution in the new
  research code. The virtual split plan explicitly constructs a policy with
  `executor_enabled=false`.
- No child instance, lineage row, capital transfer, or VPS runtime flag is
  created or changed.

## Controls Verified

- `StrategyResearchSignal` rejects `research_only=false`.
- New allocation uses `realized_equity_eur` and available cash only; floating
  PnL is never used to increase an allocation.
- One position per symbol, cooldown, instance/strategy/symbol exposure caps,
  maximum position count, daily loss stop, and drawdown stop are enforced in
  the virtual treasury simulation.
- Trend, Mean Reversion, and Relative Value remain signal-only/no-capital until
  they have equivalent portfolio-aware evidence.
- Candidate-paper recommendation fails closed unless every strict criterion is
  satisfied: 50 trades, PF > 1.30, max drawdown <= 10%, 4/5 positive folds,
  <= 40% positive-PnL concentration, non-legacy costs, and adequate duration.

## Validation

```text
python -m compileall -q src                                      PASS
bash -n deploy/systemd/run-autobot-research-collection.sh        PASS
pytest targeted orchestrator/daily/high-conviction/split suite   58 passed
pytest research + CLI + router/governance/split suite             236 passed
```

## Local Research Smoke Run

Input: existing local `data/research/daily/ohlcv` only. No runtime database,
private credential, Kraken request, order, or child instance was used.

| Item | Result |
| --- | --- |
| Standardized research signals | 202 |
| High Conviction status | `active_research` |
| `research_stress` virtual treasury PnL | +8.68 EUR |
| `research_stress` PF | 2.36 |
| `research_stress` closed trades | 9 |
| Top observed pair | ADAEUR, 3 trades, +1.66 EUR |
| Top regime | `multi_timeframe_swing`, 9 trades, +10.35 EUR |
| Paper candidate | false |
| Live promotion | false |
| Child created | false |
| Split executable | false |

Warnings: the result has only nine closed trades and still fails the sample,
fold, concentration, and validation-duration gates. It is research evidence,
not a paper or live recommendation.

## Deployment Preconditions

The code can be deployed only as a research-data collection enhancement. Before
the next scheduled run, verify the mounted report directory ownership and keep
the production service flags unchanged. No AUTOBOT runtime restart is required
for the systemd collection-script update itself; the research image must contain
the committed Python code before the next timer execution.

## Controlled VPS Deployment Evidence

- Deployed code commit: `f093eea3aefb06de29f4cc24d211aec89ee3dd71`.
- `autobot-v2` restarted only to load the rebuilt image and returned `healthy`.
- `/health`: orchestrator running, WebSocket connected, 14 instances.
- `PAPER_TRADING=true`.
- `LIVE_TRADING_CONFIRMATION=false`.
- `STRATEGY_ROUTER_LIVE_ENABLED=false`.
- `COLONY_AUTO_LIVE_PROMOTION=false`.
- No critical traceback, indentation error, live-order log, or Kraken-order
  attempt was found in the post-deployment log sample.

An isolated post-deploy validation container ran with `--network none`, a
read-only daily research-data mount, and a report-directory mount only. It had
no runtime database, `.env`, private key, order router, or executor access.

| Profile | Virtual net PnL | PF | Closed trades | Estimated intratrade DD |
| --- | ---: | ---: | ---: | ---: |
| `paper_current_taker` | +8.00 EUR | 1.28 | 21 | 4.62% |
| `research_stress` | +7.23 EUR | 1.25 | 21 | 4.68% |

The run standardized 416 signals. High Conviction remains blocked by fewer
than 50 trades, fewer than 4 positive folds out of 5, and a single-pair
concentration guard. The virtual child was not created and the split remained
non-executable; the policy also correctly blocked missing lineage evidence,
insufficient parent capital, absent official-paper proof, insufficient trade
count, insufficient scorecard and unvalidated strategy status.

Generated VPS report:
`/opt/Projet_AUTOBOT/reports/research/strategy_orchestrator/strategy_orchestrator_2026_06_23_vps.md`

## Recommendation

Deploy the isolated research bundle, then let the daily OHLCV/spread-depth
collection generate repeated orchestration reports. Keep every strategy and
split research-only until the strict candidate-paper gates pass.
