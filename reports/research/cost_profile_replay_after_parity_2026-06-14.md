# Cost Profile Replay After Parity - 2026-06-14

## Scope

Research-only replay on the frozen dataset previously used for the canonical
cost-profile comparison:

- dataset: `data/research/cost_profile_parity_20260614/cost_profile_parity_20260614_5m.csv`;
- coverage: 2026-06-07 18:20 UTC to 2026-06-14 18:20 UTC;
- symbols: AUTOBOT top-14 EUR universe;
- strategies: grid, trend, mean reversion;
- windows: full, early, middle, late and weekend;
- initial capital per cell: EUR 1,000;
- order notional: EUR 100.

No runtime, paper, live, sizing, risk, strategy threshold or promotion setting
was changed.

## Full-Window Comparison

| Cost profile | Expected round trip | Closed trades | Net PnL | Positive cells | Grid metadata cost |
| --- | ---: | ---: | ---: | ---: | ---: |
| `paper_current_taker` | 94 bps | 1,295 | EUR -1,190.800544 | 0/42 | 94 bps on 386/386 trades |
| `research_stress` | 98 bps | 1,295 | EUR -1,242.605848 | 0/42 | 98 bps on 386/386 trades |
| `research_legacy` | 50 bps | 1,295 | EUR -621.005848 | 0/42 | 50 bps on 386/386 trades |

The PnL and trade counts are identical to the pre-patch replay. This is the
expected non-regression result because no new entry filter or exit rule was
enabled. The correction changes cost context and validation evidence, not
strategy behavior.

## Corrected Cost Propagation

Before the patch, every grid trade recorded an internal expected cost of 50
bps, including the 94 and 98 bps profiles. After the patch, the grid signal
generator receives the selected canonical `ExecutionCostConfig` unless the
research caller provides an explicit override.

Observed full-window grid journal values:

- `paper_current_taker`: 386 entries at 94 bps;
- `research_stress`: 386 entries at 98 bps;
- `research_legacy`: 386 entries at 50 bps.

## Batch Decision Evidence

The batch layer now consumes evidence already produced by each child
backtest:

- no-trade baseline;
- buy-and-hold baseline;
- random-signal-same-frequency baseline;
- average MFE/cost ratio;
- average exit-capture bps.

For `paper_current_taker` and `research_stress`, all three strategy families
remain `research_only`. Their common factual blockers are:

- aggregate net PnL is negative after costs;
- no profitable full-window cell;
- profit factor below threshold;
- insufficient multi-window stability;
- no cell passes candidate thresholds;
- does not beat no-trade, buy-and-hold or random-signal baselines;
- MFE/cost below 1.5;
- exit capture below or equal to 0 bps.

The legacy profile remains non-comparable with current runtime. It is also
negative and does not justify a strategy promotion.

## Decision

- grid: `research_only`;
- trend: `research_only`;
- mean reversion: `research_only`;
- shadow candidate: none;
- live promotion: none;
- threshold reduction: not supported.

## Limits

- seven days of data only;
- 2,449 detected gaps;
- runtime samples have no real volume;
- no observed bid/ask/depth profile in this frozen dataset.

The next useful step is denser and longer market data plus observed
microstructure, not more aggressive trading settings.

