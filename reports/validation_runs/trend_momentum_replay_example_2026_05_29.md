# Validation Run - trend_momentum_replay_example_2026_05_29

Strategy: `trend_momentum`
Symbol: `TRXEUR`
Dataset: `synthetic_trend_reversal_inline`
Period: `2026-05-29T08:00:00+00:00` to `2026-05-29T08:10:00+00:00`

## Hypothesis

Existing TrendStrategy replay on synthetic trend/reversal data to prove the validation harness pipeline.

## Metrics

| Metric | Value |
| --- | ---: |
| Initial capital | 1000.00 |
| Final equity | 1000.31 |
| Total return gross | 0.0635% |
| Total return net | 0.0313% |
| Max drawdown | 0.0242% |
| Profit factor | inf |
| Winrate | 100.00% |
| Expectancy | 0.233003 |
| Closed trades | 1 |
| Average win | 0.233003 |
| Average loss | 0.000000 |
| Average duration seconds | 60.000000 |
| Sharpe | N/A |
| Sortino | N/A |
| Fees total | 0.481399 |
| Slippage total | 0.120334 |

## Baselines

| Baseline | Net PnL | Net return | Trades | Profit factor | Max DD |
| --- | ---: | ---: | ---: | ---: | ---: |
| no_trade_baseline | 0.000000 | 0.0000% | 0 | N/A | 0.0000% |
| buy_and_hold | 14.344031 | 1.4344% | 1 | inf | 0.0000% |
| random_signal_baseline | 0.141740 | 0.0142% | 2 | 0.982152 | 0.0000% |

## Decision

Recommended status: `keep_testing`
Registry proposal: `candidate`
Reason: `insufficient_closed_trades`
Live promotion allowed: `False`

## Replay Ledger

Ledger entries: 2
Rejected signals: 0

## Registry Update Proposal

```json
{
  "strategy_id": "trend_momentum",
  "proposed_validation_status": "candidate",
  "last_backtest_id": "trend_momentum_replay_example_2026_05_29",
  "decision": "keep_testing",
  "decision_reason": "insufficient_closed_trades",
  "live_auto_promotion_allowed": false,
  "metrics_summary": {
    "closed_trades": 1,
    "net_return_pct": 0.03133211732485961,
    "profit_factor": null,
    "max_drawdown_pct": 0.02417634293819901
  }
}
```

## Conclusion

The sample is not large enough. Continue replay/paper validation before any promotion.
