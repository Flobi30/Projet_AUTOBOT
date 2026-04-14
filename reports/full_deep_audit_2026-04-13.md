# Pre-Production Remediation Blueprint — AUTOBOT (Real-Money Deployment)

Date: 2026-04-13  
Scope: Pre-production hardening for real-money readiness on Kraken.

---

## A) Architecture upgrades

### A1. Persisted Order Lifecycle Service (mandatory)
Introduce a single authoritative **Order Lifecycle Service** (OLS) used by sync + async paths.

**Responsibilities**
- Generate and persist `client_order_id` before first API call.
- Own all order-state transitions.
- Attach retry metadata and last error cause.
- Reconcile state with exchange after restart.
- Expose read model for dashboard/monitoring.

**Target state machine**
`NEW -> SENT -> ACK -> PARTIAL -> FILLED | CANCELED | REJECTED | EXPIRED`

**Architecture placement**
- `SignalHandler*` emits intent only.
- OLS executes and persists transitions.
- Risk module consumes OLS events (not ad-hoc callbacks).
- Reconciliation module repairs OLS state from exchange truth.

---

### A2. Strict Exchange Reconciliation Layer (SERL)
Implement a periodic + event-driven reconciliation service with deterministic rules:

1. **Balances:** local cash/asset balances vs Kraken balances.
2. **Positions:** local open positions vs exchange effective exposure.
3. **Open Orders:** local pending/open orders vs exchange open orders.
4. **Execution economics:** fills, fees, realized/unrealized PnL vs local ledger.

SERL should publish divergences (`INFO/WARN/CRITICAL`) and can trigger kill switch.

---

### A3. Immutable Audit Event Store
Add append-only audit table(s) for full traceability of the trade lifecycle:
- decision -> signal -> validation -> order transitions -> fills -> close -> PnL attribution.
- No UPDATE/DELETE allowed on events (append-only with hash chain).

---

### A4. Startup Attestation Gate (blocker)
System must **fail closed** at startup if safety attestation is incomplete.

---

### A5. Production control-plane hardening
- Default all risky feature flags to OFF.
- Require explicit signed deployment profile for `LIVE` mode.
- Introduce progressive rollout classes: `PAPER -> LIVE_SMALL -> LIVE_SCALED`.

---

## B) Concrete schemas / state models

### B1. Persisted order-state machine schema

#### `orders`
| Field | Type | Notes |
|---|---|---|
| client_order_id | TEXT PK | UUIDv7 / ULID, generated locally before send |
| exchange_order_id | TEXT NULL | Kraken txid once ACKed |
| decision_id | TEXT NOT NULL | decision lineage |
| signal_id | TEXT NOT NULL | signal lineage |
| instance_id | TEXT NOT NULL | strategy instance |
| symbol | TEXT NOT NULL | normalized pair |
| side | TEXT NOT NULL | buy/sell |
| order_type | TEXT NOT NULL | market/limit/stop |
| tif | TEXT NULL | time-in-force |
| requested_qty | REAL NOT NULL | requested base qty |
| filled_qty | REAL NOT NULL DEFAULT 0 | cumulative fill qty |
| avg_fill_price | REAL NULL | VWAP of fills |
| status | TEXT NOT NULL | NEW/SENT/ACK/PARTIAL/FILLED/CANCELED/REJECTED/EXPIRED |
| retries | INTEGER NOT NULL DEFAULT 0 | API retry attempts |
| last_error_code | TEXT NULL | normalized error code |
| last_error_message | TEXT NULL | sanitized |
| created_at | TEXT NOT NULL | UTC ISO8601 |
| sent_at | TEXT NULL | first send timestamp |
| ack_at | TEXT NULL | exchange accepted |
| terminal_at | TEXT NULL | terminal status timestamp |
| version | INTEGER NOT NULL DEFAULT 1 | optimistic locking |

