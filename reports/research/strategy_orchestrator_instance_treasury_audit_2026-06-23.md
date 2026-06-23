# Strategy Orchestrator and Instance Treasury Audit - 2026-06-23

## Verdict

`RESEARCH_ONLY_READY`

The repository already contains conservative split-policy and lineage-reading
components, but no production meta-allocator that can allocate capital from
strategy evidence to a child instance. The new research orchestrator fills that
measurement gap without connecting to runtime execution.

## Existing Duplication Components

| Component | Current behavior | Safety boundary | Missing link |
| --- | --- | --- | --- |
| `instance_split_policy.py` | Evaluates capital, PnL, PF, trade count, validation days, drawdown, scorecard, strategy status, failure mode, and split lifetime | Executor defaults to false; paper-only; live promotion must be false | No strategy/tactical treasury source |
| `instance_split_planner.py` | Reads `instance_lineage` in SQLite and produces a report | Read-only; never creates an instance | No allocation engine or child account |
| `persistence.py` / `instance_lineage` | Persists actual parent/child lineage from the runtime path | Durable lineage is available to real split policy | Not exposed as a research treasury contract |
| `instance_split_validation_harness.py` | Proves capital transfer and one-split mechanics in an isolated SQLite sandbox | Does not start runtime or create orders | Does not use multi-strategy evidence |
| `orchestrator_async.py` `check_spin_off` | Retains the historical runtime hook | Guarded by split policy and current feature flag | Must remain disabled until explicit future approval |

## Runtime Strategy Boundary

- Grid is archived/no-go and is not imported or executed by the new research
  orchestrator.
- High Conviction is the only current source eligible for virtual treasury
  allocation because it has portfolio-aware, costed walk-forward trade records.
- Trend and Mean Reversion are normalized as research signals only; they do not
  reserve virtual capital until each has equivalent portfolio-aware evidence.
- Relative Value remains `no_go` and emits no capital allocation.
- The real router, paper executor, risk manager, order executor, and Kraken
  integration are outside the new module's import graph.

## New Research Contracts

### Instance Treasury

`InstanceTreasury` defines an isolated account with:

- an instance and optional parent id;
- role (`parent`, `child`, or `standalone`);
- assigned treasury, realized equity, cash and reserved exposure;
- realized and unrealized PnL;
- instance, strategy and symbol exposure caps;
- daily loss and drawdown limits.

New allocation sizing uses **only realized equity and available cash**. Floating
PnL remains an observability field and cannot increase size.

### Standard Strategy Signal

`StrategyResearchSignal` has a stable boundary:

`strategy_name`, `symbol`, `timestamp`, `direction`, `confidence`,
`expected_move_bps`, `cost_profile`, `regime`, `reason`, `metadata`,
`research_only`, and `instance_id`.

High Conviction, BacktestSignal-based Trend/Mean Reversion, and Relative Value
all have adapters to this contract. The contract rejects `research_only=false`.

### Meta Scoring

Scores combine strategy evidence, pair evidence, regime, cost profile and
signal confidence. Candidate-paper recommendation remains blocked unless all
of the following hold:

- at least 50 closed trades;
- PF strictly above 1.30;
- max drawdown at or below 10%;
- at least 4 positive folds out of 5;
- no pair above 40% of positive PnL;
- positive net result after non-legacy costs;
- at least 7 validation days; and
- sufficient virtual treasury.

No recommendation changes the strategy registry, router, paper runtime, or
live permission.

## Future Child Compatibility

The orchestrator creates a **virtual** child-treasury proposal only. It builds
an `InstanceSplitEvidence` object with `lineage_verified=false` and an explicit
`InstanceSplitPolicyConfig(executor_enabled=false)`. This intentionally keeps
the plan blocked until a future, separately approved integration can:

1. load and verify real `instance_lineage`;
2. use official paper validation rather than research evidence;
3. create an audited treasury transfer; and
4. receive explicit human approval to enable any executor.

`ENABLE_INSTANCE_SPLIT_EXECUTOR` is not read as an execution control by this
research module. A host environment value of `true` cannot create a child.

## Remaining Gaps Before Any Real Split

- No strategy currently meets the candidate-paper evidence gate.
- High Conviction is still below 50 closed out-of-sample trades and has pair
  concentration risk in its latest run.
- Trend and Mean Reversion require their own portfolio-aware walk-forward
  evidence before they can receive virtual capital.
- The production lineage table is intentionally not read or written by the
  report runner.
- There is no approved runtime meta-allocator or split executor integration.

## Safety Confirmation

- Research only.
- No live permission.
- No paper order.
- No Kraken request.
- No child instance.
- No change to sizing, risk, strategy router, or runtime protection flags.
