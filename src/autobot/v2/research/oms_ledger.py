"""Hermetic, append-only OMS/ledger/TCA model for AUTOBOT research and shadow.

This is not the production order router.  It uses the stable contracts to make
timeouts, partial fills, duplicate fills, restart reconstruction and
reconciliation testable without submitting, cancelling or querying an exchange.
Only ``shadow`` intents are accepted.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sqlite3
from typing import Any, Mapping, Sequence

from autobot.v2.contracts import FillEvent, MarketIdentity, OrderEvent, OrderIntent, PositionSnapshot, contract_to_dict


DEFAULT_OMS_LEDGER_PATH = Path("data/research/oms_shadow_ledger.sqlite3")
TERMINAL_ORDER_STATES = frozenset({"FILLED", "CANCELLED", "REJECTED"})
ALLOWED_ORDER_TRANSITIONS = {
    None: frozenset({"CREATED"}),
    "CREATED": frozenset({"SUBMITTED", "CANCELLED", "REJECTED"}),
    "SUBMITTED": frozenset({"ACKNOWLEDGED", "CANCELLED", "REJECTED", "UNKNOWN"}),
    "ACKNOWLEDGED": frozenset({"PARTIALLY_FILLED", "FILLED", "CANCELLED", "REJECTED", "UNKNOWN"}),
    "PARTIALLY_FILLED": frozenset({"PARTIALLY_FILLED", "FILLED", "CANCELLED", "UNKNOWN"}),
    "UNKNOWN": frozenset({"ACKNOWLEDGED", "PARTIALLY_FILLED", "FILLED", "CANCELLED", "REJECTED"}),
}


class OMSLedgerError(ValueError):
    """Raised for invalid order lifecycle, ledger or reconciliation evidence."""


@dataclass(frozen=True)
class TransactionCostAnalysis:
    client_order_id: str
    side: str
    signal_price: float
    decision_price: float
    arrival_price: float
    fill_price: float
    fee_eur: float
    spread_cost_eur: float
    slippage_eur: float
    latency_cost_eur: float
    funding_eur: float = 0.0
    execution_mode: str = "shadow"
    research_only: bool = True
    paper_capital_allowed: bool = False
    live_allowed: bool = False

    def __post_init__(self) -> None:
        if not self.client_order_id.strip():
            raise OMSLedgerError("client_order_id is required")
        side = self.side.lower()
        if side not in {"buy", "sell"}:
            raise OMSLedgerError("TCA side must be buy or sell")
        if self.execution_mode != "shadow" or not self.research_only or self.paper_capital_allowed or self.live_allowed:
            raise OMSLedgerError("TCA record must remain research-only shadow")
        for field_name in ("signal_price", "decision_price", "arrival_price", "fill_price"):
            value = float(getattr(self, field_name))
            if not math.isfinite(value) or value <= 0.0:
                raise OMSLedgerError(f"{field_name} must be positive and finite")
        for field_name in ("fee_eur", "spread_cost_eur", "slippage_eur", "latency_cost_eur", "funding_eur"):
            value = float(getattr(self, field_name))
            if not math.isfinite(value):
                raise OMSLedgerError(f"{field_name} must be finite")
        for field_name in ("fee_eur", "spread_cost_eur", "slippage_eur", "latency_cost_eur"):
            if float(getattr(self, field_name)) < 0.0:
                raise OMSLedgerError(f"{field_name} cannot be negative")
        object.__setattr__(self, "side", side)

    @property
    def implementation_shortfall_bps(self) -> float:
        direction = 1.0 if self.side == "buy" else -1.0
        return direction * ((self.fill_price - self.signal_price) / self.signal_price) * 10_000.0

    @property
    def total_cost_eur(self) -> float:
        return self.fee_eur + self.spread_cost_eur + self.slippage_eur + self.latency_cost_eur + self.funding_eur

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["implementation_shortfall_bps"] = self.implementation_shortfall_bps
        payload["total_cost_eur"] = self.total_cost_eur
        return payload


@dataclass(frozen=True)
class LedgerAccountingSnapshot:
    """State reconstructed solely from append-only shadow ledger events.

    Cash values are net flows until the caller supplies a separately observed
    baseline for reconciliation.  This prevents the ledger from inventing an
    exchange balance or treating a starting balance as execution evidence.
    """

    positions: tuple[PositionSnapshot, ...]
    cash_flow_by_quote_asset: Mapping[str, float]
    realized_pnl_by_quote_asset: Mapping[str, float]
    research_only: bool = True
    paper_capital_allowed: bool = False
    live_allowed: bool = False


@dataclass(frozen=True)
class ReconciliationReport:
    status: str
    reasons: tuple[str, ...]
    local_positions: Mapping[str, float]
    observed_positions: Mapping[str, float]
    local_open_orders: tuple[str, ...]
    observed_open_orders: tuple[str, ...]
    trading_halted: bool
    expected_cash_balances: Mapping[str, float] = field(default_factory=dict)
    observed_cash_balances: Mapping[str, float] = field(default_factory=dict)
    realized_pnl_by_quote_asset: Mapping[str, float] = field(default_factory=dict)
    research_only: bool = True
    paper_capital_allowed: bool = False
    live_allowed: bool = False


class ShadowOMSLedger:
    """Persist contract events and reconstruct shadow state after a restart."""

    def __init__(self, path: str | Path = DEFAULT_OMS_LEDGER_PATH) -> None:
        self.path = Path(path)

    def register_intent(self, intent: OrderIntent) -> bool:
        if intent.execution_mode != "shadow":
            raise OMSLedgerError("OMS ledger accepts shadow intents only")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            self._initialize(connection)
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO oms_intents
                    (client_order_id, decision_id, strategy_id, intent_json, created_at,
                     paper_capital_allowed, live_allowed)
                VALUES (?, ?, ?, ?, ?, 0, 0)
                """,
                (
                    intent.client_order_id,
                    intent.decision_id,
                    intent.strategy_id,
                    _json(contract_to_dict(intent)),
                    intent.created_at.isoformat(),
                ),
            )
            return cursor.rowcount == 1

    def record_order_event(self, event: OrderEvent) -> bool:
        with self._connect() as connection:
            self._initialize(connection)
            return self._record_order_event(connection, event)

    def record_fill(self, fill: FillEvent, *, costs: Mapping[str, float]) -> bool:
        _validate_costs(costs)
        if not math.isclose(float(costs["fee_eur"]), float(fill.fees), rel_tol=0.0, abs_tol=1e-9):
            raise OMSLedgerError("fill fee evidence does not match FillEvent fee")
        with self._connect() as connection:
            self._initialize(connection)
            duplicate = connection.execute("SELECT 1 FROM oms_fill_events WHERE fill_id = ?", (fill.fill_id,)).fetchone()
            if duplicate:
                return False
            intent = self._load_intent(connection, fill.client_order_id)
            current = self._latest_event_type(connection, fill.client_order_id)
            if current not in {"ACKNOWLEDGED", "PARTIALLY_FILLED", "UNKNOWN"}:
                raise OMSLedgerError("fill requires acknowledged, partial or recovered-unknown order state")
            fill_id = str(fill.fill_id)
            connection.execute(
                """
                INSERT OR IGNORE INTO oms_fill_events
                    (fill_id, client_order_id, fill_json, costs_json, occurred_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (fill_id, fill.client_order_id, _json(contract_to_dict(fill)), _json(dict(costs)), fill.occurred_at.isoformat()),
            )
            requested_notional = float(intent["target_notional"])
            total_notional = self._filled_notional(connection, fill.client_order_id)
            next_state = "FILLED" if total_notional + 1e-9 >= requested_notional else "PARTIALLY_FILLED"
            self._record_order_event(
                connection,
                OrderEvent(
                    client_order_id=fill.client_order_id,
                    event_type=next_state,
                    occurred_at=fill.occurred_at,
                    reason="shadow_fill_recorded",
                )
            )
            return True

    def record_tca(self, record: TransactionCostAnalysis) -> bool:
        with self._connect() as connection:
            self._initialize(connection)
            self._load_intent(connection, record.client_order_id)
            payload = record.to_dict()
            record_id = _event_id("tca", payload)
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO oms_tca_records
                    (record_id, client_order_id, record_json, recorded_at,
                     paper_capital_allowed, live_allowed)
                VALUES (?, ?, ?, ?, 0, 0)
                """,
                (record_id, record.client_order_id, _json(payload), _utc_now().isoformat()),
            )
            return cursor.rowcount == 1

    def reconstruct_positions(self) -> tuple[PositionSnapshot, ...]:
        return self.reconstruct_accounting().positions

    def reconstruct_accounting(self) -> LedgerAccountingSnapshot:
        """Rebuild positions, net cash flows and realized PnL from fills only.

        The method deliberately has no starting-capital parameter.  Starting
        balances belong to the independent reconciliation observation, not to
        the append-only event ledger.
        """

        if not self.path.exists():
            return LedgerAccountingSnapshot((), {}, {})
        with self._connect() as connection:
            self._initialize(connection)
            rows = connection.execute(
                """
                SELECT intent.intent_json, fill.fill_json, fill.costs_json
                FROM oms_fill_events AS fill
                JOIN oms_intents AS intent ON intent.client_order_id = fill.client_order_id
                ORDER BY fill.occurred_at, fill.fill_id
                """
            ).fetchall()
        positions: dict[str, dict[str, Any]] = {}
        cash_flows: dict[str, float] = {}
        realized_pnl: dict[str, float] = {}
        for intent_json, fill_json, costs_json in rows:
            intent = json.loads(str(intent_json))
            fill = json.loads(str(fill_json))
            costs = json.loads(str(costs_json))
            market = intent["market"]
            symbol = str(market["symbol"]).upper()
            quote_asset = str(market["quote_asset"]).upper()
            quantity = float(fill["quantity"])
            price = float(fill["average_price"])
            gross_notional = quantity * price
            total_cost = _total_cost(costs)
            side = str(intent["side"]).lower()
            position = positions.setdefault(
                symbol,
                {"quantity": 0.0, "cost": 0.0, "market": market, "observed_at": fill["occurred_at"]},
            )
            if side == "buy":
                position["quantity"] += quantity
                position["cost"] += gross_notional + total_cost
                cash_flows[quote_asset] = cash_flows.get(quote_asset, 0.0) - gross_notional - total_cost
            else:
                if quantity > position["quantity"] + 1e-9:
                    raise OMSLedgerError(f"sell fill exceeds reconstructed position for {symbol}")
                average = position["cost"] / position["quantity"] if position["quantity"] > 0.0 else 0.0
                realized = gross_notional - total_cost - (quantity * average)
                position["quantity"] -= quantity
                position["cost"] -= quantity * average
                cash_flows[quote_asset] = cash_flows.get(quote_asset, 0.0) + gross_notional - total_cost
                realized_pnl[quote_asset] = realized_pnl.get(quote_asset, 0.0) + realized
            position["observed_at"] = fill["occurred_at"]
        snapshots: list[PositionSnapshot] = []
        for symbol, state in sorted(positions.items()):
            if state["quantity"] <= 1e-12:
                continue
            market = state["market"]
            average = state["cost"] / state["quantity"]
            snapshots.append(
                PositionSnapshot(
                    position_id=f"shadow_position_{symbol}",
                    market=MarketIdentity(**market),
                    quantity=state["quantity"],
                    average_entry_price=average,
                    observed_at=datetime.fromisoformat(str(state["observed_at"])),
                    source="research_shadow_oms_ledger",
                )
            )
        return LedgerAccountingSnapshot(
            positions=tuple(snapshots),
            cash_flow_by_quote_asset={key: round(value, 12) for key, value in sorted(cash_flows.items())},
            realized_pnl_by_quote_asset={key: round(value, 12) for key, value in sorted(realized_pnl.items())},
        )

    def reconcile(
        self,
        *,
        observed_positions: Mapping[str, float],
        observed_open_orders: Sequence[str],
        baseline_cash_by_quote_asset: Mapping[str, float] | None = None,
        observed_cash_by_quote_asset: Mapping[str, float] | None = None,
        tolerance: float = 1e-9,
    ) -> ReconciliationReport:
        if (baseline_cash_by_quote_asset is None) != (observed_cash_by_quote_asset is None):
            raise OMSLedgerError("cash reconciliation requires both baseline and observed balances")
        accounting = self.reconstruct_accounting()
        local_positions = {snapshot.market.symbol: float(snapshot.quantity) for snapshot in accounting.positions}
        observed = {str(symbol).upper(): float(quantity) for symbol, quantity in observed_positions.items()}
        local_open = tuple(sorted(self._open_order_ids()))
        remote_open = tuple(sorted(str(value) for value in observed_open_orders))
        reasons: list[str] = []
        for symbol in sorted(set(local_positions) | set(observed)):
            if abs(local_positions.get(symbol, 0.0) - observed.get(symbol, 0.0)) > tolerance:
                reasons.append(f"position_mismatch:{symbol}")
        if local_open != remote_open:
            reasons.append("open_order_mismatch")
        expected_cash: dict[str, float] = {}
        observed_cash: dict[str, float] = {}
        if baseline_cash_by_quote_asset is not None and observed_cash_by_quote_asset is not None:
            baseline_cash = _validated_cash_balances(baseline_cash_by_quote_asset, "baseline")
            observed_cash = _validated_cash_balances(observed_cash_by_quote_asset, "observed")
            for asset in sorted(set(baseline_cash) | set(accounting.cash_flow_by_quote_asset) | set(observed_cash)):
                expected_cash[asset] = baseline_cash.get(asset, 0.0) + accounting.cash_flow_by_quote_asset.get(asset, 0.0)
                if abs(expected_cash[asset] - observed_cash.get(asset, 0.0)) > tolerance:
                    reasons.append(f"cash_balance_mismatch:{asset}")
        return ReconciliationReport(
            status="RECONCILED" if not reasons else "RECONCILIATION_REQUIRED",
            reasons=tuple(reasons),
            local_positions=local_positions,
            observed_positions=observed,
            local_open_orders=local_open,
            observed_open_orders=remote_open,
            trading_halted=bool(reasons),
            expected_cash_balances=expected_cash,
            observed_cash_balances=observed_cash,
            realized_pnl_by_quote_asset=accounting.realized_pnl_by_quote_asset,
        )

    def _open_order_ids(self) -> set[str]:
        if not self.path.exists():
            return set()
        with self._connect() as connection:
            self._initialize(connection)
            rows = connection.execute(
                """
                SELECT event.client_order_id, event.event_type
                FROM oms_order_events AS event
                WHERE event.event_id = (
                    SELECT latest.event_id
                    FROM oms_order_events AS latest
                    WHERE latest.client_order_id = event.client_order_id
                    ORDER BY latest.occurred_at DESC, latest.event_id DESC
                    LIMIT 1
                )
                """
            ).fetchall()
        return {str(row[0]) for row in rows if str(row[1]) not in TERMINAL_ORDER_STATES}

    @staticmethod
    def _load_intent(connection: sqlite3.Connection, client_order_id: str) -> dict[str, Any]:
        row = connection.execute(
            "SELECT intent_json FROM oms_intents WHERE client_order_id = ?", (client_order_id,)
        ).fetchone()
        if not row:
            raise OMSLedgerError("unknown client_order_id")
        return json.loads(str(row[0]))

    @staticmethod
    def _latest_event_type(connection: sqlite3.Connection, client_order_id: str) -> str | None:
        row = connection.execute(
            "SELECT event_type FROM oms_order_events WHERE client_order_id = ? ORDER BY occurred_at DESC, event_id DESC LIMIT 1",
            (client_order_id,),
        ).fetchone()
        return str(row[0]) if row else None

    @staticmethod
    def _record_order_event(connection: sqlite3.Connection, event: OrderEvent) -> bool:
        intent = connection.execute(
            "SELECT 1 FROM oms_intents WHERE client_order_id = ?", (event.client_order_id,)
        ).fetchone()
        if not intent:
            raise OMSLedgerError("order event requires a registered shadow intent")
        event_id = _event_id("order", contract_to_dict(event))
        if connection.execute("SELECT 1 FROM oms_order_events WHERE event_id = ?", (event_id,)).fetchone():
            return False
        prior = ShadowOMSLedger._latest_event_type(connection, event.client_order_id)
        if prior in TERMINAL_ORDER_STATES:
            raise OMSLedgerError("terminal order cannot accept additional events")
        if event.event_type not in ALLOWED_ORDER_TRANSITIONS.get(prior, frozenset()):
            raise OMSLedgerError(f"invalid order state transition: {prior} -> {event.event_type}")
        cursor = connection.execute(
            """
            INSERT INTO oms_order_events
                (event_id, client_order_id, event_type, event_json, occurred_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (event_id, event.client_order_id, event.event_type, _json(contract_to_dict(event)), event.occurred_at.isoformat()),
        )
        return cursor.rowcount == 1

    @staticmethod
    def _filled_notional(connection: sqlite3.Connection, client_order_id: str) -> float:
        rows = connection.execute(
            "SELECT fill_json FROM oms_fill_events WHERE client_order_id = ?", (client_order_id,)
        ).fetchall()
        return sum(float(json.loads(str(row[0]))["quantity"]) * float(json.loads(str(row[0]))["average_price"]) for row in rows)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30.0)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    @staticmethod
    def _initialize(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS oms_intents (
                client_order_id TEXT PRIMARY KEY,
                decision_id TEXT NOT NULL,
                strategy_id TEXT NOT NULL,
                intent_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                paper_capital_allowed INTEGER NOT NULL CHECK (paper_capital_allowed = 0),
                live_allowed INTEGER NOT NULL CHECK (live_allowed = 0)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS oms_order_events (
                event_id TEXT PRIMARY KEY,
                client_order_id TEXT NOT NULL REFERENCES oms_intents(client_order_id),
                event_type TEXT NOT NULL,
                event_json TEXT NOT NULL,
                occurred_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS oms_fill_events (
                fill_id TEXT PRIMARY KEY,
                client_order_id TEXT NOT NULL REFERENCES oms_intents(client_order_id),
                fill_json TEXT NOT NULL,
                costs_json TEXT NOT NULL,
                occurred_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS oms_tca_records (
                record_id TEXT PRIMARY KEY,
                client_order_id TEXT NOT NULL REFERENCES oms_intents(client_order_id),
                record_json TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                paper_capital_allowed INTEGER NOT NULL CHECK (paper_capital_allowed = 0),
                live_allowed INTEGER NOT NULL CHECK (live_allowed = 0)
            )
            """
        )
        for table in ("oms_intents", "oms_order_events", "oms_fill_events", "oms_tca_records"):
            for operation in ("UPDATE", "DELETE"):
                connection.execute(
                    f"""
                    CREATE TRIGGER IF NOT EXISTS {table}_append_only_{operation.lower()}
                    BEFORE {operation} ON {table}
                    BEGIN
                        SELECT RAISE(ABORT, '{table} is append-only');
                    END
                    """
                )


