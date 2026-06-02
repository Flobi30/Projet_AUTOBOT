# Strategy Regime Baseline Report - vps_2026_06_02_strategy_regime_comparison_baseline_comparison

## Summary

Buckets: `11`

## Results

| Strategy | Regime | Trades | Strategy Net | Best Baseline | Baseline Net | Delta | Beats No-Trade | Beats Best |
| --- | --- | ---: | ---: | --- | ---: | ---: | --- | --- |
| mean_reversion | chaos | 496 | -242.470512 | random_signal_same_frequency_regime | 125.000785 | -367.471297 | false | false |
| dynamic_grid | high_vol | 27 | -9.546466 | buy_and_hold_regime_segments | 338.818134 | -348.364600 | false | false |
| trend_momentum | high_vol | 6 | -7.609117 | buy_and_hold_regime_segments | 338.818134 | -346.427252 | false | false |
| mean_reversion | high_vol | 4 | 0.714304 | buy_and_hold_regime_segments | 338.818134 | -338.103831 | true | false |
| trend_momentum | chaos | 24 | 1.236346 | buy_and_hold_regime_segments | 252.495862 | -251.259515 | true | false |
| dynamic_grid | chaos | 312 | -130.593793 | random_signal_same_frequency_regime | 50.040744 | -180.634537 | false | false |
| mean_reversion | range | 200 | -106.172022 | no_trade | 0.000000 | -106.172022 | false | false |
| dynamic_grid | unknown | 13 | -27.415147 | no_trade | 0.000000 | -27.415147 | false | false |
| dynamic_grid | range | 37 | -20.529342 | no_trade | 0.000000 | -20.529342 | false | false |
| mean_reversion | unknown | 6 | -5.458526 | no_trade | 0.000000 | -5.458526 | false | false |
| dynamic_grid | low_activity | 2 | -2.408606 | no_trade | 0.000000 | -2.408606 | false | false |

## Baseline Details

### mean_reversion / chaos

| Baseline | Net PnL | Return | Trades | Notes |
| --- | ---: | ---: | ---: | --- |
| no_trade | 0.000000 | 0.000000% | 0 | Abstain from this strategy/regime bucket. |
| buy_and_hold_regime_segments | -3.342415 | -0.334241% | 14 | One first-to-last long per symbol inside matching regime bars, net of costs. |
| random_signal_same_frequency_regime | 125.000785 | 12.500079% | 496 | Deterministic random long baseline in same regime, requested trades=496. |

### dynamic_grid / high_vol

| Baseline | Net PnL | Return | Trades | Notes |
| --- | ---: | ---: | ---: | --- |
| no_trade | 0.000000 | 0.000000% | 0 | Abstain from this strategy/regime bucket. |
| buy_and_hold_regime_segments | 338.818134 | 33.881813% | 1 | One first-to-last long per symbol inside matching regime bars, net of costs. |
| random_signal_same_frequency_regime | 192.248280 | 19.224828% | 27 | Deterministic random long baseline in same regime, requested trades=27. |

### trend_momentum / high_vol

| Baseline | Net PnL | Return | Trades | Notes |
| --- | ---: | ---: | ---: | --- |
| no_trade | 0.000000 | 0.000000% | 0 | Abstain from this strategy/regime bucket. |
| buy_and_hold_regime_segments | 338.818134 | 33.881813% | 1 | One first-to-last long per symbol inside matching regime bars, net of costs. |
| random_signal_same_frequency_regime | 39.529493 | 3.952949% | 6 | Deterministic random long baseline in same regime, requested trades=6. |

### mean_reversion / high_vol

| Baseline | Net PnL | Return | Trades | Notes |
| --- | ---: | ---: | ---: | --- |
| no_trade | 0.000000 | 0.000000% | 0 | Abstain from this strategy/regime bucket. |
| buy_and_hold_regime_segments | 338.818134 | 33.881813% | 1 | One first-to-last long per symbol inside matching regime bars, net of costs. |
| random_signal_same_frequency_regime | 28.221984 | 2.822198% | 4 | Deterministic random long baseline in same regime, requested trades=4. |

