# Bid/Ask Depth Capture Plan - 2026-06-07

## Objective

Collect public top-of-book and depth snapshots so research can replace fixed spread assumptions with symbol/timeframe-specific cost profiles.

## Safety

The recorder is research-only:

- public Kraken `Depth` endpoint only;
- no private Kraken key;
- no order creation;
- no paper/live runtime integration;
- no live permission change.

Module added:

```text
src/autobot/v2/research/spread_depth_recorder.py
```

## Captured Fields

- `timestamp_local`
- `timestamp_exchange`
- `symbol`
- `source`
- `best_bid`
- `best_ask`
- `mid_price`
- `spread_bps`
- `bid_depth_eur`
- `ask_depth_eur`
- `latency_ms`

## Output

- CSV snapshots
- Markdown summary
- per-symbol spread mean/median/p95/p99
- median bid/ask top-book depth
- median latency

## Suggested Research Run

Use short samples first:

```powershell
$env:PYTHONPATH='src'
python - <<'PY'
from pathlib import Path
from autobot.v2.research.spread_depth_recorder import SpreadDepthRecorderConfig, record_spread_depth

result = record_spread_depth(
    SpreadDepthRecorderConfig(
        run_id='kraken_depth_p1_smoke_2026_06_07',
        symbols=('BTCZEUR','ETHZEUR','XLMZEUR','TRXEUR'),
        output_dir=Path('data/research/microstructure/kraken_depth_p1_smoke_2026_06_07'),
        depth_count=10,
        samples=3,
        sleep_seconds=2.0,
    )
)
print(result.to_dict())
PY
```

Then collect longer windows:

- every 30 to 60 seconds during paper runtime observation;
- at least several sessions covering calm and volatile periods;
- separate weekday/weekend samples;
- do not use this to submit or size orders until reviewed.

## Use In Validation

After enough samples:

- compute per-symbol median spread and p95 spread;
- mark symbols with extreme p95 spread as cost-risky;
- compare fixed `spread_bps=8` against observed spread distribution;
- update research cost profiles only after non-regression review.
