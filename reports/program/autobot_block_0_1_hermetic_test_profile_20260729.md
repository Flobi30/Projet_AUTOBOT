# AUTOBOT Block 0.1 — Hermetic Test Profile

## Finding

The local default pytest command excluded performance benchmarks but not
external or end-to-end tests, while the isolated test image used a different
unit-only marker expression. This made the documented local and container
verification surfaces diverge.

## Change

- `pytest.ini` defines the single default hermetic profile: exclude
  `performance`, `external` and `e2e`.
- `Dockerfile.test` invokes pytest without a second marker expression, so it
  inherits that same profile and includes hermetic unit and integration tests.
- `AGENTS.md` now distinguishes no-network analyses from public-data
  collectors, which may reach only documented public endpoints and never have
  secret or runtime-state mounts.

## Scope

No strategy, data collector behaviour, runtime service, paper capital, live
trading, promotion, sizing or order path changed.

## Deployment

Hetzner maintenance is active. This local test/documentation hardening is not
deployed until controlled VPS validation can resume.
