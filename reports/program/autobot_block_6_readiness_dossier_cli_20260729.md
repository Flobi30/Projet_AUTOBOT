# AUTOBOT — Block 6 readiness dossier CLI — 2026-07-29

## Decision

`GO_LOCAL_WAITING_FOR_VPS`.

The local readiness path can now consume the exact non-secret JSON record
emitted by `deploy/verify-autobot-runtime-evidence.sh` and bind it to the
source revision that is under review. The resulting dossier remains a human
review artifact only: it cannot enable paper capital, live trading or automatic
promotion.

## Scope

- Added `paper-readiness-dossier` to the research CLI.
- Added strict parsing for `RuntimeDeploymentEvidence`: all expected fields are
  required, and unknown fields are rejected rather than ignored.
- Required an explicit expected source commit whenever deployment evidence is
  supplied. A commit mismatch is a readiness blocker.
- Recorded safe deployment provenance in the markdown dossier.

## Verification

- `python -m compileall -q src/autobot/v2/research/resilience_readiness.py src/autobot/v2/cli.py`
- `$env:PYTHONPATH='src'; python -m pytest tests/research/test_resilience_readiness.py tests/test_v2_cli.py -q`
- `git diff --check`
- `$env:PYTHONPATH='src'; python -m pytest -q --disable-warnings` →
  `1988 passed, 6 skipped, 2 deselected`

The focused suite passed with 73 tests before the full local non-regression
suite. No runtime database, Docker service, VPS, paper-capital flag, live flag,
promotion flag or order path was changed.

## VPS follow-up after Hetzner maintenance

From the checked-out VPS commit, run only the controlled rebuild and verifier:

```bash
bash deploy/rebuild-autobot-image.sh
bash deploy/verify-autobot-runtime-evidence.sh > /tmp/autobot_runtime_evidence.json
```

Then use the emitted JSON with `paper-readiness-dossier` and the same Git
commit. If the verifier cannot produce fresh aligned evidence, the dossier must
remain `NOT_READY_FOR_HUMAN_PAPER_REVIEW`.
