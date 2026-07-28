# AUTOBOT Block 3 — runtime shadow decision bridge — 2026-07-29

## Decision

**GO_LOCAL / REWORK_FOR_VPS_VALIDATION**

This bounded increment remains research/shadow only. It does not activate
paper capital, live trading, automatic promotion, sizing, leverage, a broker
client or any order path.

## Delivered boundary

Legacy runtime BUY signals now enter a fail-closed canonical bridge:

```text
TradingSignal → AlphaSignal → TargetPortfolio → RiskDecision
```

The bridge accepts only a complete set of immutable, point-in-time evidence:

- explicit market identity and matching strategy/signal/data identifiers;
- a shadow-eligible `StrategyArtifactReference`;
- verified feature vectors matching the artifact and market;
- a `CAPACITY_OK` review with the same decision identity;
- `BoundShadowRiskEvidence` bound to the artifact, signal, target, capacity
  review, mandate and health state.

Any absent, stale or inconsistent input is recorded as a rejected shadow
decision. The only verified outcome is itself non-executable: its
`RiskDecision` is explicitly rejected with `runtime_shadow_observation_only`.
It creates neither an intent nor an execution command.

`SignalHandlerAsync` records the canonical payload under
`shadow_contract_decision`. The former `shadow_contract_preview` field remains
as a read-compatible alias while callers migrate; it now carries the same
non-executable decision payload.

## Deliberate limit

The active legacy strategy producers do not yet provide the required immutable
artifact, feature, capacity and risk-evidence contracts. They are therefore
rejected closed with a concrete missing-evidence reason. This is intentional:
the bridge must not fabricate a market mapping, cost, capacity or health fact
to make a legacy signal appear shadow-ready.

## Verification

| Check | Result |
| --- | --- |
| Bridge, legacy preview and async handler focused tests | `39 passed` |
| Portfolio, contract shadow and static strategy-boundary tests | `35 passed` |
| Shadow ledger, adapter safety and strategy-router tests | `23 passed` |
| Handler and order-router regression group | `78 passed` |
| Full suite | `1949 passed, 6 skipped, 2 deselected` |
| Python compilation | passed |
| `git diff --check` | passed |

The tests prove complete-provenance acceptance stops without an intent or
command; missing capacity/risk evidence, non-BUY legacy signals and retired
Grid aliases fail closed; and the bridge imports neither execution nor legacy
allocation modules.

## VPS gate

No VPS deployment was attempted for this increment. SSH to `autobot-vps` was
timing out at the latest check, so GitHub/VPS/container alignment is unproven
for this code. No service, container, database, runtime flag or server data was
changed locally or remotely.

Once SSH recovers, deploy only through
`bash deploy/rebuild-autobot-image.sh`, then run the existing read-only runtime
evidence smoke. The system must still show paper/live/promotion disabled before
this local gate can become a verified layer.