#### `order_state_transitions` (append-only)
| Field | Type | Notes |
|---|---|---|
| id | INTEGER PK |
| client_order_id | TEXT NOT NULL |
| from_status | TEXT NULL |
| to_status | TEXT NOT NULL |
| reason | TEXT NOT NULL | e.g. API_ACK, FILL_UPDATE, RECON_REPAIR |
| source | TEXT NOT NULL | runtime/reconciler/replay |
| exchange_payload_hash | TEXT NULL | hash of normalized response |
| occurred_at | TEXT NOT NULL |

#### Crash recovery behavior
1. On startup, load orders in non-terminal states: `NEW/SENT/ACK/PARTIAL`.
2. Query exchange open + recent closed orders.
3. Re-map by `exchange_order_id`, fallback to deterministic matching (`symbol,side,qty,time_window`).
4. Replay missing transitions into `order_state_transitions`.
5. If mapping ambiguous => `CRITICAL divergence` and block trading.

#### Replay/reconciliation behavior after restart
- Re-run idempotent reconciliation until no critical divergence.
- Never emit new order for an unresolved prior `SENT/ACK/PARTIAL` without explicit policy.
- Promote unresolved stale orders to `RECON_PENDING` operational state (outside exchange status) to block duplicate submissions.

---

### B2. Strict exchange reconciliation model

#### `reconciliation_snapshots`
| Field | Type | Notes |
|---|---|---|
| id | INTEGER PK |
| snapshot_time | TEXT NOT NULL |
| exchange_time | TEXT NULL |
| local_cash_balance | REAL NOT NULL |
| exchange_cash_balance | REAL NOT NULL |
| local_asset_value | REAL NOT NULL |
| exchange_asset_value | REAL NOT NULL |
| local_unrealized_pnl | REAL NOT NULL |
| exchange_unrealized_pnl | REAL NOT NULL |
| local_realized_pnl | REAL NOT NULL |
| exchange_realized_pnl | REAL NOT NULL |
| drift_score | REAL NOT NULL | weighted divergence score |
| severity | TEXT NOT NULL | INFO/WARN/CRITICAL |

#### Divergence detection rules (examples)
- **Balance drift critical**: `abs(local_total - exchange_total) > max(10 EUR, 0.5% NAV)`.
- **Position drift critical**: unmatched open position OR qty mismatch > instrument min step.
- **Open-order drift critical**: local ACK/PARTIAL not found on exchange AND not terminal in last reconciliation window.
- **PnL drift warning/critical**: realized PnL mismatch > fees_tolerance + slippage_tolerance.
- **Freshness critical**: balance snapshot older than `N` seconds in live mode.

#### Kill-switch triggers from reconciliation
- Any CRITICAL divergence persisting for 2 consecutive cycles.
- Drift score above critical threshold.
- Unknown fills received for unknown order lineage.

---

### B3. Immutable audit trail schema (trade lifecycle)

#### `audit_events` (append-only, immutable)
| Field | Type | Notes |
|---|---|---|
| event_id | TEXT PK | UUIDv7 |
| event_type | TEXT NOT NULL | DECISION_CREATED, SIGNAL_EMITTED, ORDER_SENT, FILL_RECEIVED, POSITION_CLOSED... |
| decision_id | TEXT NOT NULL |
| signal_id | TEXT NULL |
| client_order_id | TEXT NULL |
| exchange_order_id | TEXT NULL |
| instance_id | TEXT NOT NULL |
| config_hash | TEXT NOT NULL | hash of full runtime config |
| risk_snapshot | TEXT NOT NULL | JSON normalized |
| balance_before | TEXT NULL | JSON by asset |
| balance_after | TEXT NULL | JSON by asset |
| fees | REAL NULL |
| slippage_bps | REAL NULL |
| order_from_status | TEXT NULL |
| order_to_status | TEXT NULL |
| exchange_raw_normalized | TEXT NULL | canonical JSON payload |
| created_at | TEXT NOT NULL |
| prev_event_hash | TEXT NULL | chain pointer |
| event_hash | TEXT NOT NULL | tamper evidence |

**Rules**
- No updates, only append.
- Event hash includes canonical serialization + `prev_event_hash`.
- Any chain break => compliance incident + kill switch in live mode.

---

### B4. Updated issue re-ranking by deployment stage

