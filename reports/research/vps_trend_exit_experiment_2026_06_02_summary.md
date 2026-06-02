# VPS Trend Exit Experiment - 2026-06-02

## Objective

Test whether changing only the research-only `trend` exit policy improves AUTOBOT validation results on the local VPS-derived `market_price_samples` dataset.

This is a replay/backtest validation experiment only. It does not change official paper execution, live trading, Kraken integration, or production routing.

## Dataset

- Source: `data/vps_autobot_state_2026-06-01.db`
- Table: `market_price_samples`
- Period: `2026-05-27T20:25:09Z` to `2026-06-01T11:55:57Z`
- Symbols tested: `BTCZEUR`, `ETHZEUR`, `SOLEUR`, `LTCZEUR`, `XLMZEUR`, `XRPZEUR`, `TRXEUR`, `ADAEUR`, `LINKEUR`, `DOTEUR`, `BCHEUR`, `ATOMEUR`, `AVAXEUR`, `AAVEEUR`
- Strategy family: `trend`
- Costs: default research cost model, including taker fees, fallback spread, and slippage.

## Compared Exit Modes

| Mode | Config | Trades | Gross PnL EUR | Net PnL EUR | Cost EUR | MFE > Cost Trades | MFE > Cost Lost | Avg MFE bps | Avg Exit Capture bps | Avg Giveback bps | Positive MFE Capture |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `baseline` | existing ATR/trailing/exit-low behavior | 221 | -45.083564 | -115.803564 | 106.080000 | 81 | 43 | 66.441342 | -20.381459 | 86.822801 | 0.175703 |
| `cost_buffer_tp` | take profit at 80 bps | 276 | -61.945157 | -150.265157 | 132.480000 | 105 | 26 | 40.127716 | -22.423716 | 62.551433 | 0.406330 |
| `mfe_trailing` | activate at 55 bps, trail 30 bps giveback | 243 | -48.463463 | -126.223463 | 116.640000 | 94 | 47 | 54.124576 | -19.925879 | 74.050455 | 0.212507 |
| `time_stop` | max hold 18 bars if not positive | 221 | -45.083564 | -115.803564 | 106.080000 | 81 | 43 | 66.441342 | -20.381459 | 86.822801 | 0.175703 |

## Interpretation

None of the tested exit-only variants improves net PnL.

- `cost_buffer_tp` captures a higher share of positive MFE when trades move enough, but it increases trade count and costs, and worsens net PnL.
- `mfe_trailing` slightly improves average exit capture versus baseline, but not enough to offset costs and still worsens net PnL.
- `time_stop` did not materially trigger with the tested parameters and is equivalent to baseline on this dataset.
- The baseline already shows an exit-capture weakness, but the larger issue is not solved by exit policy alone: too many trend entries do not produce enough robust post-cost movement.

## Decision

Do not promote any of these exit policies to official paper execution.

Recommended status:

- `baseline`: keep as current research reference.
- `cost_buffer_tp`: reject this 80 bps configuration.
- `mfe_trailing`: keep testing only if paired with stricter entry/regime filters.
- `time_stop`: not useful with this parameterization.

## Next Technical Action

Move the next research slice from exit-only changes to entry/regime validation:

1. Compare accepted trend entries against rejected/candidate entries by regime.
2. Require trend entries to show stronger pre-entry momentum persistence, not just breakout.
3. Add a trend-specific setup quality report:
   - breakout strength
   - momentum persistence
   - ATR regime
   - spread/cost ratio
   - post-entry MFE distribution
   - stop-hit frequency
4. Only after entry quality improves, retest `mfe_trailing` as a secondary exit policy.

## Safety

- Live trading remains disabled and untouched.
- No registry promotion was performed.
- No dashboard/API/runtime behavior was changed.
- The experiment is research-only and measured after fees/spread/slippage.
