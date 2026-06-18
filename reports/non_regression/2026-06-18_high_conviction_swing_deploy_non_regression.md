# High Conviction Swing Deploy Non-Regression - 2026-06-18

## Verdict

PASS_WITH_WARNINGS

## Commit Deployed

- Commit: `64f0049`
- Title: `Add high-conviction swing research replay`
- Previous VPS commit: `bc4c8a0`

## Deployment

Commands executed:

```bash
git pull --ff-only origin master
docker compose build autobot
docker compose up -d autobot
```

Result:

- Container recreated successfully.
- `/health`: healthy
- WebSocket: connected
- Instances: 14
- `PAPER_TRADING=true`
- `LIVE_TRADING_CONFIRMATION=false`
- `STRATEGY_ROUTER_LIVE_ENABLED=false`
- `COLONY_AUTO_LIVE_PROMOTION=false`

No live trading flag was enabled. No strategy was promoted. No instance split executor was enabled.

## Runtime Logs

Recent startup logs showed:

- Shadow modules initialized in `SHADOW` status.
- RiskManager initialized.
- ATR warm-up messages.
- WebSocket `high_message_rate` warning with `drops=0`.
- No traceback observed in the checked log tail.

## Research Run

Command executed inside the container:

```bash
PYTHONPATH=/app/src python -m autobot.v2.cli high-conviction-swing \
  --run-id high_conviction_swing_2026_06_18 \
  --state-db /app/data/autobot_state.db \
  --lookback-hours 72 \
  --cost-profile research_stress \
  --output-dir /app/reports/research/high_conviction_swing
```

Reports copied to the repository:

- `reports/research/high_conviction_swing_2026_06_18.md`
- `reports/research/high_conviction_swing_2026_06_18.json`

## Key Result

The run covered:

- Window: `2026-06-15T16:55:00.588764+00:00` -> `2026-06-18T16:55:00.588764+00:00`
- Decision rows scanned: 2,278
- Signal candidates: 1,112
- Usable replay candidates: 891
- Symbols with usable candidates: `BCHEUR`, `DOTEUR`, `XRPZEUR`
- Cost profile: `research_stress`
- Round-trip cost estimate: 98 bps

Expected move distribution:

- `100_149_bps`: 891 signals
- `unknown`: 221 signals
- `>=150_bps`: 0 signals
- `>=200_bps`: 0 signals
- `>=500_bps`: 0 signals
- `>=1000_bps`: 0 signals

Conclusion: `micro_trade_bias_detected_no_candidate_yet`.

The best scenario was:

- Scenario: `trailing__min100bps__rr3__hold6h__mtf`
- Trades: 269
- Net PnL: -257.562023 EUR
- Profit factor: 0.008584559978723753
- Winrate: 4.089219330855019%
- Expectancy: -95.74796409164748 bps
- Max drawdown: 25,756.20234065317 bps
- Blockers: net return not positive after costs, profit factor below minimum, drawdown above maximum

## Interpretation

AUTOBOT is currently not producing high-conviction signals. The recent opportunity stream is concentrated around roughly 100-149 bps gross expected move, with average net edge around 45 bps after the available cost estimates. That is not enough for the requested swing orientation targeting 2%, 5% or 10% moves.

The warning is not a deployment problem. It is a strategy/research finding: the current signal generation remains too micro-oriented and should not be promoted.

## Safety Confirmation

- No live order was created.
- No paper official behavior was changed by the research command.
- No cost guard or microstructure filter was disabled.
- No sizing/risk setting was changed.
- No strategy registry mutation occurred.
- No duplication/spin-off was activated.
- The new CLI reads SQLite in read-only mode and writes reports only.

## Recommendation

Keep the tool deployed as a research diagnostic. Next development should target signal generation quality:

1. Build true multi-timeframe swing candidates from OHLCV history instead of replaying grid micro-signals.
2. Keep existing micro-trade strategies `learning_only` until they prove net profitability after costs.
3. Only consider controlled paper execution for a high-conviction variant after it produces enough candidates above 200/500/1000 bps and survives cost-aware replay.
