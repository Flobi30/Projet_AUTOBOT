# AUTOBOT Block 2 - Immutable Final Holdout Gate - 2026-07-15

## Decision

`GO` for further research-only hardening. This change does not start shadow,
enable paper capital, promote a strategy, alter sizing or leverage, or enable
live trading.

## Change

An experiment cannot pass its terminal `SHADOW_REVIEW` gate until it has a
recorded review on its previously reserved immutable holdout. The recorded
review is explicitly non-optimizing and therefore cannot be used to select a
new parameter set.

The requirement is enforced twice:

- `ExperimentRegistry` rejects a passed terminal review without immutable
  holdout evidence;
- strategy-artifact construction and registration independently reject a
  shadow-capable artifact if that evidence is absent.

A research-only CLI command records the evidence:

```text
python -m autobot.v2.cli experiment-registry-record-final-holdout-review \
  --registry-path <registry.sqlite3> \
  --experiment-id <experiment_id> \
  --metrics-json '<json-object>'
```

The command only appends research evidence. Its output declares optimization,
paper capital, live and promotion as disabled.

## Evidence

- Functional commit: `82e8a3a0736059a7df6a68c9f8bf841fafb1828c`.
- Focused CLI, registry, artifact and validation suite: `81 passed`.
- Research suite: `396 passed`.
- Python compilation and diff checks: passed.
- Isolated immutable VPS release suite: `1592 passed` in 70.27 seconds.
- The same four pre-existing pytest warnings remain in non-async tests marked
  with `asyncio` in `src/autobot/v2/tests/test_order_router.py`.
- VPS deployment rebuilt `autobot-v2`; the source commit is aligned with the
  functional commit, `/health` is healthy, the WebSocket is connected and 14
  instances are running.
- Safety gates remain disabled: paper execution adapter, live confirmation,
  live strategy routing, automatic promotion and instance splitting.

## Residual scope

The holdout review records evidence but does not itself decide that an alpha is
valid. Statistical, cost, concentration, risk and human-approval gates remain
mandatory. The runtime continues to expose only non-executable previews; no
paper or live route was added.
