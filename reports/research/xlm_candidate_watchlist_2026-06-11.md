# XLM Candidate Watchlist - 2026-06-11

## Why XLM is watched

XLM is the only current symbol with positive best variants in both trend and mean-reversion shadow evidence.

| Engine | Variant | Closed trades | Net shadow PnL | Profit factor | Local status |
| --- | --- | ---: | ---: | ---: | --- |
| Trend | `trend_ema_momentum` | 41 | +4.9199 EUR | 1.3318 | candidate |
| Mean reversion | `mr_range_probe` | 7 | +0.3687 EUR | 2.5806 | candidate |

## Why it is not promoted

The router currently prefers the higher-scoring mean-reversion variant, but the promotion gate rejects it because:

- only 7 closed trades are available;
- the research validation status is not execution-ready;
- robustness across longer windows and costs is not established;
- evidence is concentrated on one symbol;
- research/paper parity is not proven.

The trend variant has a better sample of 41 trades, but it still requires independent research validation, stable out-of-sample evidence and a controlled promotion review. A positive local shadow cell is not sufficient evidence for official paper execution.

## Minimum evidence before official paper review

- at least 30 closed trades for the selected variant and at least 100 samples;
- positive net PnL after conservative costs;
- profit factor at least 1.25;
- win rate at least 45 percent;
- acceptable drawdown;
- execution-ready research workflow status;
- positive walk-forward evidence across multiple windows;
- no unexplained ledger or paper-parity gap;
- explicit human review.

## Safety decision

XLM remains watchlist/shadow only. Sizing is unchanged, official paper is not enabled, and live promotion remains false.
