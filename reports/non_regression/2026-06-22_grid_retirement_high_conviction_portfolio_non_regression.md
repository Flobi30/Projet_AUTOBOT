# Grid Retirement and High Conviction Portfolio Non-Regression - 2026-06-22

## Verdict

**PASS_WITH_WARNINGS**

The runtime retirement of Grid is covered by focused tests and the new High Conviction portfolio replay is isolated from runtime execution. The research result is deliberately **not** sufficient to promote a strategy: the best replay has only nine closed trades on a short OHLCV window.

## Changed Surface

- Runtime instance factory now creates `observation_only` instances instead of Grid instances.
- A direct legacy `grid` or unknown strategy request is replaced with the observation-only strategy.
- Dynamic Grid is excluded from router candidates, governance execution, runtime shadow updates, reconciliation sources, and setup dashboard endpoints.
- Trend and mean-reversion remain shadow/research evidence only; the router cannot enable official paper execution on its own.
- Research defaults now select trend and mean reversion. Grid code and explicit Grid research commands remain available for rollback/reproducibility, but are no longer default or runtime-active.
- Added `high-conviction-portfolio-replay`, a research-only finite-capital replay with equity sizing, risk caps, exposure caps, one position per pair, cooldown, daily-loss stop, drawdown brake, and canonical cost profiles.
- Docker now persists `/app/reports` to `./reports`; no environment or trading flag changed.

## Portfolio Replay Evidence

Run: `high_conviction_portfolio_2026_06_22`

- Dataset: seven EUR pairs, OHLCV data from `data/research/daily/ohlcv/daily_2026_06_08`.
- Setups scanned: `508`; scenario variants: `48` across two cost profiles and two sizing policies.
- Starting capital: `500 EUR`.
- Best result: `paper_current_taker`, `dynamic_scaling`, `fixed_tp_sl__min500bps__rr2__hold72h`.
- Final equity: `518.14 EUR`; net PnL: `+18.14 EUR`; PF: `4.49`; win rate: `66.67%`; closed trades: `9`.
- Intrabar max drawdown: `2.62%`; planned allocation cap: `60.00%`; marked exposure briefly reached `61.23%` because existing winning positions moved in price after entry. No additional position was opened above the planned exposure cap.
- Dynamic scaling added roughly `0.15 EUR` versus conservative sizing. It did not manufacture material performance or increase drawdown meaningfully.
- Main contributors: LINKEUR `+10.25 EUR`, DOTEUR `+4.93 EUR`, ADAEUR `+4.04 EUR`. AVAXEUR and SOLEUR were negative.
- Entry rejections prove portfolio constraints were active: `99` max-open-position blocks, `114` duplicate-symbol blocks, and `6` cooldown blocks.

The earlier independent `+693 EUR` result is **not capital-feasible evidence for a 500 EUR portfolio**: it allowed overlapping fixed-notional candidates without cash, position-count, per-pair, or exposure constraints. This run does not reproduce that claim. The current positive result is a research lead only, not a validation result.

## Safety Verification

- No Kraken/private API path was added or called.
- No live flag, paper/live environment variable, sizing runtime configuration, risk runtime configuration, leverage, promotion state, or split executor was changed.
- `live_promotion_allowed` remains `false` in the new reports and router output.
- Router and governance both return research/observe-only execution policy for Grid, Trend, and Mean Reversion.
- No strategy is automatically promoted and no official paper order path is enabled by this patch.

## Validation

Commands run locally:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/research tests/test_v2_cli.py tests/test_strategy_router.py tests/test_strategy_governance.py tests/test_opportunities_endpoint.py tests/test_strategy_trade_reconciliation.py src/autobot/v2/tests/test_main_async_config.py -q
python -m compileall -q src
```

Focused validation completed before the final full targeted rerun:

```text
223 passed in 3.65s
31 passed in 1.12s
```

## Remaining Warnings

- The available OHLCV period is too short and lacks time-aligned bid/ask/depth. It cannot validate a paper candidate.
- Forty-eight scenario variants create selection bias. Walk-forward validation on longer data is mandatory.
- Marked exposure can drift above the planned cap after a price move. The entry allocator itself remains capped; a future research phase may study optional rebalancing, but must not add it to runtime without validation.

## Next Step

Deploy the retirement/research patch only after review, then keep runtime observation-only while daily OHLCV and microstructure collection continues. The next research action is a longer out-of-sample/walk-forward portfolio replay, not a paper or live promotion.
