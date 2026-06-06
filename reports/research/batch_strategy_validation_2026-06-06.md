# Batch Strategy Validation - 2026-06-06

Generated evidence: `reports/research/batch_strategy_validation_2026-06-06/batch_strategy_validation_2026-06-06.md`

## Scope

Research-only batch validation on snapshot `data/vps_autobot_state_2026-06-04_2026-06-04_121159.db`.

Symbols tested: `TRXEUR`, `XLMZEUR`.

Strategies tested: `grid`, `trend`, `mean_reversion`.

Costs: 16 bps fee, 8 bps spread, 4 bps slippage, 1 bps latency.

## Results

| Window | Cells | Trades | Net PnL | Profitable cells | Worst |
| --- | ---: | ---: | ---: | ---: | --- |
| full | 6 | 973 | -456.926628 | 0 | XLMZEUR/mean_reversion -187.692667 |
| early | 6 | 378 | -157.206791 | 0 | XLMZEUR/trend -59.581330 |
| middle | 6 | 306 | -165.651435 | 0 | XLMZEUR/mean_reversion -80.546414 |
| late | 6 | 291 | -135.376986 | 0 | XLMZEUR/mean_reversion -63.671297 |
| weekend | 6 | 280 | -134.503199 | 0 | XLMZEUR/mean_reversion -59.853978 |

## Status

- `grid`: `research_only`
- `trend`: `research_only`
- `mean_reversion`: `research_only`

Conclusion: no validation window was net positive after costs. Keep strategies research-only. No promotion.

## Limitations

This batch uses runtime sample data, which the data-quality report marks `not_ready`. It is useful to expose failure modes, not to validate a strategy for paper/live promotion.
