# VPS Trend Regime Context Experiment - 2026-06-02

## Objective

Validate that AUTOBOT research replays can attach Markov/entropy regime context to every bar, signal and trade journal entry without using future bars.

This experiment reruns the best recent trend research candidate with regime enrichment enabled:

- `confirm_bps=40`
- `min_momentum_bps=100`
- `min_atr_bps=15`
- `min_signal_net_edge_bps=120`
- strategy: `trend`
- mode: research replay only

## Dataset

- Source: `data/vps_autobot_state_2026-06-01.db`
- Table: `market_price_samples`
- Symbols: `BTCZEUR`, `ETHZEUR`, `SOLEUR`, `LTCZEUR`, `XLMZEUR`, `XRPZEUR`, `TRXEUR`, `ADAEUR`, `LINKEUR`, `DOTEUR`, `BCHEUR`, `ATOMEUR`, `AVAXEUR`, `AAVEEUR`
- Costs: default research cost model, including taker fees, fallback spread, slippage, and latency buffer.

## Replay Result

| Metric | Value |
| --- | ---: |
| Matrix cells | 14 |
| Success cells | 14 |
| Error cells | 0 |
| Closed trades | 30 |
| Gross PnL EUR | 3.227229 |
| Net PnL EUR | -6.372771 |
| Cost-dominated trades | 11 |
| MFE above cost but lost trades | 9 |

## By Regime

| Regime | Trades | Win Rate | Gross PnL EUR | Net PnL EUR | Avg Net EUR | Avg MFE bps | Avg Exit bps | Avg MFE/Cost | Cost-Dominated |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `high_vol` | 6 | 0.0000% | -5.689117 | -7.609117 | -1.268186 | 38.409767 | -94.733362 | 0.768195 | 4 |
| `chaos` | 24 | 41.6667% | 8.916346 | 1.236346 | 0.051514 | 169.703540 | 37.118037 | 3.394071 | 7 |

## Interpretation

The regime context is now useful in replay journals.

The same filtered trend candidate that was still negative overall shows two very different behaviors:

- `high_vol` is clearly harmful in this replay: `6` trades, `0%` win rate, `-7.609117 EUR` net, poor MFE/cost ratio.
- `chaos` is slightly positive: `24` trades, `41.67%` win rate, `+1.236346 EUR` net, better MFE/cost ratio.

This does not mean AUTOBOT should trade chaos blindly. The sample remains small and the regime classifier is a lightweight sensor, not a prediction engine. It does mean regime-labeled validation can now explain why aggregate PnL hides important behavior.

## Decision

Do not promote this strategy or these filters to official paper/live execution.

Use this as a research direction:

- trend entries should be tested by regime before any paper promotion;
- `high_vol` should likely be blocked or heavily penalized for this trend setup;
- `chaos` needs longer replay, baselines, and walk-forward validation before trusting it;
- regime context should also be applied to grid and mean-reversion validation.

## Safety

- Live trading remains disabled and untouched.
- Official paper execution is unchanged.
- Runtime strategy router is unchanged.
- The regime enrichment is opt-in via `include_regime_context`.
- No strategy registry promotion was performed.

