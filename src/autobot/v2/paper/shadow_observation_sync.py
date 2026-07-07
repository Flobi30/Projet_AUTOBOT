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
from hashlib import sha1
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from autobot.v2.pair_strategy_health import symbol_key
from autobot.v2.research.high_conviction_portfolio import (
    HighConvictionPortfolioConfig,
    PortfolioScenarioResult,
    build_high_conviction_portfolio_report,
    write_high_conviction_portfolio_report,
)
from autobot.v2.research.trade_journal import TradeRecord
from autobot.v2.paper.opportunity_score_v2 import (
    FORBIDDEN_SCORE_V2_CONTAINER_KEYS,
    FORBIDDEN_SCORE_V2_KEYS,
    build_opportunity_score_v2_metadata,
)
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
    high_conviction_data_paths: tuple[Path, ...] = ()
    output_dir: Path = Path("reports/paper/shadow_observations")
    high_conviction_output_dir: Path | None = None
    opportunity_match_window_hours: float = 6.0
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
    enriched_trade_count: int = 0
    duplicate_trade_count: int = 0
    skipped_trade_count: int = 0
    latest_closed_at: str | None = None
    reason_counts: dict[str, int] = field(default_factory=dict)
    inserted_score_coverage: dict[str, Any] = field(default_factory=dict)
    enriched_score_coverage: dict[str, Any] = field(default_factory=dict)
    score_origin_counts: dict[str, int] = field(default_factory=dict)
    score_coverage: dict[str, Any] = field(default_factory=dict)
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
    score_coverage: dict[str, Any]
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
            "score_coverage": dict(self.score_coverage),
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

    state_conn = sqlite3.connect(config.state_db_path, timeout=30.0)
    state_conn.row_factory = sqlite3.Row
    try:
        state_conn.execute("PRAGMA busy_timeout=30000")
        _ensure_trade_ledger_schema(state_conn)
        opportunity_lookup = _load_opportunity_score_lookup(state_conn)
        source_results: list[ShadowSyncSourceResult] = []
        for source in SYNCABLE_SHADOW_SOURCES:
            result = _sync_source(config, registry_payload, state_conn, source, generated_at, opportunity_lookup)
            source_results.append(result)
            state_conn.commit()
        source_results.append(
            _sync_high_conviction_source(config, registry_payload, state_conn, generated_at, opportunity_lookup)
        )
        state_conn.commit()
        for source in UNSYNCED_OBSERVATION_STRATEGIES:
            source_results.append(_unsynced_source_result(registry_payload, source))
        accumulation = _build_accumulation(state_conn, now=config.generated_at)
        score_coverage = _build_score_coverage(state_conn)
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
        score_coverage=score_coverage,
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
    opportunity_lookup: Mapping[str, tuple[dict[str, Any], ...]],
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
        rows = _select_shadow_source_rows(source_conn, source["table"])
    finally:
        source_conn.close()

    reason_counts: dict[str, int] = defaultdict(int)
    inserted = 0
    enriched = 0
    duplicates = 0
    skipped = 0
    inserted_score_counts = _empty_score_counts()
    enriched_score_counts = _empty_score_counts()
    score_origin_counts: dict[str, int] = defaultdict(int)
    latest_closed_at: str | None = None
    for row in rows:
        source_id = f"{source['source']}:{int(row['id'])}"
        opportunity_metadata = _shadow_row_opportunity_metadata(
            row,
            opportunity_lookup=opportunity_lookup,
            generated_at=generated_at,
            max_window_hours=config.opportunity_match_window_hours,
        )
        if _ledger_trade_exists(state_conn, f"{source_id}:close") or _ledger_trade_exists(
            state_conn, f"{source_id}:open"
        ):
            duplicates += 1
            if _enrich_existing_trade_metadata(
                state_conn,
                (f"{source_id}:open", f"{source_id}:close"),
                opportunity_metadata,
            ):
                enriched += 1
                _increment_score_counts(enriched_score_counts, opportunity_metadata)
                score_origin_counts[_opportunity_metadata_origin(opportunity_metadata)] += 1
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
                opportunity_metadata=opportunity_metadata,
            )
            inserted += 1
            _increment_score_counts(inserted_score_counts, opportunity_metadata)
            score_origin_counts[_opportunity_metadata_origin(opportunity_metadata)] += 1
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
        enriched_trade_count=enriched,
        duplicate_trade_count=duplicates,
        skipped_trade_count=skipped,
        latest_closed_at=latest_closed_at,
        reason_counts=dict(sorted(reason_counts.items())),
        inserted_score_coverage=_score_coverage_from_counts(inserted_score_counts),
        enriched_score_coverage=_score_coverage_from_counts(enriched_score_counts),
        score_origin_counts=dict(sorted(score_origin_counts.items())),
        score_coverage=_score_coverage_for_source(state_conn, strategy_id),
        warnings=tuple(dict.fromkeys(warnings)),
    )


