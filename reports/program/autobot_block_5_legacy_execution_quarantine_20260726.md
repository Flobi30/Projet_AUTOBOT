# Block 5 — Legacy execution quarantine, 2026-07-26

## Scope

This hardening patch closes two legacy synchronous paths that were not used by
the active asynchronous runtime but could still be instantiated by an
accidental import or an obsolete caller.

It does not activate paper capital, live trading, strategy promotion, or any
order path.

## Changes

- `OrderRouter` observes the explicit observation-only runtime lock before it
  constructs `OrderExecutorAsync`.
- In observation-only mode, the router never starts a worker, has no executor,
  accepts no market, limit, stop, cancel, balance, or other legacy request, and
  returns the machine-readable reason
  `observation_only_order_router_disabled`.
- The synchronous `ReconciliationManager` now refuses construction in
  observation-only mode. This prevents its legacy corrective local position
  mutations from running outside the asynchronous reconciliation boundary.
- Router status exposes `observation_only` and `executor_available` for an
  auditable operational view.

## Boundary

The active `main_async` runtime already avoids the synchronous orchestrator
and reconciliation modules. This patch makes that separation fail closed for
future accidental callers as well. The asynchronous reconciler remains the
only reconciler eligible for a future executable mode, and it is itself
disabled in the current observation-only deployment.

## Verification

- targeted observation/router/reconciliation/production safety suite: 60
  passed;
- deployment/startup/kill-switch safety suite: 30 passed;
- touched modules compiled with `py_compile`;
- `git diff --check` passed;
- secret-pattern scan of changed files found no secret material.

## Deployment gate

Deploy only with the existing observation-only Docker configuration. After
deployment, verify that the container has no Kraken private credentials, no
private reconciliation starts, the health endpoint is healthy, and the source,
image, and container revision are aligned.

## Residual risk

Legacy synchronous modules remain in the repository for compatibility. They
are not a supported runtime path and must be retired or migrated under a
separate compatibility plan before any future paper-review decision.