### trend_momentum / chaos

| Baseline | Net PnL | Return | Trades | Notes |
| --- | ---: | ---: | ---: | --- |
| no_trade | 0.000000 | 0.000000% | 0 | Abstain from this strategy/regime bucket. |
| buy_and_hold_regime_segments | 252.495862 | 25.249586% | 2 | One first-to-last long per symbol inside matching regime bars, net of costs. |
| random_signal_same_frequency_regime | 131.462153 | 13.146215% | 24 | Deterministic random long baseline in same regime, requested trades=24. |

### dynamic_grid / chaos

| Baseline | Net PnL | Return | Trades | Notes |
| --- | ---: | ---: | ---: | --- |
| no_trade | 0.000000 | 0.000000% | 0 | Abstain from this strategy/regime bucket. |
| buy_and_hold_regime_segments | -3.342415 | -0.334241% | 14 | One first-to-last long per symbol inside matching regime bars, net of costs. |
| random_signal_same_frequency_regime | 50.040744 | 5.004074% | 312 | Deterministic random long baseline in same regime, requested trades=312. |

### mean_reversion / range

| Baseline | Net PnL | Return | Trades | Notes |
| --- | ---: | ---: | ---: | --- |
| no_trade | 0.000000 | 0.000000% | 0 | Abstain from this strategy/regime bucket. |
| buy_and_hold_regime_segments | -32.062914 | -3.206291% | 9 | One first-to-last long per symbol inside matching regime bars, net of costs. |
| random_signal_same_frequency_regime | -72.389583 | -7.238958% | 200 | Deterministic random long baseline in same regime, requested trades=200. |

### dynamic_grid / unknown

| Baseline | Net PnL | Return | Trades | Notes |
| --- | ---: | ---: | ---: | --- |
| no_trade | 0.000000 | 0.000000% | 0 | Abstain from this strategy/regime bucket. |
| buy_and_hold_regime_segments | -17.800534 | -1.780053% | 9 | One first-to-last long per symbol inside matching regime bars, net of costs. |
| random_signal_same_frequency_regime | -5.325781 | -0.532578% | 13 | Deterministic random long baseline in same regime, requested trades=13. |

### dynamic_grid / range

| Baseline | Net PnL | Return | Trades | Notes |
| --- | ---: | ---: | ---: | --- |
| no_trade | 0.000000 | 0.000000% | 0 | Abstain from this strategy/regime bucket. |
| buy_and_hold_regime_segments | -32.062914 | -3.206291% | 9 | One first-to-last long per symbol inside matching regime bars, net of costs. |
| random_signal_same_frequency_regime | -16.792518 | -1.679252% | 37 | Deterministic random long baseline in same regime, requested trades=37. |

### mean_reversion / unknown

| Baseline | Net PnL | Return | Trades | Notes |
| --- | ---: | ---: | ---: | --- |
| no_trade | 0.000000 | 0.000000% | 0 | Abstain from this strategy/regime bucket. |
| buy_and_hold_regime_segments | -22.918966 | -2.291897% | 4 | One first-to-last long per symbol inside matching regime bars, net of costs. |
| random_signal_same_frequency_regime | -3.732736 | -0.373274% | 6 | Deterministic random long baseline in same regime, requested trades=6. |

### dynamic_grid / low_activity

| Baseline | Net PnL | Return | Trades | Notes |
| --- | ---: | ---: | ---: | --- |
| no_trade | 0.000000 | 0.000000% | 0 | Abstain from this strategy/regime bucket. |
| buy_and_hold_regime_segments | -26.242214 | -2.624221% | 1 | One first-to-last long per symbol inside matching regime bars, net of costs. |
| random_signal_same_frequency_regime | -1.386555 | -0.138656% | 2 | Deterministic random long baseline in same regime, requested trades=2. |

## Safety

This report is research-only. It does not authorize paper or live execution.
