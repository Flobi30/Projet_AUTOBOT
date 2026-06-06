# Runtime Decision Influence Audit - 2026-06-06

## Classification

| Module | Classification | Can affect entries | Can affect exits | Can affect sizing | Can affect risk | Default recommendation |
| --- | --- | --- | --- | --- | --- | --- |
| Official grid strategy | active runtime | yes | yes | indirect | indirect | keep guarded, do not promote |
| `SignalHandlerAsync` | active runtime | yes | yes | indirect | yes | must stay behind cost/risk guards |
| `RiskManager` | active runtime | no | no | yes/limits | yes | mandatory |
| `OrchestratorRiskManager` | active runtime | no | no | yes/limits | yes | mandatory |
| `PaperTradingExecutor` | active paper | fills paper | closes paper | no | no | paper-only |
| `OrderRouter` | live-capable | yes if wired | yes if wired | no | no | disabled for live unless human-approved |
| `OrderExecutorAsync` | live-capable | yes | yes | no | no | live blocked |
| `ModuleManager` | active toggles | yes via modules | possible | possible | possible | audit defaults before enabling more |
| `rebalance_manager` | active by default in ModuleManager | possible | possible | yes | yes | observe/guard until proven |
| `auto_evolution` | active by default in ModuleManager | possible | possible | possible | possible | should be disabled or observe-only until evidence |
| `strategy_ensemble` | active by default in ModuleManager | possible | possible | no | no | do not let it route orders without governance |
| `momentum_scoring` | active by default in ModuleManager | possible | no | no | no | observe-only unless validated |
| `multi_indicator_vote` | active by default in ModuleManager | possible | no | no | no | observe-only unless validated |
| Kelly | imported/runtime module | no direct if not wired | no | yes | yes | disabled for execution until statistically significant |
| Pyramiding | disabled by default | yes if enabled | yes | yes | yes | keep disabled |
| XGBoost | disabled by default | yes if enabled | no | no | no | keep disabled |
| Sentiment | disabled by default | yes if enabled | no | no | no | keep disabled |
| Mean reversion runtime | disabled by default | yes if enabled | yes | no | no | keep research/shadow only |
| Setup optimizer | dashboard/research assist | possible if wired | possible | possible | no | observe-only |
| Strategy router | dashboard/research routing evidence | yes if wired | possible | no | no | must fail closed and respect governance |
| Strategy governance | promotion gate | blocks entries if enforced | blocks exits if enforced | no | yes | must be mandatory before router/runtime changes |

## Key Finding

The runtime has many modules that can become decision inputs. Several helper modules default active in `ModuleManager`, while experimental modules are disabled. The safest rule is: any module that can affect entries, exits or sizing must be either observe-only or gated by strategy validation and live safety.

## Recommended Hardening

1. Keep experimental modules disabled by default.
2. Make router/governance fail closed if registry is absent or invalid.
3. Require every runtime entry path to write a decision-ledger event.
4. Block any module from changing sizing without risk manager approval.
5. Do not let `auto_evolution`, Kelly or pyramiding affect paper/live until research scorecard and parity pass.
