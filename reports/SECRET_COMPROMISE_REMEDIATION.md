# Secret Compromise Remediation Checklist (Mandatory for LIVE)

## 1) External revoke/rotation (required)
- Revoke all leaked SSH keys immediately.
- Rotate Kraken API key/secret pair.
- Rotate dashboard/API auth tokens.
- Rotate any infra secrets exposed in logs/history.

Set runtime acknowledgment only **after** the above is done:
- `LEAKED_SSH_KEY_ROTATED_ACK=true`

## 2) Fingerprint deny-list gate
Startup hard-blocks when `KRAKEN_API_KEY_FINGERPRINT` matches known compromised fingerprints.

## 3) Secret exposure marker gate
If `SECRET_EXPOSURE_MARKER_PATH` exists, startup is blocked.
Use this marker in incident response to prevent accidental restarts before remediation.

## 4) CI/push protection guidance
- Enable repository secret scanning and push protection in GitHub settings.
- Add pre-commit secret scanner (e.g. gitleaks) in developer workflows.
- Add CI job for secret scan on pull requests and default branch.

## 5) Incident closure evidence (keep)
- Revocation ticket IDs
- Rotation timestamps
- Affected hosts/accounts list
- Post-incident verification logs