def _sync_high_conviction_source(
    config: ShadowPaperObservationSyncConfig,
    registry_payload: Mapping[str, Any],
    state_conn: sqlite3.Connection,
    generated_at: str,
    opportunity_lookup: Mapping[str, tuple[dict[str, Any], ...]],
) -> ShadowSyncSourceResult:
    strategy_id = "high_conviction_swing"
    source_name = "high_conviction_portfolio_replay"
    policy_reason = shadow_paper_strategy_block_reason(strategy_id)
    registry_entry = entry_by_strategy_id(registry_payload, strategy_id)
    if registry_entry is None:
        policy_reason = policy_reason or "strategy_not_in_registry"
    elif str(registry_entry.get("validation_status") or "") in {"rejected", "retired_from_execution"}:
        policy_reason = policy_reason or "strategy_terminal_status"

    if policy_reason is not None:
        return ShadowSyncSourceResult(
            strategy_id=strategy_id,
            source=source_name,
            source_path=None,
            can_write_shadow=False,
            reason_counts={policy_reason: 1},
        )
    if not config.high_conviction_data_paths:
        return ShadowSyncSourceResult(
            strategy_id=strategy_id,
            source=source_name,
            source_path=None,
            can_write_shadow=True,
            reason_counts={"high_conviction_data_paths_missing": 1},
            warnings=("high_conviction_data_paths_missing",),
        )

    missing = [str(path) for path in config.high_conviction_data_paths if not path.exists()]
    if missing:
        return ShadowSyncSourceResult(
            strategy_id=strategy_id,
            source=source_name,
            source_path=",".join(str(path) for path in config.high_conviction_data_paths),
            can_write_shadow=True,
            reason_counts={"high_conviction_data_path_missing": len(missing)},
            warnings=tuple(f"missing:{path}" for path in missing),
        )

    try:
        report = write_high_conviction_portfolio_report(
            build_high_conviction_portfolio_report(
                HighConvictionPortfolioConfig(
                    run_id=f"{config.resolved_run_id}_high_conviction_shadow",
                    data_paths=config.high_conviction_data_paths,
                    output_dir=_high_conviction_output_dir(config),
                    min_expected_move_bps=(500.0,),
                    risk_reward_ratios=(2.0,),
                    max_hold_hours=(72.0,),
                    exit_modes=("fixed_tp_sl",),
                    cost_profiles=("research_stress",),
                    initial_capital_eur=500.0,
                    max_position_fraction=0.20,
                    risk_per_trade_pct=0.01,
                    max_global_exposure_pct=0.60,
                    max_open_positions=3,
                    cooldown_hours=6.0,
                    max_daily_loss_pct=0.03,
                    critical_drawdown_pct=0.12,
                )
            ),
            _high_conviction_output_dir(config),
        )
    except Exception as exc:
        reason = f"high_conviction_replay_error:{type(exc).__name__}"
        return ShadowSyncSourceResult(
            strategy_id=strategy_id,
            source=source_name,
            source_path=",".join(str(path) for path in config.high_conviction_data_paths),
            can_write_shadow=True,
            reason_counts={reason: 1},
            warnings=(f"{reason}:{exc}",),
        )

    primary = _select_high_conviction_primary_result(report.portfolio_results)
    records = tuple(primary.trade_records) if primary is not None else ()
    if not records:
        return ShadowSyncSourceResult(
            strategy_id=strategy_id,
            source=source_name,
            source_path=",".join(str(path) for path in config.high_conviction_data_paths),
            can_write_shadow=True,
            source_trade_count=0,
            reason_counts={"no_closed_high_conviction_shadow_trades": 1},
            warnings=("no_closed_high_conviction_shadow_trades",),
        )

    inserted = 0
    enriched = 0
    duplicates = 0
    skipped = 0
    inserted_score_counts = _empty_score_counts()
    enriched_score_counts = _empty_score_counts()
    score_origin_counts: dict[str, int] = defaultdict(int)
    latest_closed_at: str | None = None
    reason_counts: dict[str, int] = defaultdict(int)
    warnings: list[str] = []
    for index, record in enumerate(sorted(records, key=lambda item: (item.closed_at, item.symbol)), start=1):
        source_id = _high_conviction_source_id(record, index)
        opportunity_metadata = _trade_record_opportunity_metadata(
            record,
            opportunity_lookup=opportunity_lookup,
            generated_at=generated_at,
            max_window_hours=config.opportunity_match_window_hours,
        )
        if _ledger_trade_exists(state_conn, f"{source_id}:close") or _ledger_trade_exists(
            state_conn, f"{source_id}:open"
        ) or _high_conviction_economic_trade_exists(
            state_conn,
            record,
        ):
            duplicates += 1
            trade_ids = (f"{source_id}:open", f"{source_id}:close")
            if _enrich_existing_trade_metadata(state_conn, trade_ids, opportunity_metadata):
                enriched += 1
                _increment_score_counts(enriched_score_counts, opportunity_metadata)
                score_origin_counts[_opportunity_metadata_origin(opportunity_metadata)] += 1
            else:
                economic_enriched = _enrich_high_conviction_economic_match(state_conn, record, opportunity_metadata)
                enriched += economic_enriched
                if economic_enriched:
                    _increment_score_counts(enriched_score_counts, opportunity_metadata)
                    score_origin_counts[_opportunity_metadata_origin(opportunity_metadata)] += economic_enriched
            continue
        try:
            _insert_trade_record_pair(
                state_conn,
                record,
                source_id=source_id,
                source_name=source_name,
                generated_at=generated_at,
                opportunity_metadata=opportunity_metadata,
            )
            inserted += 1
            _increment_score_counts(inserted_score_counts, opportunity_metadata)
            score_origin_counts[_opportunity_metadata_origin(opportunity_metadata)] += 1
            latest_closed_at = record.closed_at.isoformat()
            reason_counts[str(record.exit_reason or "unknown_exit")] += 1
        except (TypeError, ValueError, sqlite3.Error) as exc:
            skipped += 1
            reason = f"insert_error:{type(exc).__name__}"
            reason_counts[reason] += 1
            warnings.append(reason)

    return ShadowSyncSourceResult(
        strategy_id=strategy_id,
        source=source_name,
        source_path=",".join(str(path) for path in config.high_conviction_data_paths),
        can_write_shadow=True,
        source_trade_count=len(records),
        inserted_trade_count=inserted,
        enriched_trade_count=enriched,
        duplicate_trade_count=duplicates,
        skipped_trade_count=skipped,
        latest_closed_at=latest_closed_at,
        reason_counts=dict(sorted(reason_counts.items())),
        inserted_score_coverage=_score_coverage_from_counts(inserted_score_counts),
        enriched_score_coverage=_score_coverage_from_counts(enriched_score_counts),
        score_origin_counts=dict(sorted(score_origin_counts.items())),
        score_coverage=_score_coverage_for_source(state_conn, strategy_id),
        warnings=tuple(dict.fromkeys(warnings)),
    )