#### Must fix **before PAPER trading**
1. Remove leaked SSH key + rotate credentials everywhere.
2. Fix async validator contract mismatch.
3. Fix WAL stuck-key behavior (`try/finally` cleanup).
4. Remove auth token leakage in logs.
5. Enforce startup attestation scaffold (at least non-live critical checks).

#### Must fix **before LIVE (small capital)**
1. Implement persisted order-state machine + transition log.
2. Implement strict reconciliation for balances/orders/positions.
3. Add concrete kill switch automation.
4. Ensure PF/risk controls use real persisted trades (not empty in-memory structures).
5. Remove development auth bypass from deployable profiles.

#### Must fix **before scaling capital**
1. Immutable audit trail with hash chain.
2. Chaos test suite passing with SLOs.
3. Full divergence auto-repair + incident runbooks.
4. Feature flag governance + signed config releases.
5. Continuous reconciliation dashboards and alerting.

---

## C) Kill switch rules

### C1. Core financial limits
- **Max drawdown (portfolio):** trigger at `>= 12%` intraday OR `>= 15%` rolling.
- **Per-instance drawdown:** trigger at `>= 8%`.
- **Loss velocity:** trigger if loss > `X` EUR in `Y` minutes (configurable).

### C2. Execution and API health
- **Repeated API failures:** `>= 10` consecutive private API errors.
- **Invalid nonce storm:** `>= 3` nonce errors in 60s.
- **Rate-limit lockout:** sustained 429/backoff saturation for > 120s.

### C3. Data integrity and freshness
- **Stale balances:** no confirmed fresh balance for > 30s in live mode.
- **Reconciliation mismatch:** CRITICAL divergence for 2 cycles.
- **Missing heartbeat:** strategy/executor/WS heartbeat missing > 15s.
- **Partial fill stuck:** PARTIAL status older than configured SLA (e.g. 180s) with no update.

### C4. Kill switch behavior
When triggered:
1. Block new order submissions immediately.
2. Cancel non-protective open orders.
3. Keep/restore protective stops.
4. Snapshot state + emit critical incident event.
5. Require explicit human ack + attestation before resume.

---

## D) Chaos test matrix

| Test ID | Scenario | Injection | Expected behavior | Pass criteria |
|---|---|---|---|---|
| CH-01 | Duplicate signals | Send same BUY signal rapidly | Single logical order lineage | No duplicate exchange orders |
| CH-02 | Duplicate order submission | Retry same `client_order_id` | Idempotent ACK/fill mapping | One terminal order only |
| CH-03 | API timeout | Delay private API responses | Retries with bounded backoff | No uncontrolled duplicate send |
| CH-04 | 429 rate limit | Force burst > limit | Backoff + queueing | No ban, no dropped critical orders |
| CH-05 | WS disconnect | Cut market stream | Degrade to safe mode | No unsafe blind trading |
| CH-06 | Restart during open order | Crash after SENT/ACK | Replay + reconcile | Correct final terminal state |
| CH-07 | Partial fill then retry | Simulate 30% fill + timeout | Transition to PARTIAL then continue policy | No overfill/duplicate fills |
| CH-08 | Stale balance response | Freeze balance endpoint | Kill switch on staleness | Trading halted within SLA |
| CH-09 | Cancel ACK then late fill | Exchange race condition | Reconcile late fill correctly | Position/PnL consistency preserved |

**Execution policy**
- Mandatory before any live exposure.
- Run nightly in CI against simulator; weekly against paper exchange sandbox.
- Define SLOs per scenario (max recovery time, max drift, max duplicate count = 0).

---

## E) Updated GO / NO-GO decision

### Current decision: **NO-GO (live capital)**
Reason: critical credential, validation, idempotency, and traceability controls are not yet at financial-grade safety.

### Conditional path to GO
- **GO for Paper:** only after “before PAPER” list is fully complete.
- **GO for Live Small Capital:** only after persisted OSM + SERL + kill switch rules are implemented and chaos matrix green.
- **GO for Scaled Capital:** only after immutable audit trail, full chaos hardening, and operational governance controls are in place.

