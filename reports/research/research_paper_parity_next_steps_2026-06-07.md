# Research / Paper Parity Next Steps - 2026-06-07

## Objective

Prepare the next parity audit after longer OHLCV and microstructure data exist. Do not modify official paper runtime now.

## What To Compare Later

- research signals vs official paper decisions;
- prices used by replay vs official paper ledger;
- research cost model vs `PaperTradingExecutor`;
- entry/exit order direction;
- order sizes;
- spread and slippage assumptions;
- exit reasons;
- PnL gross/net;
- strategy governance and router decisions;
- risk manager rejections.

## Required Inputs

- fresh read-only VPS snapshot of `autobot_state.db`;
- official paper `trade_ledger`;
- historical OHLCV CSV for the same period;
- spread/depth snapshots or a documented spread proxy;
- batch validation report for the same symbols and strategies.

## Proposed Commands

```powershell
$env:PYTHONPATH='src'
python -m autobot.v2.cli research-paper-parity --run-id parity_after_long_ohlcv_2026_06_07 --state-db <snapshot-autobot_state.db> --symbols BTCZEUR,ETHZEUR,XLMZEUR,TRXEUR --strategies grid,trend,mean_reversion --output-dir reports/research/research_paper_parity_after_long_ohlcv --fee-bps 16 --spread-bps 8 --slippage-bps 4
```

Then compare any generated research matrix with official paper:

```powershell
$env:PYTHONPATH='src'
python -m autobot.v2.cli compare-paper-research --run-id compare_after_long_ohlcv_2026_06_07 --matrix-path <matrix.json> --state-db <snapshot-autobot_state.db> --output-dir reports/research/paper_research_comparison_after_long_ohlcv
```

## Current Rule

Until this parity is done:

- all strategies stay `research_only`;
- no strategy promotion;
- no instance duplication activation;
- no live activation.