def _select_high_conviction_primary_result(
    rows: Iterable[PortfolioScenarioResult],
) -> PortfolioScenarioResult | None:
    for row in rows:
        scenario = row.scenario
        if (
            row.cost_profile == "research_stress"
            and row.policy == "conservative"
            and float(scenario.get("min_expected_move_bps") or 0.0) == 500.0
            and float(scenario.get("risk_reward_ratio") or 0.0) == 2.0
            and float(scenario.get("max_hold_hours") or 0.0) == 72.0
            and str(scenario.get("exit_mode") or "") == "fixed_tp_sl"
        ):
            return row
    return next(iter(rows), None)


def _high_conviction_output_dir(config: ShadowPaperObservationSyncConfig) -> Path:
    """Return the persistent research output path for High Conviction replay artifacts.

    The shadow sync report itself can still be written under ``reports/``. The
    replay artifacts default to ``data/`` because the daily research container
    mounts that path as a writable persistent volume, while report folders may
    be root-owned after manual VPS checks.
    """

    if config.high_conviction_output_dir is not None:
        return config.high_conviction_output_dir
    return Path("data/research/high_conviction_shadow_sync") / config.resolved_run_id


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


def _select_shadow_source_rows(conn: sqlite3.Connection, table: str) -> list[sqlite3.Row]:
    columns = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    optional = [
        name
        for name in (
            "opportunity_score",
            "score",
            "opportunity_status",
            "opportunity_reason",
            "opportunity_components",
            "regime",
            "timeframe",
            "signal_source",
        )
        if name in columns
    ]
    selected = [
        "id",
        "symbol",
        "variant",
        "position_id",
        "entry_price",
        "exit_price",
        "volume",
        "notional",
        "fees",
        "realized_pnl",
        "reason",
        "opened_at",
        "closed_at",
        "created_at",
        *optional,
    ]
    return conn.execute(
        f"""
        SELECT {', '.join(selected)}
        FROM {table}
        ORDER BY closed_at ASC, id ASC
        """
    ).fetchall()


