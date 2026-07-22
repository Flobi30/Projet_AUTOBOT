# AUTOBOT — Shadow artifact readiness evidence (2026-07-22)

## Verdict

`GO_RESEARCH_ONLY_NO_SHADOW_ARTIFACT_CANDIDATE`.

The new `strategy-artifact-readiness-audit` was deployed at code commit
`bb20d4556bc25429b4118469868de04e8dc5577a`. It found no experiment that may
be registered as a governed shadow artifact. This is a correct fail-closed
outcome: no artifact, shadow activation, paper capital, live trading, order or
automatic promotion was created.

## Controlled registry migration

The first VPS audit correctly found a legacy experiment-registry schema missing
`experiments.research_campaign_id`. Before migration, an integrity-checked
local backup was created outside the Git worktree:

- source: `data/research/experiment_registry.sqlite3`;
- backup fingerprint: `289c6793408004219ffac4b5d569306372d0b9313acb26ff4c4e5aa4689fda40`;
- source fingerprint before migration: `da130aaf6b8e11f192f1b5ae2abec962c800d7b096f8b6d7be87260b40b38a2d`;
- SQLite integrity check: `ok`;
- foreign-key violations: `0`.

The existing append-only `ExperimentRegistry` migration was then run once in a
network-isolated container with only `data/research` writable. It added the
nullable campaign schema/index required by the already-tested migration. It
did not register an experiment, add a trial, advance a gate, create an
artifact, start runtime, or access any execution component. The preserved trial
count after migration is `43`.

## Post-migration read-only audit

The schema is now `CURRENT` and reports four experiments, zero registered
artifacts and zero evidence-ready candidates:

| Experiment | Latest evidence | Trials | Result |
| --- | --- | ---: | --- |
| `long_trend` / `regime_filtered_trend` | `DATA_CHECK / PASSED` | 11 | incomplete; no terminal shadow review or immutable holdout |
| `long_trend` / `regime_filtered_trend` | `NET_SMOKE / REJECTED` | 11 | terminal performance rejection |
| `funding_basis` / `funding_extreme_reversion` | `NET_SMOKE / INSUFFICIENT_DATA` | 6 | terminal insufficient data; successor remains subject to material-data and trial-floor rules |
| `funding_basis` / `funding_extreme_reversion` | `NET_SMOKE / REJECTED` | 15 | terminal performance rejection |

All records remain blocked from artifact registration because a terminal passed
`SHADOW_REVIEW`, immutable final-holdout review and the subsequent human
governance evidence are absent. The audit is intentionally non-authorizing.

## Validation

- local focused governance/registry/CLI suite: `93 passed`;
- local full suite: `1874 passed, 6 skipped`;
- VPS disposable no-network, read-only test container: `93 passed`;
- VPS health: healthy; orchestrator running; WebSocket connected; 14 instances;
- Git checkout and container image revision: `bb20d4556bc25429b4118469868de04e8dc5577a`;
- all execution-capable flags remain false; no matching live/order-submission
  log in the post-deploy window.

`PAPER_TRADING=true` remains a legacy runtime setting only. Its execution
adapter, router, test-trading, dynamic reallocation and all promotion/live
flags are explicitly false.

## Operational note

SQLite databases operating in WAL mode may need a writable shared-memory side
file even for a URI opened with `mode=ro`. Therefore, a fully isolated audit
container should consume a verified SQLite backup snapshot rather than bind the
live registry directory read-only. The audit module itself never initializes or
migrates a registry; this is a container/filesystem constraint, not a change to
the research data.

## Next safe action

Continue bounded data collection and research validation. A future shadow
artifact is permitted only after a new or continuing experiment passes every
immutable gate and a human separately records a current shadow-only risk
mandate and approval reference. No paper or live transition is in scope.