def _validate_costs(costs: Mapping[str, float]) -> None:
    required = {"fee_eur", "spread_cost_eur", "slippage_eur", "latency_cost_eur"}
    missing = sorted(required - set(costs))
    if missing:
        raise OMSLedgerError(f"fill cost evidence missing: {','.join(missing)}")
    for field_name in required:
        value = float(costs[field_name])
        if not math.isfinite(value) or value < 0.0:
            raise OMSLedgerError(f"{field_name} must be finite and non-negative")
    if "funding_eur" in costs and not math.isfinite(float(costs["funding_eur"])):
        raise OMSLedgerError("funding_eur must be finite when supplied")


def _total_cost(costs: Mapping[str, float]) -> float:
    _validate_costs(costs)
    return sum(float(costs[field_name]) for field_name in ("fee_eur", "spread_cost_eur", "slippage_eur", "latency_cost_eur")) + float(costs.get("funding_eur", 0.0))


def _validated_cash_balances(values: Mapping[str, float], label: str) -> dict[str, float]:
    if not isinstance(values, Mapping):
        raise OMSLedgerError(f"{label} cash balances must be a mapping")
    normalised: dict[str, float] = {}
    for raw_asset, raw_value in values.items():
        asset = str(raw_asset).upper().strip()
        value = float(raw_value)
        if not asset or not math.isfinite(value):
            raise OMSLedgerError(f"{label} cash balances contain an invalid value")
        normalised[asset] = value
    return normalised


def _event_id(prefix: str, payload: Mapping[str, Any]) -> str:
    normalized = _json(payload)
    import hashlib

    return f"{prefix}_{hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:24]}"


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
