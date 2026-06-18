# High Conviction Discovery Non-Regression - 2026-06-18

Verdict: PASS_WITH_WARNINGS

## Scope

This check covers the new research-only high-conviction discovery layer.

Modified/created files:

- `src/autobot/v2/research/high_conviction_discovery.py`
- `src/autobot/v2/cli.py`
- `tests/research/test_high_conviction_discovery.py`
- `reports/research/high_conviction_discovery_2026_06_18.md`
- `reports/research/high_conviction_discovery_2026_06_18.json`

No paper runtime, live runtime, sizing, risk manager, strategy router, strategy registry, or duplication executor behavior was changed.

## What Changed

- Added an OHLCV-based setup discovery runner independent from current grid/decision-ledger signals.
- Added setup families:
  - `breakout_1h_4h`
  - `pullback_trend`
  - `major_support_mean_reversion`
  - `volatility_expansion`
  - `trend_continuation`
- Added replay scenarios for:
  - minimum expected move: `200`, `500`, `1000` bps
  - risk/reward: `1:2`, `1:3`
  - max hold: `6h`, `24h`, `72h`, `168h`
  - exits: `fixed_tp_sl`, `trailing`, `partial_runner`, `trend_invalidation`
- Added CLI command:

```powershell
python -m autobot.v2.cli high-conviction-discovery
```

## Runtime Safety

- Live trading was not enabled.
- Duplication/spin-off was not enabled.
- No Kraken order path is imported or called by the new runner.
- No strategy registry mutation or promotion is performed.
- No paper/live flags are read or modified.
- `live_promotion_allowed=false` is included in reports and scenario results.

## Commands Run

```powershell
python -m py_compile src\autobot\v2\research\high_conviction_discovery.py src\autobot\v2\cli.py
```

Result: PASS

```powershell
$env:PYTHONPATH='src'; python -m pytest tests\research\test_high_conviction_discovery.py -q
```

Result: `3 passed`

```powershell
python -m compileall -q src
```

Result: PASS

```powershell
$env:PYTHONPATH='src'; python -m pytest tests\research\test_high_conviction_discovery.py tests\research\test_high_conviction_swing.py tests\test_v2_cli.py -q
```

Result: `32 passed`

```powershell
$env:PYTHONPATH='src'; python -m pytest tests\research -q
```

Result: `158 passed`

## Research Smoke Run

Command:

```powershell
$env:PYTHONPATH='src'; python -m autobot.v2.cli high-conviction-discovery --run-id high_conviction_discovery_2026_06_18 --data-paths data\research\daily\ohlcv\daily_2026_06_08 --output-dir reports\research --micro-report-json reports\research\high_conviction_swing_2026_06_18.json --cost-profile research_stress
```

Generated:

- `reports/research/high_conviction_discovery_2026_06_18.md`
- `reports/research/high_conviction_discovery_2026_06_18.json`

Summary:

- Setups detected: `508`
- Symbols with setups: `ADAEUR`, `AVAXEUR`, `DOTEUR`, `LINKEUR`, `SOLEUR`, `TRXEUR`, `XRPZEUR`
- Expected move distribution:
  - `<200 bps`: `0`
  - `200-499 bps`: `268`
  - `500-999 bps`: `221`
  - `>=1000 bps`: `19`
- Cost profile: `research_stress`
- Round-trip cost estimate: `98 bps`
- Best scenario: `trend_invalidation__min1000bps__rr2__hold24h`
- Best net PnL: `-13.177494 EUR`
- Best profit factor: `0.205004609978723753`
- Best trade count: `19`
- Best status: `research_only`
- Comparison versus micro/grid report: discovery best PnL was `244.384529 EUR` better than the prior micro replay, but still negative.

Conclusion: `no_profitable_high_conviction_candidate_yet`

## Warnings / Limits

- The local OHLCV sample is still short and should not be used for promotion.
- Bid/ask/depth are not yet used as per-symbol dynamic spread inputs in this runner.
- Positive individual trades exist, but no scenario passed PF/sample-size gates.
- Current evidence supports further research, not official paper promotion.

## Recommendation

Do not promote any high-conviction setup yet.

Next step: collect longer multi-timeframe OHLCV plus spread/depth, then rerun this discovery over longer windows before deciding whether one family deserves controlled shadow or official paper review.

