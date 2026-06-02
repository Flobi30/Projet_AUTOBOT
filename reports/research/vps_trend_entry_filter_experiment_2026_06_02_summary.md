# VPS Trend Entry Filter Experiment - 2026-06-02

## Objective

Test whether stricter research-only trend entry filters improve net results on the local VPS-derived dataset.

This experiment does not change official paper execution, live trading, Kraken integration, dashboard behavior, or the strategy router.

## Dataset

- Source: `data/vps_autobot_state_2026-06-01.db`
- Table: `market_price_samples`
- Period: `2026-05-27T20:25:09Z` to `2026-06-01T11:55:57Z`
- Symbols tested: `BTCZEUR`, `ETHZEUR`, `SOLEUR`, `LTCZEUR`, `XLMZEUR`, `XRPZEUR`, `TRXEUR`, `ADAEUR`, `LINKEUR`, `DOTEUR`, `BCHEUR`, `ATOMEUR`, `AVAXEUR`, `AAVEEUR`
- Strategy family: `trend`
- Costs: default research cost model, including taker fees, fallback spread, and slippage.

## Results

| Config | confirm_bps | min_momentum_bps | min_atr_bps | Trades | Gross PnL EUR | Net PnL EUR | Cost EUR | Net/Trade EUR | Cost-Dominated | MFE>Cost Lost | Avg MFE bps | Avg Exit bps | Avg MFE/Cost |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `baseline` | 20 | 25 | 8 | 221 | -45.083564 | -115.803564 | 106.080000 | -0.523998 | 140 | 43 | 66.441342 | -20.381459 | 1.328827 |
| `no_weak_breakout` | 40 | 40 | 15 | 94 | -6.334494 | -36.414494 | 45.120000 | -0.387388 | 43 | 26 | 104.809923 | -6.732764 | 2.096198 |
| `strong_momentum` | 40 | 100 | 15 | 75 | -3.351476 | -27.351476 | 36.000000 | -0.364686 | 32 | 21 | 112.925286 | -4.464617 | 2.258506 |
| `strong_breakout` | 80 | 100 | 15 | 24 | -13.965635 | -21.645635 | 11.520000 | -0.901901 | 14 | 5 | 91.231864 | -58.137821 | 1.824637 |
| `high_atr_strong` | 40 | 100 | 50 | 6 | -8.448624 | -10.368624 | 2.880000 | -1.728104 | 2 | 4 | 86.947417 | -140.683784 | 1.738948 |

## Interpretation

Stricter entry filters reduce damage but do not create a profitable trend strategy on this dataset.

- Removing weak breakouts improves net PnL from `-115.803564` EUR to `-36.414494` EUR and cuts trades from `221` to `94`.
- Requiring stronger momentum improves net PnL further to `-27.351476` EUR and cuts cost-dominated trades from `140` to `32`.
- Very strong breakout or high-ATR filters reduce trade count too much and worsen average trade quality.
- The best tested direction is `confirm_bps=40`, `min_momentum_bps=100`, `min_atr_bps=15`, but it is still negative after costs.

## Decision

Do not promote any tested entry filter to official paper execution yet.

Recommended next research step:

1. Use `strong_momentum` as the next research baseline, not as a production setting.
2. Combine stricter entry with a tested exit policy only in replay:
   - baseline exit
   - `mfe_trailing`
   - possibly a smaller fixed giveback threshold
3. Add a cost-aware signal threshold:
   - require expected movement to exceed modeled cost by a configurable margin.
4. Add regime context to validation journals, because current replay regime is `unknown`.

## Safety

- No live trading was enabled.
- No runtime paper executor was changed.
- No strategy registry promotion was performed.
- This experiment is research-only and measured net of modeled fees/spread/slippage.
