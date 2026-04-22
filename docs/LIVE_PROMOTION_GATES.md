# Live Promotion Gates (Paper -> Micro-Live -> Small-Live)

## Stage 1: paper
Required:
- `DEPLOYMENT_STAGE=paper`
- `PAPER_TRADING=true`
- Startup attestation passes.

## Stage 2: micro_live
Required:
- `DEPLOYMENT_STAGE=micro_live`
- `PAPER_TRADING=false`
- `LIVE_TRADING_CONFIRMATION=true`
- `API_KEY_ASSIGNMENT_MODE=dedicated`
- `UNIQUE_BOT_ID == API_KEY_ASSIGNED_BOT_ID`
- `ALLOW_SHARED_API_KEY=false`
- `MAX_LIVE_INSTANCES<=1`
- No compromise marker and leaked-key rotation ack set.

## Stage 3: small_live
Required:
- all micro_live requirements
- `DEPLOYMENT_STAGE=small_live`
- `SMALL_LIVE_APPROVED=true`
- `MAX_LIVE_INSTANCES<=2`
- reconciliation baseline + clock drift checks pass
- global kill switch not tripped

## Secret leak incident policy (blocking)
If a secret leak incident occurred:
1. Revoke/rotate externally.
2. Set and keep `data/compromised_secret.marker` until incident closure.
3. Startup and CI promotion must remain blocked while marker exists.
4. After closure evidence is archived, remove marker and set:
   - `LEAKED_SSH_KEY_ROTATED_ACK=true`

## Push protection / CI guidance
- Enable GitHub Secret Scanning and Push Protection at repository settings level.
- Keep `security-and-audit.yml` mandatory in branch protection checks for critical branches (`main`, `master`, `work`).
- Mark these checks as required before merge: `Python tests (unit)`, `Python tests (integration)`, and `Dashboard build + lint`.