def _insert_shadow_trade_pair(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    *,
    strategy_id: str,
    source_name: str,
    source_id: str,
    default_regime: str,
    generated_at: str,
    opportunity_metadata: Mapping[str, Any] | None = None,
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
            **dict(opportunity_metadata or {"score_bucket": "missing"}),
        },
        separators=(",", ":"),
    )
    common = {
        "position_id": position_id,
        "instance_id": "shadow_paper",
        "symbol": str(row["symbol"] or "").strip(),
        "volume": volume,
        "strategy_id": strategy_id,
        "timeframe": str(_row_value(row, "timeframe", "shadow_tick") or "shadow_tick"),
        "signal_source": str(
            _row_value(row, "signal_source", None) or f"{source_name}:{row['variant']}"
        ),
        "regime": str(_row_value(row, "regime", default_regime) or default_regime),
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


def _insert_trade_record_pair(
    conn: sqlite3.Connection,
    record: TradeRecord,
    *,
    source_id: str,
    source_name: str,
    generated_at: str,
    opportunity_metadata: Mapping[str, Any] | None = None,
) -> None:
    if record.strategy_id != "high_conviction_swing":
        raise ValueError("high_conviction shadow record must use strategy_id=high_conviction_swing")
    if record.entry_price <= 0.0 or record.exit_price <= 0.0 or record.quantity <= 0.0:
        raise ValueError("high_conviction shadow record requires positive entry/exit/quantity")
    if record.gross_pnl_eur is None or record.net_pnl_eur is None:
        raise ValueError("high_conviction shadow record requires gross and net pnl")
    if record.fees_eur is None or record.slippage_eur is None:
        raise ValueError("high_conviction shadow record requires fees and slippage")
    cost_fields = (record.fees_eur, record.spread_cost_eur, record.slippage_eur, record.latency_cost_eur)
    if any(float(cost) < 0.0 for cost in cost_fields):
        raise ValueError("high_conviction shadow record costs cannot be negative")
    total_cost = sum(float(cost) for cost in cost_fields)

    entry_notional = record.entry_price * record.quantity
    exit_notional = record.exit_price * record.quantity
    total_notional = max(entry_notional + exit_notional, 1e-12)
    fee_entry = max(0.0, record.fees_eur) * (entry_notional / total_notional)
    fee_exit = max(0.0, record.fees_eur) * (exit_notional / total_notional)
    slippage_bps = max(0.0, record.slippage_eur + record.spread_cost_eur + record.latency_cost_eur) / total_notional * 10_000.0
    position_id = f"shadow:high_conviction_swing:{source_id}"
    metadata = json.dumps(
        {
            "source": source_name,
            "source_run_id": record.run_id,
            "entry_reason": record.entry_reason,
            "exit_reason": record.exit_reason,
            "execution_mode": EXECUTION_MODE_SHADOW_PAPER,
            "research_only": True,
            "family": record.metadata.get("family"),
            "policy": record.metadata.get("policy"),
            "expected_move_bps": record.metadata.get("expected_move_bps"),
            "logical_stop_bps": record.metadata.get("logical_stop_bps"),
            "mfe_bps": record.metadata.get("mfe_bps"),
            "mae_bps": record.metadata.get("mae_bps"),
            "cost_bps": record.metadata.get("cost_bps"),
            **dict(opportunity_metadata or {"score_bucket": "missing"}),
        },
        separators=(",", ":"),
    )
    common = {
        "position_id": position_id,
        "instance_id": "shadow_paper",
        "symbol": record.symbol.upper(),
        "volume": record.quantity,
        "strategy_id": record.strategy_id,
        "timeframe": str(record.metadata.get("timeframe") or "multi_timeframe"),
        "signal_source": str(record.metadata.get("signal_source") or source_name),
        "regime": record.regime or str(record.metadata.get("regime") or "unknown"),
        "execution_liquidity": "research_replay",
        "execution_mode": EXECUTION_MODE_SHADOW_PAPER,
    }
    _insert_trade_ledger_row(
        conn,
        trade_id=f"{source_id}:open",
        side=record.side or "buy",
        expected_price=record.entry_price,
        executed_price=record.entry_price,
        fees=fee_entry,
        slippage_bps=slippage_bps,
        realized_pnl=None,
        gross_pnl=None,
        net_pnl=None,
        is_opening_leg=1,
        is_closing_leg=0,
        created_at=record.opened_at.isoformat() if record.opened_at else generated_at,
        signal_id=source_id,
        decision_id=metadata,
        **common,
    )
    _insert_trade_ledger_row(
        conn,
        trade_id=f"{source_id}:close",
        side="sell",
        expected_price=record.exit_price,
        executed_price=record.exit_price,
        fees=fee_exit,
        slippage_bps=slippage_bps,
        realized_pnl=record.net_pnl_eur,
        gross_pnl=record.gross_pnl_eur,
        net_pnl=record.net_pnl_eur,
        is_opening_leg=0,
        is_closing_leg=1,
        created_at=record.closed_at.isoformat() if record.closed_at else generated_at,
        signal_id=source_id,
        decision_id=metadata,
        **common,
    )


def _high_conviction_source_id(record: TradeRecord, index: int) -> str:
    payload = "|".join(
        (
            record.strategy_id,
            record.symbol,
            record.opened_at.isoformat(),
            record.closed_at.isoformat(),
            f"{record.entry_price:.12g}",
            f"{record.exit_price:.12g}",
            f"{record.quantity:.12g}",
            str(index),
        )
    )
    digest = sha1(payload.encode("utf-8")).hexdigest()[:16]
    return f"high_conviction_research:{digest}"


def _high_conviction_economic_trade_exists(conn: sqlite3.Connection, record: TradeRecord) -> bool:
    """Detect prior High Conviction syncs even if their replay run_id changed."""

    closed_at = record.closed_at.isoformat() if record.closed_at else None
    if closed_at is None:
        return False
    row = conn.execute(
        """
        SELECT 1
        FROM trade_ledger
        WHERE strategy_id=?
          AND execution_mode=?
          AND is_closing_leg=1
          AND symbol=?
          AND created_at=?
          AND ABS(executed_price - ?) < 0.000000001
          AND ABS(volume - ?) < 0.000000001
          AND ABS(COALESCE(net_pnl, 0.0) - ?) < 0.000000001
        LIMIT 1
        """,
        (
            "high_conviction_swing",
            EXECUTION_MODE_SHADOW_PAPER,
            record.symbol.upper(),
            closed_at,
            float(record.exit_price),
            float(record.quantity),
            float(record.net_pnl_eur or 0.0),
        ),
    ).fetchone()
    return row is not None


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


def _shadow_row_opportunity_metadata(
    row: sqlite3.Row,
    *,
    opportunity_lookup: Mapping[str, tuple[dict[str, Any], ...]],
    generated_at: str,
    max_window_hours: float,
) -> dict[str, Any]:
    merged = _merge_opportunity_metadata(
        _opportunity_metadata_from_mapping(row),
        _lookup_opportunity_metadata(
            opportunity_lookup,
            symbol=str(row["symbol"] or ""),
            timestamp=str(row["opened_at"] or row["closed_at"] or generated_at),
            max_window_hours=max_window_hours,
        ),
    )
    return _with_score_v2_metadata(merged, _row_score_v2_source(row), merged)


def _trade_record_opportunity_metadata(
    record: TradeRecord,
    *,
    opportunity_lookup: Mapping[str, tuple[dict[str, Any], ...]],
    generated_at: str,
    max_window_hours: float,
) -> dict[str, Any]:
    merged = _merge_opportunity_metadata(
        _opportunity_metadata_from_mapping(record.metadata),
        _lookup_opportunity_metadata(
            opportunity_lookup,
            symbol=record.symbol,
            timestamp=record.opened_at.isoformat() if record.opened_at else generated_at,
            max_window_hours=max_window_hours,
        ),
    )
    return _with_score_v2_metadata(merged, _trade_record_score_v2_source(record), merged)


def _enrich_existing_trade_metadata(
    conn: sqlite3.Connection,
    trade_ids: Iterable[str],
    opportunity_metadata: Mapping[str, Any],
) -> int:
    """Fill missing score metadata on existing shadow rows without changing PnL."""

    if opportunity_metadata.get("score_bucket") not in {"high", "medium", "low"} and opportunity_metadata.get(
        "score_v2_bucket"
    ) not in {"high", "medium", "low", "missing"}:
        return 0
    updated = 0
    for trade_id in trade_ids:
        row = conn.execute(
            "SELECT id, decision_id FROM trade_ledger WHERE trade_id=? LIMIT 1",
            (trade_id,),
        ).fetchone()
        if row is None:
            continue
        current = _json_mapping(row["decision_id"])
        current_score = _opportunity_metadata_from_mapping(current)
        if current_score.get("score_bucket") in {"high", "medium", "low"} and current.get("score_v2_bucket"):
            continue
        merged = dict(current)
        merged.update(dict(opportunity_metadata))
        merged["opportunity_metadata_enriched"] = True
        conn.execute(
            "UPDATE trade_ledger SET decision_id=? WHERE id=?",
            (json.dumps(merged, separators=(",", ":")), int(row["id"])),
        )
        updated += 1
    return 1 if updated else 0


def _enrich_high_conviction_economic_match(
    conn: sqlite3.Connection,
    record: TradeRecord,
    opportunity_metadata: Mapping[str, Any],
) -> int:
    closed_at = record.closed_at.isoformat() if record.closed_at else None
    if closed_at is None:
        return 0
    rows = conn.execute(
        """
        SELECT trade_id
        FROM trade_ledger
        WHERE strategy_id=?
          AND execution_mode=?
          AND symbol=?
          AND position_id IN (
              SELECT position_id
              FROM trade_ledger
              WHERE strategy_id=?
                AND execution_mode=?
                AND is_closing_leg=1
                AND symbol=?
                AND created_at=?
                AND ABS(executed_price - ?) < 0.000000001
                AND ABS(volume - ?) < 0.000000001
                AND ABS(COALESCE(net_pnl, 0.0) - ?) < 0.000000001
          )
        """,
        (
            "high_conviction_swing",
            EXECUTION_MODE_SHADOW_PAPER,
            record.symbol.upper(),
            "high_conviction_swing",
            EXECUTION_MODE_SHADOW_PAPER,
            record.symbol.upper(),
            closed_at,
            float(record.exit_price),
            float(record.quantity),
            float(record.net_pnl_eur or 0.0),
        ),
    ).fetchall()
    return _enrich_existing_trade_metadata(
        conn,
        tuple(str(row["trade_id"]) for row in rows if row["trade_id"]),
        opportunity_metadata,
    )


def _opportunity_metadata_from_mapping(source: Mapping[str, Any]) -> dict[str, Any]:
    score = _optional_float(_mapping_value(source, "opportunity_score"))
    score_source = "opportunity_score" if score is not None else None
    if score is None:
        score = _optional_float(_mapping_value(source, "score"))
        if score is not None:
            score_source = "score"
    if score is None:
        score = _optional_float(_mapping_value(source, "router_score"))
        if score is not None:
            score_source = "router_score"
    metadata: dict[str, Any] = {"score_bucket": _score_bucket(score)}
    if score is not None:
        metadata["opportunity_score"] = score
        metadata["opportunity_metadata_origin"] = "source"
    else:
        metadata["opportunity_metadata_origin"] = "missing"
    if score_source is not None:
        metadata["opportunity_score_source"] = score_source
    has_opportunity_shape = any(
        _mapping_value(source, key) not in (None, "")
        for key in (
            "opportunity_score",
            "score",
            "router_score",
            "opportunity_status",
            "status",
            "router_action",
            "opportunity_reason",
            "router_reason",
            "opportunity_components",
            "components",
        )
    )
    status = _mapping_value(source, "opportunity_status")
    if status in (None, "") and has_opportunity_shape:
        status = _mapping_value(source, "status")
    if status in (None, "") and has_opportunity_shape:
        status = _mapping_value(source, "router_action")
    reason = _mapping_value(source, "opportunity_reason")
    if reason in (None, "") and has_opportunity_shape:
        reason = _mapping_value(source, "reason")
    if reason in (None, "") and has_opportunity_shape:
        reason = _mapping_value(source, "router_reason")
    components = _mapping_value(source, "opportunity_components")
    if components in (None, "") and has_opportunity_shape:
        components = _mapping_value(source, "components")
    if status not in (None, ""):
        metadata["opportunity_status"] = str(status)
    if reason not in (None, ""):
        metadata["opportunity_reason"] = str(reason)
    parsed_components = _json_mapping(components)
    if parsed_components:
        metadata["opportunity_components"] = parsed_components
    return _with_score_v2_metadata(metadata, _mapping_score_v2_source(source), metadata)


def _merge_opportunity_metadata(primary: Mapping[str, Any], fallback: Mapping[str, Any]) -> dict[str, Any]:
    """Keep explicit source score first, then enrich from runtime score lookup."""

    merged = dict(primary)
    if merged.get("score_bucket") != "missing":
        return _with_score_v2_metadata(merged, merged)
    if fallback.get("score_bucket") in {"high", "medium", "low"}:
        merged.update(fallback)
    return _with_score_v2_metadata(merged, merged)


def _with_score_v2_metadata(metadata: Mapping[str, Any], *sources: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(metadata)
    current_bucket = merged.get("score_v2_bucket")
    if current_bucket in {"high", "medium", "low"}:
        return merged
    if current_bucket == "missing" and not sources:
        return merged
    score_source: dict[str, Any] = {}
    for source in sources:
        score_source.update(_sanitize_score_v2_source(source))
    if not score_source:
        score_source = {}
    score_v2 = build_opportunity_score_v2_metadata(score_source)
    merged.update(score_v2)
    return merged


def _mapping_score_v2_source(source: Mapping[str, Any]) -> dict[str, Any]:
    raw: dict[str, Any] = {}
    for key in (
        "strategy_id",
        "symbol",
        "timeframe",
        "regime",
        "opportunity_score",
        "score",
        "router_score",
        "expected_move_bps",
        "expected_gross_move_bps",
        "estimated_total_cost_bps",
        "estimated_round_trip_cost_bps",
        "estimated_fees_bps",
        "estimated_spread_cost_bps",
        "estimated_slippage_bps",
        "latency_buffer_bps",
        "estimated_net_edge_bps",
        "expected_net_edge_bps",
        "logical_stop_bps",
        "stop_loss_bps",
        "risk_reward_ratio",
        "breakout_quality",
        "breakout_score",
        "trend_quality",
        "trend_strength",
        "trend_timeframe_alignment",
        "multi_timeframe_alignment",
        "volatility_expansion",
        "volatility_expansion_score",
        "support_resistance",
        "support_strength",
        "spread_bps",
        "liquidity_score",
        "depth_score",
        "pair_health_score",
        "pair_health_penalty_bps",
        "segment_health_score",
        "segment_health_penalty_bps",
        "trade_frequency_penalty_bps",
        "drawdown_penalty_bps",
    ):
        value = _mapping_value(source, key)
        if value not in (None, ""):
            raw[key] = value
    components = _mapping_value(source, "opportunity_components")
    parsed_components = _json_mapping(components)
    if parsed_components:
        raw["opportunity_components"] = parsed_components
    nested = _mapping_value(source, "components")
    parsed_nested = _json_mapping(nested)
    if parsed_nested:
        raw["components"] = parsed_nested
    return _sanitize_score_v2_source(raw)


def _row_score_v2_source(row: sqlite3.Row) -> dict[str, Any]:
    source = _mapping_score_v2_source(row)
    source.setdefault("symbol", str(_row_value(row, "symbol", "") or ""))
    source.setdefault("timeframe", str(_row_value(row, "timeframe", "") or ""))
    source.setdefault("estimated_total_cost_bps", _safe_float(_row_value(row, "cost_bps", None)) or None)
    return _sanitize_score_v2_source(source)


def _trade_record_score_v2_source(record: TradeRecord) -> dict[str, Any]:
    metadata = record.metadata if isinstance(record.metadata, Mapping) else {}
    source = _mapping_score_v2_source(metadata)
    source.setdefault("strategy_id", record.strategy_id)
    source.setdefault("symbol", record.symbol)
    source.setdefault("timeframe", str(metadata.get("timeframe") or "multi_timeframe"))
    source.setdefault("regime", record.regime or metadata.get("regime"))
    if metadata.get("cost_bps") not in (None, ""):
        source.setdefault("estimated_total_cost_bps", metadata.get("cost_bps"))
    if metadata.get("logical_stop_bps") not in (None, ""):
        source.setdefault("logical_stop_bps", metadata.get("logical_stop_bps"))
    return _sanitize_score_v2_source(source)


def _sanitize_score_v2_source(source: Mapping[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in source.items():
        normalized = str(key).lower()
        if normalized in FORBIDDEN_SCORE_V2_KEYS or normalized in FORBIDDEN_SCORE_V2_CONTAINER_KEYS:
            continue
        if isinstance(value, Mapping):
            nested = _sanitize_score_v2_source(value)
            if nested:
                cleaned[str(key)] = nested
            continue
        if isinstance(value, (list, tuple)):
            items = []
            for item in value:
                if isinstance(item, Mapping):
                    nested = _sanitize_score_v2_source(item)
                    if nested:
                        items.append(nested)
                elif not isinstance(item, (list, tuple)):
                    items.append(item)
            if items:
                cleaned[str(key)] = items
            continue
        cleaned[str(key)] = value
    return cleaned


def _score_bucket(score: float | None) -> str:
    if score is None:
        return "missing"
    if score >= 70.0:
        return "high"
    if score >= 40.0:
        return "medium"
    return "low"


def _mapping_value(source: Mapping[str, Any], key: str) -> Any:
    if isinstance(source, sqlite3.Row):
        return _row_value(source, key)
    return source.get(key)


def _row_value(row: sqlite3.Row, key: str, default: Any = None) -> Any:
    try:
        return row[key]
    except (IndexError, KeyError):
        return default


def _json_mapping(raw: Any) -> dict[str, Any]:
    if isinstance(raw, Mapping):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, Mapping) else {}
    return {}


def _load_opportunity_score_lookup(conn: sqlite3.Connection) -> dict[str, tuple[dict[str, Any], ...]]:
    """Load runtime opportunity scores as a metadata-only lookup.

    The lookup is intentionally advisory: it enriches shadow observations with
    the nearest already-persisted opportunity score but never authorizes
    execution or promotion.
    """

    if not _table_exists(conn, "decision_ledger"):
        return {}
    rows = conn.execute(
        """
        SELECT symbol, event_type, event_status, reason, source, payload_json, created_at
        FROM decision_ledger
        WHERE payload_json IS NOT NULL
        ORDER BY created_at ASC, id ASC
        """
    ).fetchall()
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        payload = _json_mapping(row["payload_json"])
        opportunity = payload.get("opportunity") if isinstance(payload.get("opportunity"), Mapping) else {}
        candidates = (opportunity, payload)
        metadata: dict[str, Any] = {"score_bucket": "missing"}
        for candidate in candidates:
            parsed = _opportunity_metadata_from_mapping(candidate)
            if parsed.get("score_bucket") != "missing":
                metadata = parsed
                break
        if metadata.get("score_bucket") == "missing":
            continue
        parsed_at = _parse_datetime(row["created_at"])
        if parsed_at is None:
            continue
        metadata.update(
            {
                "opportunity_metadata_origin": "decision_ledger_lookup",
                "opportunity_source": str(row["source"] or "decision_ledger"),
                "opportunity_event_type": str(row["event_type"] or ""),
                "opportunity_event_status": str(row["event_status"] or ""),
                "opportunity_event_reason": str(row["reason"] or ""),
                "opportunity_event_created_at": parsed_at.isoformat(),
            }
        )
        grouped[symbol_key(row["symbol"])].append({"created_at": parsed_at, "metadata": metadata})
    return {key: tuple(values) for key, values in grouped.items()}


def _lookup_opportunity_metadata(
    lookup: Mapping[str, tuple[dict[str, Any], ...]],
    *,
    symbol: str,
    timestamp: str,
    max_window_hours: float,
) -> dict[str, Any]:
    events = lookup.get(symbol_key(symbol), ())
    if not events:
        return {}
    target = _parse_datetime(timestamp)
    if target is None:
        return {}
    max_delta = max(0.0, float(max_window_hours)) * 3600.0
    best: tuple[float, dict[str, Any]] | None = None
    for event in events:
        event_at = event.get("created_at")
        if not isinstance(event_at, datetime):
            continue
        delta = (target - event_at).total_seconds()
        if delta < 0.0:
            continue
        if delta > max_delta:
            continue
        if best is None or delta < best[0]:
            best = (delta, dict(event.get("metadata") or {}))
    if best is None:
        return {}
    metadata = dict(best[1])
    metadata["opportunity_metadata_origin"] = "decision_ledger_lookup"
    metadata["opportunity_match_delta_seconds"] = round(best[0], 3)
    return metadata


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif value not in (None, ""):
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


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


def _build_score_coverage(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT strategy_id, symbol, decision_id
        FROM trade_ledger
        WHERE COALESCE(is_closing_leg, 0) = 1
          AND strategy_id IS NOT NULL
          AND strategy_id != ?
          AND execution_mode = ?
        """,
        (LEGACY_UNATTRIBUTED_STRATEGY_ID, EXECUTION_MODE_SHADOW_PAPER),
    ).fetchall()
    return {
        "global": _score_coverage_rows(rows),
        "by_strategy": _score_coverage_group(rows, "strategy_id"),
        "by_symbol": _score_coverage_group(rows, "symbol"),
    }


def _empty_score_counts() -> dict[str, int]:
    return {"high": 0, "medium": 0, "low": 0, "missing": 0}


def _opportunity_metadata_origin(metadata: Mapping[str, Any]) -> str:
    origin = str(metadata.get("opportunity_metadata_origin") or "")
    if origin in {"source", "decision_ledger_lookup", "missing"}:
        return origin
    if metadata.get("score_bucket") in {"high", "medium", "low"}:
        return "unknown_scored"
    return "missing"


def _increment_score_counts(counts: dict[str, int], metadata: Mapping[str, Any]) -> None:
    bucket = str(metadata.get("score_bucket") or "missing")
    if bucket not in counts:
        bucket = "missing"
    counts[bucket] += 1


def _score_coverage_from_counts(counts: Mapping[str, int]) -> dict[str, Any]:
    buckets = {bucket: int(counts.get(bucket, 0)) for bucket in ("high", "medium", "low", "missing")}
    total = sum(buckets.values())
    scored = total - buckets["missing"]
    return {
        "total": total,
        "scored": scored,
        "score_coverage_pct": (scored / total * 100.0) if total else 0.0,
        "buckets": buckets,
    }


def _score_coverage_for_source(conn: sqlite3.Connection, strategy_id: str) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT strategy_id, symbol, decision_id
        FROM trade_ledger
        WHERE COALESCE(is_closing_leg, 0) = 1
          AND strategy_id = ?
          AND execution_mode = ?
        """,
        (strategy_id, EXECUTION_MODE_SHADOW_PAPER),
    ).fetchall()
    return _score_coverage_rows(rows)


def _score_coverage_group(rows: Sequence[sqlite3.Row], key: str) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        grouped[str(row[key] or "unknown")].append(row)
    return {name: _score_coverage_rows(tuple(items)) for name, items in sorted(grouped.items())}


def _score_coverage_rows(rows: Sequence[sqlite3.Row]) -> dict[str, Any]:
    buckets = {"high": 0, "medium": 0, "low": 0, "missing": 0}
    for row in rows:
        metadata = _opportunity_metadata_from_mapping(_json_mapping(row["decision_id"]))
        bucket = str(metadata.get("score_bucket") or "missing")
        if bucket not in buckets:
            bucket = "missing"
        buckets[bucket] += 1
    total = len(rows)
    scored = total - buckets["missing"]
    return {
        "total": total,
        "scored": scored,
        "score_coverage_pct": (scored / total * 100.0) if total else 0.0,
        "buckets": buckets,
    }


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
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_trade_ledger_trade_id_unique ON trade_ledger(trade_id)")


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


def _optional_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


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
        "| Strategy | Source | Can write | Source trades | Inserted | Inserted coverage | Enriched | Enriched coverage | Duplicates | Skipped | Score coverage | Origins | Reasons |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for item in report.source_results:
        coverage = item.score_coverage.get("score_coverage_pct") if item.score_coverage else None
        coverage_text = "n/a" if coverage is None else f"{float(coverage):.2f}%"
        inserted_coverage = item.inserted_score_coverage.get("score_coverage_pct") if item.inserted_score_coverage else None
        inserted_coverage_text = "n/a" if inserted_coverage is None else f"{float(inserted_coverage):.2f}%"
        enriched_coverage = item.enriched_score_coverage.get("score_coverage_pct") if item.enriched_score_coverage else None
        enriched_coverage_text = "n/a" if enriched_coverage is None else f"{float(enriched_coverage):.2f}%"
        origins = ", ".join(f"{key}:{value}" for key, value in item.score_origin_counts.items()) or "none"
        lines.append(
            "| {strategy} | {source} | {can_write} | {source_trades} | {inserted} | {inserted_coverage} | {enriched} | {enriched_coverage} | {duplicates} | {skipped} | {coverage} | {origins} | {reasons} |".format(
                strategy=item.strategy_id,
                source=item.source,
                can_write=str(item.can_write_shadow).lower(),
                source_trades=item.source_trade_count,
                inserted=item.inserted_trade_count,
                inserted_coverage=inserted_coverage_text,
                enriched=item.enriched_trade_count,
                enriched_coverage=enriched_coverage_text,
                duplicates=item.duplicate_trade_count,
                skipped=item.skipped_trade_count,
                coverage=coverage_text,
                origins=origins,
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
            "## Score Coverage",
            "",
            f"- Global: `{report.score_coverage.get('global', {}).get('score_coverage_pct', 0.0):.2f}%`",
            "",
            "| Strategy | Total | Scored | Coverage | High | Medium | Low | Missing |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for strategy, coverage in report.score_coverage.get("by_strategy", {}).items():
        buckets = coverage.get("buckets", {})
        lines.append(
            "| {strategy} | {total} | {scored} | {coverage:.2f}% | {high} | {medium} | {low} | {missing} |".format(
                strategy=strategy,
                total=coverage.get("total", 0),
                scored=coverage.get("scored", 0),
                coverage=float(coverage.get("score_coverage_pct") or 0.0),
                high=buckets.get("high", 0),
                medium=buckets.get("medium", 0),
                low=buckets.get("low", 0),
                missing=buckets.get("missing", 0),
            )
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
