"""Sync closed shadow-lab trades into the post-P0 paper ledger.

This module is deliberately narrow: it creates attributed ``shadow_paper``
observations from already-closed shadow lab trades. It does not route orders,
does not allocate official paper capital, and never changes live state.
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from autobot.v2.shadow_cost_bridge import conservative_shadow_cost_defaults
from autobot.v2.strategy_runtime_policy import (
    EXECUTION_MODE_PAPER_CAPITAL,
    EXECUTION_MODE_SHADOW_PAPER,
    LEGACY_UNATTRIBUTED_STRATEGY_ID,
    shadow_paper_strategy_block_reason,
)
from autobot.v2.strategy_validation_registry import entry_by_strategy_id, load_registry


SYNCABLE_SHADOW_SOURCES: tuple[dict[str, str], ...] = (
    {
        "strategy_id": "trend_momentum",
        "source": "trend_shadow_lab",
        "default_path": "data/trend_shadow_lab.db",
        "table": "trend_shadow_trades",
        "default_regime": "trend",
    },
    {
        "strategy_id": "mean_reversion",
        "source": "mean_reversion_shadow_lab",
        "default_path": "data/mean_reversion_shadow_lab.db",
        "table": "mean_reversion_shadow_trades",
        "default_regime": "range",
    },
)

UNSYNCED_OBSERVATION_STRATEGIES: tuple[dict[str, str], ...] = (
    {
        "strategy_id": "high_conviction_swing",
        "source": "high_conviction_research",
        "reason": "no_closed_shadow_trade_source",
    },
    {
        "strategy_id": "opportunity_scoring",
        "source": "opportunity_scoring",
        "reason": "scoring_layer_no_direct_trade_source",
    },
)


@dataclass(frozen=True)
class ShadowPaperObservationSyncConfig:
    state_db_path: Path
    registry_path: Path = Path("docs/research/strategy_hypotheses.json")
    trend_shadow_db_path: Path = Path("data/trend_shadow_lab.db")
    mean_reversion_shadow_db_path: Path = Path("data/mean_reversion_shadow_lab.db")
    output_dir: Path = Path("reports/paper/shadow_observations")
    run_id: str | None = None
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    write_report: bool = True

    @property
    def resolved_run_id(self) -> str:
        if self.run_id:
            return self.run_id
        return f"shadow_paper_observations_{self.generated_at.strftime('%Y%m%d_%H%M%S')}"

    def source_path_for(self, source: Mapping[str, str]) -> Path:
        if source["strategy_id"] == "trend_momentum":
            return self.trend_shadow_db_path
        if source["strategy_id"] == "mean_reversion":
            return self.mean_reversion_shadow_db_path
        return Path(source["default_path"])


@dataclass(frozen=True)
class ShadowSyncSourceResult:
    strategy_id: str
    source: str
    source_path: str | None
    can_write_shadow: bool
    source_trade_count: int = 0
    inserted_trade_count: int = 0
    duplicate_trade_count: int = 0
    skipped_trade_count: int = 0
    latest_closed_at: str | None = None
    reason_counts: dict[str, int] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ShadowAccumulationBucket:
    strategy_id: str
    execution_mode: str
    total_trades: int
    trades_24h: int
    trades_7d: int
    net_pnl_eur: float
    gross_pnl_eur: float
    fees_eur: float
    slippage_eur: float
    profit_factor_net: float | None
    data_status: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ShadowPaperObservationSyncReport:
    run_id: str
    generated_at: str
    state_db_path: str
    registry_path: str
    execution_mode: str
    source_results: tuple[ShadowSyncSourceResult, ...]
    accumulation: tuple[ShadowAccumulationBucket, ...]
    safety_notes: tuple[str, ...]
    json_report_path: str | None = None
    markdown_report_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "state_db_path": self.state_db_path,
            "registry_path": self.registry_path,
            "execution_mode": self.execution_mode,
            "source_results": [item.to_dict() for item in self.source_results],
            "accumulation": [item.to_dict() for item in self.accumulation],
            "safety_notes": list(self.safety_notes),
            "json_report_path": self.json_report_path,
            "markdown_report_path": self.markdown_report_path,
        }


def sync_shadow_paper_observations(
    config: ShadowPaperObservationSyncConfig,
    *,
    write_report: bool | None = None,
) -> ShadowPaperObservationSyncReport:
    """Copy eligible closed shadow trades into the attributed paper ledger."""

    should_write = config.write_report if write_report is None else write_report
    registry_payload = load_registry(config.registry_path)
    generated_at = config.generated_at.isoformat()

    state_conn = sqlite3.connect(config.state_db_path)
    state_conn.row_factory = sqlite3.Row
    try:
        _ensure_trade_ledger_schema(state_conn)
        source_results: list[ShadowSyncSourceResult] = []
        for source in SYNCABLE_SHADOW_SOURCES:
            result = _sync_source(config, registry_payload, state_conn, source, generated_at)
            source_results.append(result)
        for source in UNSYNCED_OBSERVATION_STRATEGIES:
            source_results.append(_unsynced_source_result(registry_payload, source))
        state_conn.commit()
        accumulation = _build_accumulation(state_conn, now=config.generated_at)
    finally:
        state_conn.close()

    report = ShadowPaperObservationSyncReport(
        run_id=config.resolved_run_id,
        generated_at=generated_at,
        state_db_path=str(config.state_db_path),
        registry_path=str(config.registry_path),
        execution_mode=EXECUTION_MODE_SHADOW_PAPER,
        source_results=tuple(source_results),
        accumulation=tuple(accumulation),
        safety_notes=(
            "Research/paper observation sync only.",
            "No Kraken order is created.",
            "No live or official paper-capital permission is granted.",
            "shadow_paper observations are excluded from promotion evidence.",
            "Grid remains blocked by strategy_runtime_policy.",
        ),
    )
    if should_write:
        report = _write_report(report, config.output_dir)
    return report


def _sync_source(
    config: ShadowPaperObservationSyncConfig,
    registry_payload: Mapping[str, Any],
    state_conn: sqlite3.Connection,
    source: Mapping[str, str],
    generated_at: str,
) -> ShadowSyncSourceResult:
    strategy_id = source["strategy_id"]
    source_path = config.source_path_for(source)
    policy_reason = shadow_paper_strategy_block_reason(strategy_id)
    registry_entry = entry_by_strategy_id(registry_payload, strategy_id)
    warnings: list[str] = []
    if registry_entry is None:
        policy_reason = policy_reason or "strategy_not_in_registry"
    elif str(registry_entry.get("validation_status") or "") in {"rejected", "retired_from_execution"}:
        policy_reason = policy_reason or "strategy_terminal_status"

    if policy_reason is not None:
        return ShadowSyncSourceResult(
            strategy_id=strategy_id,
            source=source["source"],
            source_path=str(source_path),
            can_write_shadow=False,
            reason_counts={policy_reason: 1},
        )

    if not source_path.exists():
        return ShadowSyncSourceResult(
            strategy_id=strategy_id,
            source=source["source"],
            source_path=str(source_path),
            can_write_shadow=True,
            reason_counts={"source_db_missing": 1},
            warnings=("source_db_missing",),
        )

    source_conn = sqlite3.connect(source_path)
    source_conn.row_factory = sqlite3.Row
    try:
        if not _table_exists(source_conn, source["table"]):
            return ShadowSyncSourceResult(
                strategy_id=strategy_id,
                source=source["source"],
                source_path=str(source_path),
                can_write_shadow=True,
                reason_counts={"source_table_missing": 1},
                warnings=("source_table_missing",),
            )
        rows = source_conn.execute(
            f"""
            SELECT id, symbol, variant, position_id, entry_price, exit_price,
                   volume, notional, fees, realized_pnl, reason, opened_at,
                   closed_at, created_at
            FROM {source['table']}
            ORDER BY closed_at ASC, id ASC
            """
        ).fetchall()
    finally:
        source_conn.close()

    reason_counts: dict[str, int] = defaultdict(int)
    inserted = 0
    duplicates = 0
    skipped = 0
    latest_closed_at: str | None = None
    for row in rows:
        source_id = f"{source['source']}:{int(row['id'])}"
        if _ledger_trade_exists(state_conn, f"{source_id}:close") or _ledger_trade_exists(
            state_conn, f"{source_id}:open"
        ):
            duplicates += 1
            continue
        try:
            _insert_shadow_trade_pair(
                state_conn,
                row,
                strategy_id=strategy_id,
                source_name=source["source"],
                source_id=source_id,
                default_regime=source["default_regime"],
                generated_at=generated_at,
            )
            inserted += 1
            latest_closed_at = str(row["closed_at"] or latest_closed_at or "")
            reason_counts[str(row["reason"] or "unknown_exit")] += 1
        except (TypeError, ValueError, sqlite3.Error) as exc:
            skipped += 1
            reason = f"insert_error:{type(exc).__name__}"
            reason_counts[reason] += 1
            warnings.append(reason)

    return ShadowSyncSourceResult(
        strategy_id=strategy_id,
        source=source["source"],
        source_path=str(source_path),
        can_write_shadow=True,
        source_trade_count=len(rows),
        inserted_trade_count=inserted,
        duplicate_trade_count=duplicates,
        skipped_trade_count=skipped,
        latest_closed_at=latest_closed_at,
        reason_counts=dict(sorted(reason_counts.items())),
        warnings=tuple(dict.fromkeys(warnings)),
    )


def _unsynced_source_result(
    registry_payload: Mapping[str, Any],
    source: Mapping[str, str],
) -> ShadowSyncSourceResult:
    strategy_id = source["strategy_id"]
    policy_reason = shadow_paper_strategy_block_reason(strategy_id)
    if entry_by_strategy_id(registry_payload, strategy_id) is None:
        policy_reason = policy_reason or "strategy_not_in_registry"
    can_write = policy_reason is None
    reason = source["reason"] if can_write else policy_reason or "not_allowed"
    return ShadowSyncSourceResult(
        strategy_id=strategy_id,
        source=source["source"],
        source_path=None,
        can_write_shadow=can_write,
        reason_counts={reason: 1},
        warnings=(reason,),
    )


def _insert_shadow_trade_pair(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    *,
    strategy_id: str,
    source_name: str,
    source_id: str,
    default_regime: str,
    generated_at: str,
) -> None:
    entry_price = _positive_float(row["entry_price"], "entry_price")
    exit_price = _positive_float(row["exit_price"], "exit_price")
    volume = _positive_float(row["volume"], "volume")
    total_cost = max(_safe_float(row["fees"]), 0.0)
    net_pnl = _safe_float(row["realized_pnl"])
    gross_pnl = net_pnl + total_cost
    entry_notional = entry_price * volume
    exit_notional = exit_price * volume
    total_notional = max(entry_notional + exit_notional, 1e-12)
    fee_entry, fee_exit, slippage_bps = _split_legacy_costs(total_cost, entry_notional, exit_notional)
    position_id = f"shadow:{strategy_id}:{row['position_id']}:{int(row['id'])}"
    metadata = json.dumps(
        {
            "source_row_id": int(row["id"]),
            "source": source_name,
            "variant": str(row["variant"] or ""),
            "exit_reason": str(row["reason"] or "unknown_exit"),
            "execution_mode": EXECUTION_MODE_SHADOW_PAPER,
            "research_only": True,
        },
        separators=(",", ":"),
    )
    common = {
        "position_id": position_id,
        "instance_id": "shadow_paper",
        "symbol": str(row["symbol"] or "").strip(),
        "volume": volume,
        "strategy_id": strategy_id,
        "timeframe": "shadow_tick",
        "signal_source": f"{source_name}:{row['variant']}",
        "regime": default_regime,
        "execution_liquidity": "shadow_lab",
        "execution_mode": EXECUTION_MODE_SHADOW_PAPER,
    }
    if not common["symbol"]:
        raise ValueError("symbol missing")

    _insert_trade_ledger_row(
        conn,
        trade_id=f"{source_id}:open",
        side="buy",
        expected_price=entry_price,
        executed_price=entry_price,
        fees=fee_entry,
        slippage_bps=slippage_bps,
        realized_pnl=None,
        gross_pnl=None,
        net_pnl=None,
        is_opening_leg=1,
        is_closing_leg=0,
        created_at=str(row["opened_at"] or generated_at),
        signal_id=source_id,
        decision_id=metadata,
        **common,
    )
    _insert_trade_ledger_row(
        conn,
        trade_id=f"{source_id}:close",
        side="sell",
        expected_price=exit_price,
        executed_price=exit_price,
        fees=fee_exit,
        slippage_bps=slippage_bps,
        realized_pnl=net_pnl,
        gross_pnl=gross_pnl,
        net_pnl=net_pnl,
        is_opening_leg=0,
        is_closing_leg=1,
        created_at=str(row["closed_at"] or generated_at),
        signal_id=source_id,
        decision_id=metadata,
        **common,
    )


def _split_legacy_costs(
    total_cost: float,
    entry_notional: float,
    exit_notional: float,
) -> tuple[float, float, float]:
    if total_cost <= 0.0:
        return 0.0, 0.0, 0.0
    defaults = conservative_shadow_cost_defaults()
    total_bps = defaults.fee_bps_per_side + defaults.slippage_bps_per_side
    fee_share = defaults.fee_bps_per_side / total_bps if total_bps > 0.0 else 1.0
    fee_total = total_cost * fee_share
    slippage_total = total_cost - fee_total
    notional_total = max(entry_notional + exit_notional, 1e-12)
    entry_fee = fee_total * (entry_notional / notional_total)
    exit_fee = fee_total * (exit_notional / notional_total)
    slippage_bps = (slippage_total / notional_total) * 10_000.0
    return entry_fee, exit_fee, slippage_bps


def _insert_trade_ledger_row(conn: sqlite3.Connection, **values: Any) -> None:
    columns = [
        "trade_id",
        "position_id",
        "instance_id",
        "symbol",
        "side",
        "expected_price",
        "executed_price",
        "volume",
        "fees",
        "slippage_bps",
        "realized_pnl",
        "is_opening_leg",
        "is_closing_leg",
        "exchange_order_id",
        "decision_id",
        "signal_id",
        "strategy_id",
        "timeframe",
        "signal_source",
        "gross_pnl",
        "net_pnl",
        "regime",
        "execution_liquidity",
        "execution_mode",
        "created_at",
    ]
    payload = {name: values.get(name) for name in columns}
    payload["exchange_order_id"] = None
    conn.execute(
        f"INSERT INTO trade_ledger ({', '.join(columns)}) VALUES ({', '.join(['?'] * len(columns))})",
        tuple(payload[name] for name in columns),
    )


def _build_accumulation(
    conn: sqlite3.Connection,
    *,
    now: datetime,
) -> list[ShadowAccumulationBucket]:
    rows = conn.execute(
        """
        SELECT strategy_id, execution_mode, created_at, gross_pnl, net_pnl,
               fees, slippage_bps, executed_price, volume
        FROM trade_ledger
        WHERE is_closing_leg = 1
          AND strategy_id IS NOT NULL
          AND strategy_id != ?
          AND execution_mode IN (?, ?)
        """,
        (LEGACY_UNATTRIBUTED_STRATEGY_ID, EXECUTION_MODE_SHADOW_PAPER, EXECUTION_MODE_PAPER_CAPITAL),
    ).fetchall()
    grouped: dict[tuple[str, str], list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["strategy_id"]), str(row["execution_mode"]))].append(row)

    buckets: list[ShadowAccumulationBucket] = []
    cutoff_24h = now - timedelta(hours=24)
    cutoff_7d = now - timedelta(days=7)
    for (strategy_id, execution_mode), group in sorted(grouped.items()):
        net_values = [_safe_float(item["net_pnl"]) for item in group]
        gross_values = [_safe_float(item["gross_pnl"]) for item in group]
        fees = sum(_safe_float(item["fees"]) for item in group)
        slippage = sum(_slippage_eur(item) for item in group)
        positives = sum(value for value in net_values if value > 0.0)
        negatives = abs(sum(value for value in net_values if value < 0.0))
        pf = None if negatives <= 0.0 else positives / negatives
        total = len(group)
        buckets.append(
            ShadowAccumulationBucket(
                strategy_id=strategy_id,
                execution_mode=execution_mode,
                total_trades=total,
                trades_24h=sum(1 for item in group if _created_after(item, cutoff_24h)),
                trades_7d=sum(1 for item in group if _created_after(item, cutoff_7d)),
                net_pnl_eur=sum(net_values),
                gross_pnl_eur=sum(gross_values),
                fees_eur=fees,
                slippage_eur=slippage,
                profit_factor_net=pf,
                data_status="insufficient_data" if total < 30 else "observation_ready",
            )
        )
    return buckets


def _created_after(row: sqlite3.Row, cutoff: datetime) -> bool:
    value = row["created_at"]
    if not value:
        return False
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed >= cutoff


def _slippage_eur(row: sqlite3.Row) -> float:
    bps = _safe_float(row["slippage_bps"])
    executed_price = _safe_float(row["executed_price"])
    volume = _safe_float(row["volume"])
    return abs(executed_price * volume) * bps / 10_000.0


def _ensure_trade_ledger_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS trade_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id TEXT NOT NULL,
            position_id TEXT,
            instance_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            expected_price REAL,
            executed_price REAL NOT NULL,
            volume REAL NOT NULL,
            fees REAL DEFAULT 0,
            slippage_bps REAL,
            realized_pnl REAL,
            is_opening_leg INTEGER DEFAULT 0,
            is_closing_leg INTEGER DEFAULT 0,
            exchange_order_id TEXT,
            decision_id TEXT,
            signal_id TEXT,
            strategy_id TEXT,
            timeframe TEXT,
            signal_source TEXT,
            gross_pnl REAL,
            net_pnl REAL,
            regime TEXT,
            execution_liquidity TEXT,
            execution_mode TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    existing = {row[1] for row in conn.execute("PRAGMA table_info(trade_ledger)").fetchall()}
    missing_columns = {
        "strategy_id": "TEXT",
        "timeframe": "TEXT",
        "signal_source": "TEXT",
        "gross_pnl": "REAL",
        "net_pnl": "REAL",
        "regime": "TEXT",
        "execution_liquidity": "TEXT",
        "execution_mode": "TEXT",
    }
    for name, ddl_type in missing_columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE trade_ledger ADD COLUMN {name} {ddl_type}")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trade_ledger_strategy_id ON trade_ledger(strategy_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trade_ledger_execution_mode ON trade_ledger(execution_mode)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trade_ledger_trade_id ON trade_ledger(trade_id)")


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _ledger_trade_exists(conn: sqlite3.Connection, trade_id: str) -> bool:
    row = conn.execute("SELECT 1 FROM trade_ledger WHERE trade_id=? LIMIT 1", (trade_id,)).fetchone()
    return row is not None


def _positive_float(value: Any, name: str) -> float:
    parsed = _safe_float(value)
    if parsed <= 0.0:
        raise ValueError(f"{name} must be positive")
    return parsed


def _safe_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _write_report(
    report: ShadowPaperObservationSyncReport,
    output_dir: Path,
) -> ShadowPaperObservationSyncReport:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{report.run_id}.json"
    md_path = output_dir / f"{report.run_id}.md"
    json_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_markdown(report), encoding="utf-8")
    return ShadowPaperObservationSyncReport(
        **{
            **report.to_dict(),
            "source_results": report.source_results,
            "accumulation": report.accumulation,
            "safety_notes": report.safety_notes,
            "json_report_path": str(json_path),
            "markdown_report_path": str(md_path),
        }
    )


def _markdown(report: ShadowPaperObservationSyncReport) -> str:
    lines = [
        f"# Shadow Paper Observation Sync - {report.run_id}",
        "",
        f"- Generated: `{report.generated_at}`",
        f"- State DB: `{report.state_db_path}`",
        f"- Registry: `{report.registry_path}`",
        f"- Execution mode: `{report.execution_mode}`",
        "",
        "## Sources",
        "",
        "| Strategy | Source | Can write | Source trades | Inserted | Duplicates | Skipped | Reasons |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for item in report.source_results:
        lines.append(
            "| {strategy} | {source} | {can_write} | {source_trades} | {inserted} | {duplicates} | {skipped} | {reasons} |".format(
                strategy=item.strategy_id,
                source=item.source,
                can_write=str(item.can_write_shadow).lower(),
                source_trades=item.source_trade_count,
                inserted=item.inserted_trade_count,
                duplicates=item.duplicate_trade_count,
                skipped=item.skipped_trade_count,
                reasons=", ".join(f"{key}:{value}" for key, value in item.reason_counts.items()) or "none",
            )
        )
    lines.extend(
        [
            "",
            "## Accumulation",
            "",
            "| Strategy | Mode | Trades 24h | Trades 7d | Total | Net PnL | PF net | Status |",
            "|---|---|---:|---:|---:|---:|---:|---|",
        ]
    )
    for item in report.accumulation:
        pf = "n/a" if item.profit_factor_net is None else f"{item.profit_factor_net:.4f}"
        lines.append(
            f"| {item.strategy_id} | {item.execution_mode} | {item.trades_24h} | {item.trades_7d} | {item.total_trades} | {item.net_pnl_eur:.4f} | {pf} | {item.data_status} |"
        )
    lines.extend(
        [
            "",
            "## Safety",
            "",
        ]
    )
    lines.extend(f"- {note}" for note in report.safety_notes)
    return "\n".join(lines) + "\n"
