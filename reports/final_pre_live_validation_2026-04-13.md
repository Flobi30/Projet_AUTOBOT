# FINAL PRE-LIVE VALIDATION — AUTOBOT
Date: 2026-04-13

## A) Final readiness assessment

### Implemented and enforced now
- Startup attestation hard-blocks are active for environment validity, live confirmation, dashboard token, risk limits, secret compromise markers, leaked-key ack, exchange/API health checks, nonce health, clock drift, reconciliation baseline, and promotion stage gates.
- Dedicated-key-per-bot guardrails are enforced in live stages (`micro_live`, `small_live`) via `API_KEY_ASSIGNMENT_MODE=dedicated`, `ALLOW_SHARED_API_KEY=false`, and `UNIQUE_BOT_ID == API_KEY_ASSIGNED_BOT_ID`.
- Global kill-switch state is persisted and propagated across processes through shared state storage.
- Reconciliation now includes balances and deeper parity checks for fills/fees/PnL mismatch thresholds.
- CI security workflow includes secret scanning + dependency audits and promotion blocking on compromise marker.

### Readiness summary
- Paper mode: technically ready if startup/CI controls are configured as required.
- Micro-live: conditionally acceptable with strict envelope and mandatory ops controls.
- Small-live: not yet acceptable due unresolved operational and reconciliation depth gaps.

---

## B) Pre-live checklist

### 1. Required environment variables
Mandatory (startup blocks otherwise):
- APP_ENV=production
- DEPLOYMENT_STAGE in {paper,micro_live,small_live}
- DASHBOARD_API_TOKEN (non-empty)
- MAX_DRAWDOWN_PCT
- RISK_PER_TRADE_PCT
- MAX_POSITION_SIZE_PCT
- LEAKED_SSH_KEY_ROTATED_ACK=true

Live-only mandatory:
- PAPER_TRADING=false
- LIVE_TRADING_CONFIRMATION=true
- API_KEY_ASSIGNMENT_MODE=dedicated
- ALLOW_SHARED_API_KEY=false
- UNIQUE_BOT_ID
- API_KEY_ASSIGNED_BOT_ID (must equal UNIQUE_BOT_ID)
- MAX_LIVE_INSTANCES <= 1 (micro_live)

For small_live promotion:
- SMALL_LIVE_APPROVED=true

Compromise controls:
- SECRET_EXPOSURE_MARKER_PATH must NOT exist
- KRAKEN_API_KEY_FINGERPRINT must not match denylist

### 2. Required GitHub settings
- Branch protection with mandatory required checks:
  - Security and Dependency Audit workflow
- Require pull request reviews
- Enable GitHub Secret Scanning
- Enable Push Protection for secrets

### 3. Required deployment settings
- One bot per dedicated API key (no shared key live deployment)
- Persistent writable `data/` volume shared by bot process components (for nonce + global kill switch DB)
- Clock synchronization enabled (NTP/chrony)
- Immutable logs retained for post-incident analysis

### 4. Required exchange/API settings
- Kraken API key enabled only for required scopes
- IP whitelist enabled where possible
- No key reuse across hosts/bots in live stages
- Exchange connectivity healthy prior to startup

### 5. Required dedicated-key-per-bot settings
- UNIQUE_BOT_ID == API_KEY_ASSIGNED_BOT_ID
- API_KEY_ASSIGNMENT_MODE=dedicated
- ALLOW_SHARED_API_KEY=false

### 6. Required recovery/kill-switch procedures
- On kill switch trigger:
  1) Block new orders
  2) Capture reason/timestamp from global kill state
  3) Perform reconciliation review
  4) Operator remediation
  5) Explicit recovery acknowledgment before restart

---

## C) Micro-live runbook

### Step 0 — Preflight only (no trading)
1. Set `PREFLIGHT_ONLY=true`
2. Start bot process
3. Confirm startup attestation passes and process exits without starting trading loop

### Step 1 — Safe startup
1. Ensure compromise marker absent:
   - `test ! -f data/compromised_secret.marker`
2. Ensure live controls set (env list above)
3. Start bot with `DEPLOYMENT_STAGE=micro_live` and `PAPER_TRADING=false`
4. Confirm no startup attestation error in logs

### Step 2 — Verify startup attestation
- Confirm logs indicate attestation passed before orchestrator start.
- If blocked, resolve exact failing check and retry.

### Step 3 — Verify reconciliation
- Execute a minimal controlled trade and confirm no reconciliation mismatch alerts.
- Confirm post-trade parity checks run and do not trip kill switch.

### Step 4 — Verify kill switch
- Trigger controlled safety event in staging/preflight (e.g., simulated repeated API failures).
- Verify global kill state flips to tripped and trading actions stop.

### Step 5 — Verify nonce health
- Confirm nonce checks pass at startup.
- Watch for invalid nonce escalation; repeated nonce errors must trigger safety stop.

### Step 6 — Verify no compromised-secret blocker
- Ensure `LEAKED_SSH_KEY_ROTATED_ACK=true`
- Ensure denylisted fingerprint not configured
- Ensure compromise marker absent

### Step 7 — Safe stop
1. Stop accepting new actions
2. Let in-flight work settle
3. Stop orchestrator cleanly
4. Archive logs and state snapshots

---

## D) Updated GO / NO-GO

### Paper
- **GO** (with required env + CI settings configured).

### Micro-live
- **CONDITIONAL GO** only if all startup gates, CI required checks, dedicated key guardrails, and runbook steps are satisfied.

### Small-live
- **NO-GO** currently.
- Reason: reconciliation depth and operations governance still not at required maturity for larger capital exposure.

---

## E) Remaining blockers (ranked)

1) Cross-host/global coordination robustness
- Probability: Medium
- Impact: High
- Difficulty: Medium
- Why: current shared-state approach is strong on single-host/shared-volume, but not a full distributed control-plane.

2) Per-trade reconciliation depth vs exchange truth
- Probability: Medium
- Impact: High
- Difficulty: Medium-High
- Why: deeper parity exists but full deterministic trade-by-trade reconciliation still needs expansion.

3) Operational governance hardening (branch protection + mandatory checks enforcement)
- Probability: Medium
- Impact: Medium-High
- Difficulty: Low-Medium
- Why: CI workflows exist; repository/org enforcement must be strictly configured.

4) Incident recovery workflow automation
- Probability: Low-Medium
- Impact: High
- Difficulty: Medium
- Why: recovery is defined, but still partially manual.

---

## F) Safe micro-live test envelope

Use this as maximum envelope until blockers above are closed:
- Capital size: <= 100 EUR total
- Number of pairs: 1
- Concurrent open positions: <= 1
- Session duration: <= 2 hours per run
- Max sessions/day: 1

Rollback conditions (immediate fallback to paper):
- Any startup attestation bypass attempt or failure
- Any global kill-switch trip
- Any critical reconciliation divergence
- Any invalid nonce storm

Stop conditions (hard stop):
- Drawdown reaches configured max
- Repeated API failures threshold reached
- Balance/clock/reconciliation checks fail

