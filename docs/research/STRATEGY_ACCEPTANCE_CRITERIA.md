# AUTOBOT Strategy Acceptance Criteria

This document defines the minimum evidence required before a strategy can move
from research to official paper execution, and later to human live review. These
thresholds are deliberately conservative and realistic for a small crypto spot
bot. Passing them does not authorize live trading.

## Workflow

Allowed non-terminal workflow:

1. `learning`
2. `candidate`
3. `backtest_passed`
4. `walk_forward_passed`
5. `shadow_passed`
6. `paper_validated`

Terminal statuses:

- `rejected`
- `retired_from_execution`

No strategy should skip a stage. A strategy may be rejected or retired from any
stage. Live trading remains disabled unless there is an explicit human decision
outside this automated workflow.

## Minimum Backtest Evidence

A backtest can only be marked as passed when all of the following are true:

- closed trades: at least 30
- net PnL: greater than 0 after fees and slippage
- profit factor: at least 1.25
- max drawdown: at most 12 percent of tested capital
- Sharpe: at least 0.25, with Sortino reported when available
- out-of-sample periods: at least 1
- fees included: yes
- slippage included: yes
- baseline comparison included: yes
- baseline delta: non-negative versus the relevant baseline

These are not aggressive return goals. They are a minimum sanity filter to avoid
promoting obviously weak or unproven systems.

## Walk-Forward Evidence

`walk_forward_passed` requires:

- all backtest evidence above
- train/test or rolling out-of-sample separation documented
- no future data in indicators, labels, sizing, exits, or regime features
- no degradation that turns expectancy negative in the test slices
- stable behavior across more than one symbol or clearly documented
  pair-specific justification

The current AUTOBOT `pf_validation.walk_forward_validate` is a lightweight PnL
sequence check, not a full event-driven market replay. It can support a warning
or early signal, but it is not sufficient alone for live readiness.

## Shadow Evidence

`shadow_passed` requires:

- at least 30 closed shadow trades for the strategy or variant
- net shadow PnL greater than 0 after fees and slippage
- shadow profit factor at least 1.25
- maximum drawdown within the documented limit
- comparison against `no_trade` and the current official paper engine
- reconciliation showing that shadow assumptions are not materially better than
  official paper fills

No-loss shadow samples are not accepted as robust until they have at least 50
closed trades.

## Official Paper Evidence

`paper_validated` requires:

- at least 100 closed official paper trades
- net official paper PnL greater than 0 after fees and slippage
- paper profit factor at least 1.20
- paper max drawdown at most 10 percent
- performance not dominated by one single pair unless this is explicitly
  documented as a pair-specific strategy
- no unresolved ledger/reconciliation gaps
- no critical market-data-quality issue
- current live mode still disabled

Paper validation means "ready for human review", not "ready for automatic live".

## Required Baselines

Every strategy report must include the applicable baselines:

- `no_trade`: cash preservation, zero fees, zero slippage
- `buy_and_hold_symbol`: simple asset exposure over the same period when
  meaningful
- `random_entry_same_frequency`: same trade count/frequency with randomized
  entries when data supports it
- `current_official_engine`: especially when validating a shadow replacement

If a baseline cannot be computed, the report must state why and the strategy
cannot move beyond `candidate`.

## Cost And Execution Realism

All validation must report:

- exchange fees or configured fee bps
- spread or order-book quality assumption
- slippage assumption
- whether market, limit, stop or simulated threshold fills are used
- partial-fill and queue assumptions
- minimum order and precision constraints

If fills are assumed perfect, the result is learning-only.

## Regime Breakdown

Reports should split performance by regime where possible:

- range
- trend
- chaos
- low activity
- high volatility
- unknown

If regime data is unavailable, the report must say so. A strategy cannot be
considered robust just because it performs in one hidden regime.

## Automatic Rejection Flags

Reject or keep in learning when any of these are true:

- positive gross PnL but negative net PnL after fees/slippage
- profit factor below 1.0 after enough closed trades
- performance only appears after excessive parameter search
- out-of-sample result is negative while in-sample is positive
- one pair explains nearly all profit without pair-specific thesis
- official paper results contradict shadow results
- strategy needs live-only assumptions to work
- missing fees, slippage, baseline, or out-of-sample period

## Configurability

The code-level guard in `src/autobot/v2/strategy_validation_registry.py` exposes
the threshold values through `StrategyAcceptanceCriteria`. Runtime thresholds may
later be moved to `.env`, but the defaults here are the current research
standard.
