# AUTOBOT Quant Tools Inventory - 2026-06-24

## Scope and Safety

- Scope: repository audit plus lightweight research diagnostics only.
- No runtime router, paper executor, live executor, Kraken private client, strategy promotion, or instance-split executor was changed.
- Every added result is `research_only`; `paper_candidate_allowed` and `live_promotion_allowed` remain `false`.

## Existing Research and Validation Foundation

| Tool | State | Main files | Current runner | Daily report | Orchestrator use | Priority | Recommended action |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Generic walk-forward | present | `research/walk_forward.py` | validation CLI and matrix | no | indirect evidence | high | keep as the chronological validation baseline |
| Strategy/regime walk-forward | present | `research/strategy_regime_walk_forward.py` | matrix and standard audit | no | not yet | medium | use once trend/mean-reversion receive portfolio replays |
| High Conviction walk-forward | present | `research/high_conviction_walk_forward.py` | daily collector and CLI | yes | direct | high | continue collecting out-of-sample evidence |
| Robustness guard | present, runtime-oriented | `robustness_guard.py` | runtime guard | no | no | low | do not reuse for research promotion; it is a different boundary |
| Validation matrix | present | `research/validation_matrix.py` | matrix, strategy experiments, standard audit | no | indirect evidence | high | retain for batch comparisons |
| Research/paper parity | present | `research/research_paper_parity.py` | parity CLI | no | no | high | run after enough official paper evidence exists |
| Loss attribution | present | `research/loss_attribution.py` | matrix and standard audit | no | no | high | retain for failure-mode diagnosis |
| Metrics engine | present | `research/metrics_engine.py` | backtests, replays and reports | indirect | direct | high | canonical net-of-cost metrics source |
| Backtest engine | present | `research/backtest_engine.py` | backtest/matrix CLI | no | indirect | high | retain as event-driven validation layer |
| Standard audit | present | `research/standard_audit_runner.py` | standard-audit CLI | no | no | medium | run periodically, not every daily collection |
| Daily collector | present | `research/daily_data_collection_runner.py` | `collect-research-daily` | yes | direct | high | keep public-data-only scheduled collection |
| Strategy Orchestrator / Treasury | present | `research/strategy_orchestrator.py` | daily collector and CLI | yes | direct | high | preserve virtual-only allocation and split plan |

## Advanced Tools

| Tool | State | Main files | Current runner | Daily report | Orchestrator use | Priority | Recommended action |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Monte Carlo trade sequence | added | `research/robustness_experiments.py` | Strategy Orchestrator | yes | observation-only | high | use to flag fragile distributions; never as a promotion gate alone |
| Bootstrap trade sequence | added | `research/robustness_experiments.py` | Strategy Orchestrator | yes | observation-only | high | require at least 50 closed trades before interpreting results |
| Spread/slippage/latency shocks | added | `research/robustness_experiments.py` | Strategy Orchestrator | yes | observation-only | high | keep shocks conservative and one-way only |
| Fat-tail loss shock | added | `research/robustness_experiments.py` | Strategy Orchestrator | yes | observation-only | high | use as a sensitivity test, not a market forecast |
| Purged CV / embargo | added as planning layer | `research/purged_cv.py` | Strategy Orchestrator | yes | observation-only | high | use for future parameter/model selection; chronological walk-forward remains mandatory |
| PBO / Deflated Sharpe | partial proxy | `quant_validation.py`, `robustness_guard.py` | validation/runtime guard | no | no | medium | keep as warnings; do not call the proxies academic PBO/DSR proof |
| Markov / entropy regime | present | `regime_features.py`, `research/regime_context.py` | opportunity/regime reports | partial | indirect | medium | retain as descriptive regime context |
| Fractal / Hurst / fractal dimension | added | `research/fractal_features.py` | Strategy Orchestrator | yes | observation-only | medium | collect evidence first; no allocation effect |
| Volatility clustering | added, descriptive | `research/fractal_features.py` | Strategy Orchestrator | yes | observation-only | medium | use alongside existing volatility metrics, not as a standalone signal |
| Optuna | absent | - | - | no | no | low | defer until datasets are longer and parameter trials are governed |
| FAISS memory | absent | - | - | no | no | low | defer; no trustworthy labeled pattern store yet |
| LightGBM/meta-learner | absent | - | - | no | no | low | defer until feature labels and purged validation are mature |
| vectorbt / Backtrader / NautilusTrader / Backtesting.py | absent | - | - | no | no | low | do not add a second simulator while AUTOBOT's own replay engine is the validation source |

## Dependency Check

- `numpy`, `pandas` and `scipy` are available in the local environment but are not required by the added diagnostics.
- `statsmodels`, `optuna`, `faiss`, `lightgbm`, `vectorbt`, `backtrader`, `nautilus_trader` and `backtesting` are not declared runtime dependencies.
- Relative Value therefore keeps its optional Engle-Granger path isolated; it is not upgraded or promoted by this work.

## Design Decisions

- Mean-field games are useful as a conceptual model for a future allocator: independent research strategies compete for one virtual treasury. They are not suitable as a lightweight first implementation.
- Fractal-chaotic volatility concepts are represented only as Hurst, fractal-dimension and volatility-clustering observations. They do not change signal generation, sizing, stops or execution.
- Relativistic/fat-tail pricing concepts are represented only as conservative downside stress. They are not used as a spot pricing model.
- Human behavioural concepts are not market signals. No human-override feature was added.

## Limits

- Trend and Mean Reversion currently provide research signals but do not yet produce portfolio-aware out-of-sample `TradeRecord` sets. Their robustness diagnostics would be premature.
- The High Conviction sample is still below the existing 50 closed-trade review threshold. The new bootstrap correctly reports `insufficient_sample` rather than declaring a strategy robust.
- Purged CV is a research split planner, not a complete CPCV/PBO implementation and not a replacement for chronological walk-forward.

## Next Action

Accumulate more OHLCV and microstructure data, then add equivalent portfolio-aware walk-forward replays for Trend and Mean Reversion. Only after that should the shared virtual treasury compare strategies on the same capital and cost basis.
