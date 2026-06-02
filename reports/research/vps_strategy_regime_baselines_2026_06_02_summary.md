# VPS Strategy Regime Baselines - 2026-06-02

## Objective

Add mandatory simple baselines to the strategy x regime comparison so AUTOBOT does not treat a small positive bucket as evidence of edge unless it beats references.

This is research-only. It does not modify official paper execution, live trading, routing, sizing, Kraken access, or the dashboard.

## Inputs

- Strategy/regime report: `reports/research/vps_2026_06_02_strategy_regime_comparison/vps_2026_06_02_strategy_regime_comparison.json`
- Market data: `data/vps_autobot_state_2026-06-01.db`
- Symbols: top 14 EUR crypto pairs used in recent validation.
- Regime context: research Markov/entropy enrichment, applied chronologically without future bars.
- Costs: `16 bps` taker fee, `8 bps` fallback spread, `4 bps` slippage.

## Baselines Added

| Baseline | Purpose |
| --- | --- |
| `no_trade` | Safety baseline: doing nothing must beat negative-expectancy buckets. |
| `buy_and_hold_regime_segments` | One first-to-last long per symbol inside matching regime bars, net of costs. |
| `random_signal_same_frequency_regime` | Deterministic random long entries in the same regime with the same trade count. |

## Result

No strategy/regime bucket beats its best baseline.

| Strategy | Regime | Trades | Strategy Net EUR | Best Baseline | Baseline Net EUR | Delta EUR | Interpretation |
| --- | --- | ---: | ---: | --- | ---: | ---: | --- |
| `trend_momentum` | `chaos` | 24 | 1.236346 | `buy_and_hold_regime_segments` | 252.495862 | -251.259515 | Positive vs no-trade, but not an edge. |
| `mean_reversion` | `high_vol` | 4 | 0.714304 | `buy_and_hold_regime_segments` | 338.818134 | -338.103831 | Tiny positive sample, not useful. |
| `dynamic_grid` | `chaos` | 312 | -130.593793 | `random_signal_same_frequency_regime` | 50.040744 | -180.634537 | Strong underperformance. |
| `dynamic_grid` | `range` | 37 | -20.529342 | `no_trade` | 0.000000 | -20.529342 | Grid does not prove range edge. |
| `mean_reversion` | `range` | 200 | -106.172022 | `no_trade` | 0.000000 | -106.172022 | Current mean reversion default fails. |

Full report:

- `reports/research/vps_2026_06_02_strategy_regime_baselines/vps_2026_06_02_strategy_regime_comparison_baseline_comparison.md`
- `reports/research/vps_2026_06_02_strategy_regime_baselines/vps_2026_06_02_strategy_regime_comparison_baseline_comparison.json`

## Interpretation

The previous strategy/regime report showed two slightly positive pockets:

- `trend_momentum / chaos`: `+1.236346 EUR` over `24` trades.
- `mean_reversion / high_vol`: `+0.714304 EUR` over `4` trades.

The new baseline report shows that both pockets are weak:

- `trend_momentum / chaos` loses to buy-and-hold inside the same regime by `-251.259515 EUR`.
- `mean_reversion / high_vol` loses to buy-and-hold inside the same regime by `-338.103831 EUR`.

So these positives are not proof of strategy skill. They are likely exposure to favorable market movement, sample noise, or inefficient execution capture.

## Decision

Do not promote any tested strategy/regime bucket.

Do not increase allocation.

Do not lower thresholds to create more trades.

## Next Step

The next useful validation step is walk-forward strategy x regime testing with baselines. A bucket should not be considered actionable unless it:

- beats no-trade;
- beats regime buy-and-hold or explains why buy-and-hold is not applicable;
- beats random same-frequency;
- remains positive after costs;
- has enough trades;
- survives out-of-sample splits.

## Safety

- Live trading remains disabled and untouched.
- Official paper execution is unchanged.
- No strategy registry promotion was performed.
- The new baselines are diagnostics only.
