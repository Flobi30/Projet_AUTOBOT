# Advanced Quant Research Lab - 2026-06-26

## Verdict

PASS_WITH_WARNINGS for research integration.

AUTOBOT now has a research-only Advanced Market Analysis layer connected to the Strategy Orchestrator meta-score. The new diagnostics can influence simulated research allocation decisions, but they cannot create orders, promote strategies, activate live, or create child instances.

## A. Quant Tool Inventory

| Tool | Present | File(s) | Runner | Daily report | Useful | CPU/RAM | Priority | Action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| High Conviction walk-forward | yes | `high_conviction_walk_forward.py` | daily + CLI | yes | yes | medium | keep, needs longer data |
| Strategy Orchestrator / Treasury | yes | `strategy_orchestrator.py` | daily + CLI | yes | yes | medium | extended with market/robustness scoring |
| Monte Carlo trade bootstrap | yes | `robustness_experiments.py` | orchestrator diagnostics | yes | yes | bounded | keep nightly only |
| Spread/slippage/latency/fat-tail stress | yes | `robustness_experiments.py` | orchestrator diagnostics | yes | yes | bounded | keep conservative |
| Purged CV / embargo planning | yes | `purged_cv.py` | orchestrator diagnostics | yes | yes | low | planning evidence only |
| Deflated Sharpe proxy | yes | `statistical_validation.py` | orchestrator diagnostics | yes | yes | low | new, proxy only |
| Fractal/Hurst/vol clustering | yes | `fractal_features.py` | orchestrator diagnostics | yes | yes | low | kept descriptive |
| Advanced market analysis | yes | `advanced_market_analysis.py` | orchestrator diagnostics | yes | yes | low | new research-only layer |
| Research/Paper parity | yes | `research_paper_parity.py` | manual research | no | yes | medium | next validation phase |
| Loss attribution | yes | `loss_attribution.py` | research CLI | no | yes | low | keep for post-run audits |
| Validation matrix | yes | `validation_matrix.py` | research CLI | no | yes | medium | keep for batch campaigns |
| Relative Value engine | yes | `relative_value_engine.py` | manual research | indirect | limited | low | stays no_go/no_capital |
| Grid experiment runner | yes | `grid_experiment_runner.py` | manual research | no | archived | medium | keep archived for rollback/audit |
| Optuna | absent | - | - | no | future | high if abused | low now | do not add yet |
| LightGBM/meta-learner | absent | - | - | no | future | medium/high | medium later | only after stable labels |
| FAISS memory | absent | - | - | no | future | medium | low now | defer |
| Qlib/FinRL/vectorbt/Backtrader/Nautilus/LEAN | absent as dependencies | - | - | no | architectural references | high | low now | do not install now |

## B. Advanced Market Analysis

New standardized research signals:

- `volatility_regime_signal`
- `trend_regime_signal`
- `mean_reversion_regime_signal`
- `fractal_market_state`
- `turbulence_risk_score`
- `fat_tail_risk_score`
- `monte_carlo_survival_score`
- `cost_survival_score`
- `liquidity_risk_score`
- `overfitting_risk_score`
- `relative_value_state`
- `market_confidence_score`

Inputs:

- Local OHLCV bars from research collection.
- Optional spread/depth microstructure profiles.
- Robustness report outputs.
- Deflated Sharpe proxy outputs.

Limits:

- The layer is descriptive, not a price predictor.
- No bid/ask history is used unless daily spread/depth snapshots exist.
- DSR is a proxy because exact trial count and full strategy-selection history are not yet fully modelled.

## C. Strategy Orchestrator Integration

Pipeline now represented in research:

`Market Data -> Advanced Market Analysis -> Strategy Signal Layer -> Meta-Scoring -> Instance Treasury -> Risk Guard -> Research Decision`

Strategy signal status:

- High Conviction: capital-eligible only inside research simulations.
- Trend Momentum: standardized signals, research_signal_only until portfolio-aware validation exists.
- Mean Reversion: standardized signals, research_signal_only until portfolio-aware validation exists.
- Relative Value: no_go / research_signal_only / no_capital.
- Grid: archived / no_go.

Meta-score now blends:

- strategy score;
- pair score;
- regime score;
- market-analysis score;
- robustness score;
- Monte Carlo survival;
- Purged CV planning score;
- Deflated Sharpe score;
- cost survival;
- liquidity;
- overfitting risk;
- confidence;
- profit-factor quality.

Research decisions are restricted to:

- `no_trade_research`
- `observe_research`
- `simulated_allocation_low`
- `simulated_allocation_medium`
- `simulated_allocation_high`
- `candidate_review_blocked`
- `candidate_review_possible`
- `high_quality_candidate`
- `paper_limited_future`
- `scale_candidate_future`

None of these decisions can create an order.

## D. Profit Factor / Activity Gates

Progressive gates implemented in `statistical_validation.py`:

| Gate | Minimum evidence | Decision |
| --- | --- | --- |
| A | PF > 1.10 | learning/observe only |
| B | >=50 trades, PF > 1.30, DD <=10%, costs, folds, concentration | candidate_review_possible |
| C | >=75 trades, PF > 1.50, DD <=8%, MC/stress/DSR acceptable | high_quality_candidate |
| D | >=100 trades, PF > 1.70, DD <=7%, validation days and low overfit | paper_limited_future |
| E | >=150 trades, PF > 2.00, DD <=6%, robust stress and low concentration | scale_candidate_future |

Important: `candidate_paper_recommended` remains false. The new gates recommend research review only.

Current expected status remains cautious:

- Grid: archived/no_go.
- Relative Value: no_go/no_capital.
- Trend/MR: research_signal_only until portfolio-aware validation is added.
- High Conviction: active_research, still dependent on data accumulation and robust fold evidence.

## E. Server Budget

The added calculations are lightweight:

- no heavy ML dependency;
- no Optuna/LightGBM/FAISS/Qlib/FinRL;
- no runtime service;
- daily research container remains the intended execution context;
- bootstrap iterations stay bounded by orchestrator config;
- no websocket/runtime coupling.

The existing isolated daily research runner remains the right place to run this.

## F. Safety

Confirmed by design:

- research_only: true.
- no order path imports added.
- no paper/live runtime import added.
- no Kraken private client import added.
- no state DB/persistence write added.
- no live flag changed.
- no strategy promoted.
- no child instance created.
- split executor remains forced off in the research orchestrator.

## Added

- `src/autobot/v2/research/advanced_market_analysis.py`
- `src/autobot/v2/research/statistical_validation.py`
- Strategy Orchestrator meta-score integration.
- Daily runner passes microstructure profiles into the orchestrator.
- Targeted tests for research-only market analysis, statistical validation, and orchestrator safety.

## Must Wait

- Real paper promotion.
- Live activation.
- Split executor.
- Heavy ML/meta-learner.
- Full DSR/PBO with complete trial registry.
- Research/paper parity enforcement using fresh official paper ledgers.

## Next Step

Let the nightly research collection run, then compare:

1. High Conviction PF and drawdown under `paper_current_taker` and `research_stress`.
2. Market confidence by symbol.
3. PF gate status per strategy.
4. Whether Trend/MR deserve portfolio-aware walk-forward runners.
