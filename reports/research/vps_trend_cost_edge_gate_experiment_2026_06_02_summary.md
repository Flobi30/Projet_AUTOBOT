# VPS Trend Cost/Edge Gate Experiment - 2026-06-02

## Objective

Test whether a research-only cost-aware signal gate improves the previously best trend replay candidate:

- Entry filter: `confirm_bps=40`, `min_momentum_bps=100`, `min_atr_bps=15`
- Cost gate: require `gross_edge_bps - estimated_round_trip_cost_bps >= min_signal_net_edge_bps`

The gate is implemented in the isolated research backtest engine and is disabled by default. It does not change official paper execution, live trading, Kraken integration, dashboard behavior, or the strategy router.

## Dataset

- Source: `data/vps_autobot_state_2026-06-01.db`
- Table: `market_price_samples`
- Period: `2026-05-27T20:25:09Z` to `2026-06-01T11:55:57Z`
- Symbols tested: `BTCZEUR`, `ETHZEUR`, `SOLEUR`, `LTCZEUR`, `XLMZEUR`, `XRPZEUR`, `TRXEUR`, `ADAEUR`, `LINKEUR`, `DOTEUR`, `BCHEUR`, `ATOMEUR`, `AVAXEUR`, `AAVEEUR`
- Strategy family: `trend`
- Costs: default research cost model, including taker fees, fallback spread, slippage, and latency buffer.

## Results

| Config | Min Net Edge After Cost | Trades | Gross PnL EUR | Net PnL EUR | Cost EUR | Net/Trade EUR | Cost-Dominated | MFE>Cost Lost | Avg MFE bps | Avg Exit bps | Avg MFE/Cost |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `strong_momentum_no_gate` | none | 75 | -3.351476 | -27.351476 | 36.000000 | -0.364686 | 32 | 21 | 112.925286 | -4.464617 | 2.258506 |
| `strong_momentum_edge_0` | 0 | 75 | -3.351476 | -27.351476 | 36.000000 | -0.364686 | 32 | 21 | 112.925286 | -4.464617 | 2.258506 |
| `strong_momentum_edge_40` | 40 | 75 | -3.351476 | -27.351476 | 36.000000 | -0.364686 | 32 | 21 | 112.925286 | -4.464617 | 2.258506 |
| `strong_momentum_edge_80` | 80 | 47 | 0.303366 | -14.736634 | 22.560000 | -0.313545 | 16 | 17 | 124.279816 | 0.644879 | 2.485596 |
| `strong_momentum_edge_120` | 120 | 30 | 3.227229 | -6.372771 | 14.400000 | -0.212426 | 11 | 9 | 143.444785 | 10.747757 | 2.868896 |

## Interpretation

The cost/edge gate materially reduces bad trend trades, but the strategy is still not profitable after modeled costs.

- `edge_0` and `edge_40` are equivalent to no gate because the existing `min_momentum_bps=100` already clears those levels against the default estimated round-trip cost.
- `edge_80` reduces trades from `75` to `47` and improves net PnL from `-27.351476` EUR to `-14.736634` EUR.
- `edge_120` reduces trades to `30`, creates positive gross PnL, and improves net PnL to `-6.372771` EUR, but fees still keep it negative.
- Average exit capture improves from `-4.464617` bps to `10.747757` bps at `edge_120`, meaning the remaining entries are cleaner.

## Decision

Do not promote this to official paper execution yet.

The research evidence says:

- cost-aware gating is useful;
- `strong_momentum + edge_120` is the best tested trend candidate so far;
- it is still negative after modeled fees/spread/slippage;
- sample size is small at `30` trades;
- further validation must combine this with better exit capture and longer/more diverse data before paper promotion.

## Next Research Step

Run a combined replay using:

- `confirm_bps=40`
- `min_momentum_bps=100`
- `min_atr_bps=15`
- `min_signal_net_edge_bps=120`
- compare exits:
  - baseline
  - `mfe_trailing` with stricter activation/drawdown
  - a conservative take-profit/stop pair

Then add regime context to validation journals so that AUTOBOT can tell whether these filters work only in specific market regimes.

## Safety

- Live trading remains disabled and untouched.
- Runtime paper execution is unchanged.
- No strategy registry promotion was performed.
- The gate is disabled by default and only active when explicitly configured in research validation.
