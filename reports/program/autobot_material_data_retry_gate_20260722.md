# AUTOBOT — Material derivatives research retry gate — 2026-07-22

## Decision

**GO — guard added; no experiment rerun.**

The new `research-retry-eligibility` command is a read-only research gate. It
does not change research memory, experiment registry, scheduler state, trial
claims, holdouts, strategy status, shadow, paper or live state.

The VPS assessment correctly returned:

```text
funding_basis / funding_extreme_reversion
→ BLOCKED_PRIOR_PERFORMANCE_REJECTION
```

The current canonical derivatives data is materially richer than the early
data-missing records, but the latest terminal record is
`p19_funding_basis_smoke_20260717` with `REJECT_FAST` after a negative net-edge
result. Data growth alone must not relaunch the same economic thesis or hide
the trial history. A distinct hypothesis/template must be specified and pass
the normal experiment-registration process before any future research run.

## Implemented boundary

- `src/autobot/v2/research/research_retry_eligibility.py`
  - deterministic, host-independent signature for funding, same-quote basis
    and open-interest history;
  - explicit `INSUFFICIENT_DATA`/`DATA_MISSING` capability transitions may
    identify a separately named future campaign only;
  - prior or later `REJECT_FAST`/`REJECTED`/`NO_GO` outcomes remain blocked;
  - campaign/run/report/path changes alone cannot make a retry eligible;
  - reports a predecessor trial-count floor so a successor cannot ignore
    earlier parameter-search evidence;
  - no imports from the runtime, router, executor, paper engine or bounded
    research coordinator.
- `research-retry-eligibility` CLI command for an auditable, optional
  JSON/Markdown decision report.
- Architecture documentation and 24-layer coverage updated for the research
  memory boundary.

## VPS evidence

Runtime source commit and image label during validation:

```text
ee0f5dcfcb16d78f0dd70e922a3dc50917f053e3
```

Read-only disposable-container assessment:

```text
funding history: 55,342 rows, 2025-07-02 → 2026-07-22
basis history:   58,910 rows, 2025-07-17 → 2026-07-22
OI history:      53,298 rows, 2025-07-17 → 2026-07-22
signature:       28ede7125b3610bc0602b21db1628725dedfccfbf60c55ff587c7690a7f69a3a
```

All three capabilities are canonical Kraken Futures research data with no
implicit quote conversion. The new command ran with `--network none`, a
read-only source mount and `--no-write-report`.

## Tests

Local:

```text
python -m compileall -q src
pytest tests/research/test_research_retry_eligibility.py -q  → 10 passed
pytest tests/research/test_data_capability_scanner.py \
       tests/research/test_alpha_hypothesis_scheduler.py \
       tests/research/test_experiment_registry.py tests/test_v2_cli.py -q
→ 89 passed
pytest -q → 1859 passed, 6 skipped
```

VPS disposable container, no network and read-only source:

```text
pytest tests/research/test_research_retry_eligibility.py \
       tests/research/test_data_capability_scanner.py \
       tests/research/test_experiment_registry.py -q
→ 39 passed
```

The test set proves same-data blocking, current-capability blocking, a
missing-data-only new-campaign candidate, performance-rejection blocking,
later-result anti-cherry-picking, read-only SQLite memory access, no order-path
imports, and execution flags remaining false.

## Safety confirmation

- Container `autobot-v2`: healthy; WebSocket connected; 14 instances.
- All deployed research/runtime timers restored active after rebuild.
- Paper execution adapter/router, test trading, capital reallocation and
  autopilot remain disabled.
- Live confirmation, live router, auto-promotion and split executor remain
  disabled.
- No runner was scheduled, no experiment was registered, no order was created
  and Grid remains no-go.

## Remaining work

The evidence gate intentionally does not retrofit old memory records with a
current signature. The next *new* research campaign, if a materially distinct
hypothesis is registered, must record its current material signature and the
predecessor trial floor at registration. It must then pass data check, net-cost
smoke, walk-forward, stress and immutable-holdout validation before any shadow
consideration.
