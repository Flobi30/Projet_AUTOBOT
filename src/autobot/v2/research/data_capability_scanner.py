"""Research-only data capability scanner for AUTOBOT.

The scanner inventories research data sources and maps them to alpha families
that can be tested. It never imports runtime order paths, never starts services,
and never mutates trading state.
"""

from __future__ import annotations

import csv
import json
import sqlite3
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


CAPABILITY_IDS = (
    "spot_ohlcv",
    "multi_symbol_ohlcv",
    "orderbook_depth_snapshots",
    "spread_history",
    "funding_rates",
    "futures_perp_prices",
    "spot_perp_basis",
    "open_interest",
    "liquidation_events",
    "volume_anomalies",
    "news_sentiment",
    "exchange_fees",
    "slippage_fill_history",
)

ALPHA_UNLOCKS = {
    "spot_ohlcv": ("volatility_breakout", "long_trend", "market_structure", "volatility_regime"),
    "multi_symbol_ohlcv": ("cross_sectional_momentum", "relative_value"),
    "orderbook_depth_snapshots": ("order_flow_imbalance", "liquidation_cascade", "market_making"),
    "spread_history": ("cost_sensitive_intraday_filter", "order_flow_imbalance"),
    "funding_rates": ("funding_basis",),
    "futures_perp_prices": ("funding_basis", "spot_perp_basis"),
    "spot_perp_basis": ("funding_basis",),
    "open_interest": ("funding_basis", "liquidation_cascade"),
    "liquidation_events": ("liquidation_cascade",),
    "volume_anomalies": ("volatility_breakout", "liquidity_sweep_fakeout"),
    "news_sentiment": ("news_event_filter",),
    "exchange_fees": ("all_cost_sensitive_research",),
    "slippage_fill_history": ("paper_research_parity", "execution_cost_calibration"),
}

DERIVATIVES_CAPABILITIES = {"funding_rates", "futures_perp_prices", "spot_perp_basis", "open_interest"}


@dataclass(frozen=True)
class DataCapability:
    capability_id: str
    available: bool
    source_paths: tuple[str, ...] = ()
    provider: str = "unknown"
    symbols: tuple[str, ...] = ()
    timeframes: tuple[str, ...] = ()
    start_at: str | None = None
    end_at: str | None = None
    row_count: int = 0
    duplicate_count: int = 0
    gap_count: int = 0
    freshness_seconds: float | None = None
    storage_size_bytes: int = 0
    quality_status: str = "missing"
    alpha_families_unlocked: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    proxy_status: str = "not_proxy"
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in ("source_paths", "symbols", "timeframes", "alpha_families_unlocked", "blockers", "notes"):
            payload[key] = list(payload[key])
        return payload


@dataclass(frozen=True)
class OHLCVBackfillPlan:
    current_start_at: str | None
    current_end_at: str | None
    current_row_count: int
    current_symbols: tuple[str, ...]
    current_timeframes: tuple[str, ...]
    target_intraday_months_minimum: int = 6
    target_intraday_months_preferred: int = 12
    recommended_provider_priority: tuple[str, ...] = ("kraken_public_ohlcv", "ccxt_kraken_public_ohlcv", "external_public_csv_if_verified")
    bounded_commands: tuple[str, ...] = ()
    storage_policy_notes: tuple[str, ...] = ()
    estimated_storage_multiplier_for_12m: float = 0.0
    status: str = "plan_only"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in ("current_symbols", "current_timeframes", "recommended_provider_priority", "bounded_commands", "storage_policy_notes"):
            payload[key] = list(payload[key])
        return payload


@dataclass(frozen=True)
class DerivativesDataPlan:
    data_type: str
    required_for: tuple[str, ...]
    potential_sources: tuple[str, ...]
    complexity: str
    estimated_storage: str
    recommended_frequency: str
    priority: str
    current_status: str
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in ("required_for", "potential_sources", "notes"):
            payload[key] = list(payload[key])
        return payload


@dataclass(frozen=True)
class ResearchStoragePolicy:
    raw_data: str
    canonical_data: str
    deduped_data: str
    manifests: str
    retention: str
    compression: str
    safe_cleanup: tuple[str, ...]
    protected_paths: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["safe_cleanup"] = list(self.safe_cleanup)
        payload["protected_paths"] = list(self.protected_paths)
        return payload


@dataclass(frozen=True)
class DataCapabilityScanReport:
    run_id: str
    generated_at: str
    data_roots: tuple[str, ...]
    state_db: str | None
    capabilities: tuple[DataCapability, ...]
    alpha_family_status: dict[str, dict[str, Any]]
    rejected_family_status: dict[str, dict[str, Any]]
    ohlcv_backfill_plan: OHLCVBackfillPlan
    derivatives_data_plan: tuple[DerivativesDataPlan, ...]
    research_storage_policy: ResearchStoragePolicy
    scheduler_data_state: dict[str, Any]
    scheduler_notes: tuple[str, ...]
    safety_notes: tuple[str, ...] = (
        "Research-only data capability scan.",
        "No live trading, paper capital, promotion, shadow activation, sizing, leverage, UI, or runtime order path.",
        "No orders are created.",
        "Grid remains no-go.",
    )
    json_report_path: str | None = None
    markdown_report_path: str | None = None
    paper_capital_allowed: bool = False
    live_allowed: bool = False
    promotable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "data_roots": list(self.data_roots),
            "state_db": self.state_db,
            "capabilities": [item.to_dict() for item in self.capabilities],
            "alpha_family_status": self.alpha_family_status,
            "rejected_family_status": self.rejected_family_status,
            "ohlcv_backfill_plan": self.ohlcv_backfill_plan.to_dict(),
            "derivatives_data_plan": [item.to_dict() for item in self.derivatives_data_plan],
            "research_storage_policy": self.research_storage_policy.to_dict(),
            "scheduler_data_state": self.scheduler_data_state,
            "scheduler_notes": list(self.scheduler_notes),
            "safety_notes": list(self.safety_notes),
            "json_report_path": self.json_report_path,
            "markdown_report_path": self.markdown_report_path,
            "paper_capital_allowed": self.paper_capital_allowed,
            "live_allowed": self.live_allowed,
            "promotable": self.promotable,
        }


def build_data_capability_scan_report(
    *,
    run_id: str,
    data_roots: Sequence[str | Path],
    state_db: str | Path | None = None,
    memory_path: str | Path = "reports/research/alpha_research_memory.json",
) -> DataCapabilityScanReport:
    roots = tuple(Path(path) for path in data_roots)
    root_files = _files_under(roots)
    state_db_path = Path(state_db) if state_db else None
    canonical_manifest = _latest_canonical_ohlcv_manifest(roots)
    derivatives_manifest = _latest_kraken_futures_derivatives_manifest(roots)
    capabilities = _build_capabilities(
        root_files,
        state_db_path,
        canonical_manifest=canonical_manifest,
        derivatives_manifest=derivatives_manifest,
    )
    capability_by_id = {item.capability_id: item for item in capabilities}
    alpha_status = _alpha_family_status(capability_by_id)
    rejected_status = _rejected_family_status(memory_path, capability_by_id)
    ohlcv = capability_by_id["spot_ohlcv"]
    scheduler_data_state = _scheduler_data_state(roots, capability_by_id, alpha_status, canonical_manifest, derivatives_manifest)
    report = DataCapabilityScanReport(
        run_id=run_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        data_roots=tuple(str(path) for path in roots),
        state_db=str(state_db_path) if state_db_path else None,
        capabilities=capabilities,
        alpha_family_status=alpha_status,
        rejected_family_status=rejected_status,
        ohlcv_backfill_plan=_build_ohlcv_backfill_plan(ohlcv),
        derivatives_data_plan=_build_derivatives_plan(capability_by_id),
        research_storage_policy=_storage_policy(),
        scheduler_data_state=scheduler_data_state,
        scheduler_notes=_scheduler_notes(alpha_status, rejected_status, scheduler_data_state),
    )
    return report


def write_data_capability_scan_report(
    report: DataCapabilityScanReport,
    output_dir: str | Path,
) -> DataCapabilityScanReport:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / f"{report.run_id}.json"
    markdown_path = output / f"{report.run_id}.md"
    json_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(render_data_capability_scan_report(report), encoding="utf-8")
    return replace(report, json_report_path=str(json_path), markdown_report_path=str(markdown_path))


def render_data_capability_scan_report(report: DataCapabilityScanReport) -> str:
    lines = [
        f"# P18H Research Data Expansion Plan - {report.run_id}",
        "",
        f"Generated at: `{report.generated_at}`",
        "",
        "## Data Capabilities",
        "",
        "| Capability | Available | Rows | Symbols | Timeframes | Start | End | Quality | Unlocks | Blockers |",
        "| --- | ---: | ---: | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in report.capabilities:
        lines.append(
            f"| `{item.capability_id}` | `{item.available}` | {item.row_count} | "
            f"{', '.join(item.symbols) or '-'} | {', '.join(item.timeframes) or '-'} | "
            f"{item.start_at or '-'} | {item.end_at or '-'} | `{item.quality_status}` | "
            f"{', '.join(item.alpha_families_unlocked) or '-'} | {', '.join(item.blockers) or 'none'} |"
        )
    lines.extend(["", "## Alpha Families", ""])
    lines.append("| Family | Status | Capabilities | Blockers | Notes |")
    lines.append("| --- | --- | --- | --- | --- |")
    for family, payload in sorted(report.alpha_family_status.items()):
        lines.append(
            f"| `{family}` | `{payload['status']}` | {', '.join(payload.get('available_capabilities', [])) or '-'} | "
            f"{', '.join(payload.get('blockers', [])) or 'none'} | {', '.join(payload.get('notes', [])) or '-'} |"
        )
    lines.extend(["", "## Rejected Families Retest Gate", ""])
    lines.append("| Family | Status | Retest Allowed | Reason |")
    lines.append("| --- | --- | ---: | --- |")
    for family, payload in sorted(report.rejected_family_status.items()):
        lines.append(
            f"| `{family}` | `{payload['status']}` | `{payload['retest_allowed']}` | {payload['reason']} |"
        )
    lines.extend(["", "## OHLCV Backfill Plan", ""])
    for key, value in report.ohlcv_backfill_plan.to_dict().items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Scheduler Data State", ""])
    for key, value in report.scheduler_data_state.items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Derivatives / Event Data Plan", ""])
    lines.append("| Data | Status | Priority | Complexity | Sources | Unlocks | Notes |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for item in report.derivatives_data_plan:
        lines.append(
            f"| `{item.data_type}` | `{item.current_status}` | `{item.priority}` | `{item.complexity}` | "
            f"{', '.join(item.potential_sources)} | {', '.join(item.required_for)} | {', '.join(item.notes)} |"
        )
    lines.extend(["", "## Research Storage Policy", ""])
    for key, value in report.research_storage_policy.to_dict().items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Scheduler Notes", ""])
    lines.extend(f"- {item}" for item in report.scheduler_notes)
    lines.extend(["", "## Safety", ""])
    lines.extend(f"- {item}" for item in report.safety_notes)
    lines.append(f"- paper_capital_allowed: `{report.paper_capital_allowed}`")
    lines.append(f"- live_allowed: `{report.live_allowed}`")
    lines.append(f"- promotable: `{report.promotable}`")
    lines.append("")
    return "\n".join(lines)


def _build_capabilities(
    files: Sequence[Path],
    state_db: Path | None,
    *,
    canonical_manifest: Mapping[str, Any] | None = None,
    derivatives_manifest: Mapping[str, Any] | None = None,
) -> tuple[DataCapability, ...]:
    ohlcv = _scan_ohlcv(files, canonical_manifest=canonical_manifest)
    spread_depth = _scan_spread_depth(files)
    exchange_fees = _scan_named_files(files, "exchange_fees", ("fee", "cost_profile"), provider="autobot_cost_profiles")
    volume_anomalies = _volume_anomaly_capability(ohlcv)
    slippage = _scan_slippage_fill_history(state_db)
    derivatives = _derivatives_capabilities_from_manifest(derivatives_manifest) if derivatives_manifest else {}
    raw = {
        "spot_ohlcv": ohlcv,
        "multi_symbol_ohlcv": _multi_symbol_ohlcv_capability(ohlcv),
        "orderbook_depth_snapshots": spread_depth["orderbook_depth_snapshots"],
        "spread_history": spread_depth["spread_history"],
        "funding_rates": derivatives.get("funding_rates") or _scan_named_files(files, "funding_rates", ("funding",)),
        "futures_perp_prices": derivatives.get("futures_perp_prices") or _scan_named_files(files, "futures_perp_prices", ("perp", "futures", "mark_price", "index_price")),
        "spot_perp_basis": derivatives.get("spot_perp_basis") or _scan_named_files(files, "spot_perp_basis", ("basis",)),
        "open_interest": derivatives.get("open_interest") or _scan_named_files(files, "open_interest", ("open_interest", "oi")),
        "liquidation_events": _scan_named_files(files, "liquidation_events", ("liquidation",)),
        "volume_anomalies": volume_anomalies,
        "news_sentiment": _scan_named_files(files, "news_sentiment", ("news", "sentiment")),
        "exchange_fees": exchange_fees,
        "slippage_fill_history": slippage,
    }
    return tuple(raw[item] for item in CAPABILITY_IDS)


def _scan_ohlcv(files: Sequence[Path], *, canonical_manifest: Mapping[str, Any] | None = None) -> DataCapability:
    if canonical_manifest:
        final_duplicate_count = sum(
            int(item.get("duplicate_count") or 0)
            for item in canonical_manifest.get("files", ())
            if isinstance(item, Mapping)
        )
        gap_count = int(canonical_manifest.get("gap_count") or 0)
        quality = "canonical_ready" if final_duplicate_count == 0 and gap_count == 0 else "canonical_ready_with_gaps"
        source_paths = tuple(
            str(item.get("csv_path"))
            for item in canonical_manifest.get("files", ())
            if isinstance(item, Mapping) and item.get("csv_path")
        )
        return DataCapability(
            capability_id="spot_ohlcv",
            available=int(canonical_manifest.get("canonical_row_count") or 0) > 0,
            source_paths=source_paths[:50],
            provider=str(canonical_manifest.get("exchange") or "kraken") + "_public_ohlcv_canonical",
            symbols=tuple(str(item) for item in canonical_manifest.get("symbols", ())),
            timeframes=tuple(str(item) for item in canonical_manifest.get("timeframes", ())),
            start_at=canonical_manifest.get("start_at"),
            end_at=canonical_manifest.get("end_at"),
            row_count=int(canonical_manifest.get("canonical_row_count") or 0),
            duplicate_count=final_duplicate_count,
            gap_count=gap_count,
            freshness_seconds=_freshness_seconds(tuple(Path(item) for item in source_paths)),
            storage_size_bytes=int(canonical_manifest.get("storage_size_bytes") or 0),
            quality_status=quality,
            alpha_families_unlocked=ALPHA_UNLOCKS["spot_ohlcv"],
            blockers=() if final_duplicate_count == 0 else ("canonical_duplicate_bars_present",),
            notes=("canonical_ohlcv_snapshot", f"snapshot_id={canonical_manifest.get('snapshot_id')}"),
        )
    csv_files = [path for path in files if path.suffix.lower() == ".csv" and _looks_like_ohlcv(path)]
    symbols: set[str] = set()
    timeframes: set[str] = set()
    starts: list[str] = []
    ends: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    duplicate_count = 0
    row_count = 0
    for path in csv_files:
        for row in _read_csv_sample(path, max_rows=None):
            timestamp = str(row.get("timestamp") or row.get("datetime") or row.get("time") or "").strip()
            symbol = str(row.get("symbol") or _symbol_from_filename(path)).strip().upper()
            timeframe = str(row.get("timeframe") or _timeframe_from_filename(path)).strip().lower()
            if not timestamp or not symbol or not timeframe:
                continue
            key = (symbol, timeframe, timestamp)
            if key in seen:
                duplicate_count += 1
                continue
            seen.add(key)
            row_count += 1
            symbols.add(symbol)
            timeframes.add(timeframe)
            starts.append(timestamp)
            ends.append(timestamp)
    available = row_count > 0
    blockers = () if available else ("spot_ohlcv_missing",)
    quality = "ready_for_ohlcv_research" if available and duplicate_count == 0 else ("dedupe_required" if available else "missing")
    return DataCapability(
        capability_id="spot_ohlcv",
        available=available,
        source_paths=tuple(str(path) for path in csv_files[:50]),
        provider="kraken_public_ohlcv" if available else "unknown",
        symbols=tuple(sorted(symbols)),
        timeframes=tuple(sorted(timeframes)),
        start_at=min(starts) if starts else None,
        end_at=max(ends) if ends else None,
        row_count=row_count,
        duplicate_count=duplicate_count,
        storage_size_bytes=_storage_size(csv_files),
        freshness_seconds=_freshness_seconds(csv_files),
        quality_status=quality,
        alpha_families_unlocked=ALPHA_UNLOCKS["spot_ohlcv"] if available else (),
        blockers=blockers,
        notes=("csv_ohlcv_scan",),
    )


def _multi_symbol_ohlcv_capability(ohlcv: DataCapability) -> DataCapability:
    available = ohlcv.available and len(ohlcv.symbols) >= 2
    blockers = () if available else ("multi_symbol_ohlcv_missing",)
    return DataCapability(
        capability_id="multi_symbol_ohlcv",
        available=available,
        source_paths=ohlcv.source_paths,
        provider=ohlcv.provider,
        symbols=ohlcv.symbols,
        timeframes=ohlcv.timeframes,
        start_at=ohlcv.start_at,
        end_at=ohlcv.end_at,
        row_count=ohlcv.row_count,
        duplicate_count=ohlcv.duplicate_count,
        gap_count=ohlcv.gap_count,
        freshness_seconds=ohlcv.freshness_seconds,
        storage_size_bytes=ohlcv.storage_size_bytes,
        quality_status="ready_for_cross_sectional_research" if available else "missing",
        alpha_families_unlocked=ALPHA_UNLOCKS["multi_symbol_ohlcv"] if available else (),
        blockers=blockers,
        notes=("derived_from_spot_ohlcv",),
    )


def _scan_spread_depth(files: Sequence[Path]) -> dict[str, DataCapability]:
    csv_files = [path for path in files if path.suffix.lower() == ".csv" and _looks_like_spread_depth(path)]
    symbols: set[str] = set()
    starts: list[str] = []
    ends: list[str] = []
    row_count = 0
    has_depth = False
    has_spread = False
    for path in csv_files:
        for row in _read_csv_sample(path, max_rows=None):
            symbol = str(row.get("symbol") or _symbol_from_filename(path)).strip().upper()
            timestamp = str(row.get("timestamp_local") or row.get("timestamp") or row.get("time") or "").strip()
            if symbol:
                symbols.add(symbol)
            if timestamp:
                starts.append(timestamp)
                ends.append(timestamp)
            if row.get("spread_bps") not in (None, ""):
                has_spread = True
            if row.get("bid_depth_eur") not in (None, "") or row.get("ask_depth_eur") not in (None, ""):
                has_depth = True
            row_count += 1
    base = {
        "source_paths": tuple(str(path) for path in csv_files[:50]),
        "provider": "kraken_rest_public_depth" if csv_files else "unknown",
        "symbols": tuple(sorted(symbols)),
        "start_at": min(starts) if starts else None,
        "end_at": max(ends) if ends else None,
        "row_count": row_count,
        "storage_size_bytes": _storage_size(csv_files),
        "freshness_seconds": _freshness_seconds(csv_files),
    }
    return {
        "spread_history": DataCapability(
            capability_id="spread_history",
            available=has_spread,
            quality_status="sampled_public_top_of_book" if has_spread else "missing",
            alpha_families_unlocked=ALPHA_UNLOCKS["spread_history"] if has_spread else (),
            blockers=() if has_spread else ("spread_history_missing",),
            notes=("public_depth_snapshot_history",) if has_spread else (),
            **base,
        ),
        "orderbook_depth_snapshots": DataCapability(
            capability_id="orderbook_depth_snapshots",
            available=has_depth,
            quality_status="sampled_top_of_book_depth" if has_depth else "missing",
            alpha_families_unlocked=ALPHA_UNLOCKS["orderbook_depth_snapshots"] if has_depth else (),
            blockers=() if has_depth else ("orderbook_depth_missing",),
            notes=("top_of_book_depth_only_not_full_replay",) if has_depth else (),
            **base,
        ),
    }


def _scan_named_files(
    files: Sequence[Path],
    capability_id: str,
    needles: Sequence[str],
    *,
    provider: str = "unknown",
) -> DataCapability:
    matched = [path for path in files if any(needle in path.name.lower() for needle in needles)]
    # Cost profile docs/configs are enough for cost-awareness, but not market data.
    available = bool(matched)
    return DataCapability(
        capability_id=capability_id,
        available=available,
        source_paths=tuple(str(path) for path in matched[:50]),
        provider=provider if available else "unknown",
        row_count=_rough_csv_row_count(matched),
        storage_size_bytes=_storage_size(matched),
        freshness_seconds=_freshness_seconds(matched),
        quality_status="available_metadata" if available else "missing",
        alpha_families_unlocked=ALPHA_UNLOCKS[capability_id] if available else (),
        blockers=() if available else (f"{capability_id}_missing",),
        proxy_status="proxy_low_confidence" if capability_id in DERIVATIVES_CAPABILITIES and available else "not_proxy",
    )


def _derivatives_capabilities_from_manifest(manifest: Mapping[str, Any]) -> dict[str, DataCapability]:
    datasets = {
        str(item.get("dataset_id")): item
        for item in manifest.get("datasets", ())
        if isinstance(item, Mapping)
    }
    mapping_symbols = tuple(
        str(item.get("futures_symbol"))
        for item in manifest.get("mappings", ())
        if isinstance(item, Mapping) and item.get("futures_symbol")
    )
    mapping_bases = tuple(
        str(item.get("base_asset"))
        for item in manifest.get("mappings", ())
        if isinstance(item, Mapping) and item.get("base_asset")
    )
    source_paths = tuple(
        str(item.get("csv_path"))
        for item in datasets.values()
        if item.get("csv_path")
    )
    funding = datasets.get("funding_rates", {})
    tickers = datasets.get("ticker_snapshots", {})
    candles = datasets.get("derivatives_candles", {})
    basis = datasets.get("basis", {})
    funding_available = bool(manifest.get("funding_history_ready"))
    perp_available = bool(manifest.get("mark_candles_ready") or manifest.get("trade_candles_ready") or int(tickers.get("row_count") or 0) > 0)
    basis_history_ready = bool(manifest.get("basis_history_ready"))
    basis_current_ready = bool(manifest.get("basis_current_ready"))
    oi_history_ready = bool(manifest.get("open_interest_history_ready"))
    current_oi_ready = bool(manifest.get("current_open_interest_ready"))
    return {
        "funding_rates": DataCapability(
            capability_id="funding_rates",
            available=funding_available,
            source_paths=tuple(path for path in (funding.get("csv_path"), manifest.get("manifest_path")) if path),
            provider="kraken_futures_public",
            symbols=mapping_symbols,
            start_at=funding.get("start_at"),
            end_at=funding.get("end_at"),
            row_count=int(funding.get("row_count") or 0),
            duplicate_count=int(funding.get("duplicate_count") or 0),
            storage_size_bytes=int(funding.get("storage_size_bytes") or 0),
            freshness_seconds=_freshness_seconds(tuple(Path(path) for path in source_paths if path)),
            quality_status="historical_funding_ready" if funding_available else "missing",
            alpha_families_unlocked=ALPHA_UNLOCKS["funding_rates"] if funding_available else (),
            blockers=() if funding_available else ("funding_rates_missing",),
            proxy_status="not_proxy",
            notes=("kraken_futures_historical_funding_rates", f"snapshot_id={manifest.get('snapshot_id')}"),
        ),
        "futures_perp_prices": DataCapability(
            capability_id="futures_perp_prices",
            available=perp_available,
            source_paths=tuple(path for path in (tickers.get("csv_path"), candles.get("csv_path"), manifest.get("manifest_path")) if path),
            provider="kraken_futures_public",
            symbols=mapping_symbols,
            timeframes=("current", "1m") if perp_available else (),
            start_at=min(item for item in (tickers.get("start_at"), candles.get("start_at")) if item) if any((tickers.get("start_at"), candles.get("start_at"))) else None,
            end_at=max(item for item in (tickers.get("end_at"), candles.get("end_at")) if item) if any((tickers.get("end_at"), candles.get("end_at"))) else None,
            row_count=int(tickers.get("row_count") or 0) + int(candles.get("row_count") or 0),
            duplicate_count=int(tickers.get("duplicate_count") or 0) + int(candles.get("duplicate_count") or 0),
            storage_size_bytes=int(tickers.get("storage_size_bytes") or 0) + int(candles.get("storage_size_bytes") or 0),
            freshness_seconds=_freshness_seconds(tuple(Path(path) for path in source_paths if path)),
            quality_status="kraken_futures_perp_prices_ready" if perp_available else "missing",
            alpha_families_unlocked=ALPHA_UNLOCKS["futures_perp_prices"] if perp_available else (),
            blockers=() if perp_available else ("futures_perp_prices_missing",),
            proxy_status="not_proxy",
            notes=("mark_trade_spot_candles_or_ticker_snapshot", f"snapshot_id={manifest.get('snapshot_id')}"),
        ),
        "spot_perp_basis": DataCapability(
            capability_id="spot_perp_basis",
            available=basis_history_ready,
            source_paths=tuple(path for path in (basis.get("csv_path"), manifest.get("manifest_path")) if path),
            provider="kraken_futures_public",
            symbols=mapping_symbols,
            start_at=basis.get("start_at"),
            end_at=basis.get("end_at"),
            row_count=int(basis.get("row_count") or 0),
            duplicate_count=int(basis.get("duplicate_count") or 0),
            storage_size_bytes=int(basis.get("storage_size_bytes") or 0),
            freshness_seconds=_freshness_seconds(tuple(Path(path) for path in source_paths if path)),
            quality_status="basis_history_ready" if basis_history_ready else ("current_basis_only_waiting_for_history" if basis_current_ready else "missing"),
            alpha_families_unlocked=ALPHA_UNLOCKS["spot_perp_basis"] if basis_history_ready else (),
            blockers=() if basis_history_ready else (("basis_history_too_short",) if basis_current_ready else ("spot_perp_basis_missing",)),
            proxy_status="not_proxy",
            notes=(f"basis_confidence={manifest.get('basis_confidence_status')}", f"snapshot_id={manifest.get('snapshot_id')}"),
        ),
        "open_interest": DataCapability(
            capability_id="open_interest",
            available=oi_history_ready,
            source_paths=tuple(path for path in (tickers.get("csv_path"), manifest.get("manifest_path")) if path),
            provider="kraken_futures_public",
            symbols=mapping_symbols,
            start_at=tickers.get("start_at"),
            end_at=tickers.get("end_at"),
            row_count=int(tickers.get("row_count") or 0),
            duplicate_count=int(tickers.get("duplicate_count") or 0),
            storage_size_bytes=int(tickers.get("storage_size_bytes") or 0),
            freshness_seconds=_freshness_seconds(tuple(Path(path) for path in source_paths if path)),
            quality_status="open_interest_history_ready" if oi_history_ready else ("current_open_interest_only" if current_oi_ready else "missing"),
            alpha_families_unlocked=ALPHA_UNLOCKS["open_interest"] if oi_history_ready else (),
            blockers=() if oi_history_ready else (("open_interest_history_missing",) if current_oi_ready else ("open_interest_missing",)),
            proxy_status="not_proxy",
            notes=("current_open_interest_does_not_equal_history", f"base_assets={','.join(mapping_bases)}"),
        ),
    }


def _volume_anomaly_capability(ohlcv: DataCapability) -> DataCapability:
    available = ohlcv.available
    return DataCapability(
        capability_id="volume_anomalies",
        available=available,
        source_paths=ohlcv.source_paths,
        provider=ohlcv.provider,
        symbols=ohlcv.symbols,
        timeframes=ohlcv.timeframes,
        start_at=ohlcv.start_at,
        end_at=ohlcv.end_at,
        row_count=ohlcv.row_count,
        duplicate_count=ohlcv.duplicate_count,
        freshness_seconds=ohlcv.freshness_seconds,
        storage_size_bytes=ohlcv.storage_size_bytes,
        quality_status="derived_from_ohlcv_volume" if available else "missing",
        alpha_families_unlocked=ALPHA_UNLOCKS["volume_anomalies"] if available else (),
        blockers=() if available else ("ohlcv_volume_missing",),
        notes=("derived_feature_not_separate_feed",) if available else (),
    )


def _scan_slippage_fill_history(state_db: Path | None) -> DataCapability:
    if state_db is None or not state_db.exists():
        return DataCapability(
            capability_id="slippage_fill_history",
            available=False,
            blockers=("state_db_missing",),
            alpha_families_unlocked=(),
        )
    try:
        with sqlite3.connect(f"file:{state_db}?mode=ro", uri=True, timeout=5.0) as conn:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "trade_ledger" not in tables:
                return DataCapability(
                    capability_id="slippage_fill_history",
                    available=False,
                    source_paths=(str(state_db),),
                    blockers=("trade_ledger_missing",),
                )
            columns = {row[1] for row in conn.execute("PRAGMA table_info(trade_ledger)")}
            row_count = int(conn.execute("SELECT COUNT(*) FROM trade_ledger").fetchone()[0])
            has_slippage = "slippage" in columns or "slippage_bps" in columns
            has_fees = "fees" in columns or "fee" in columns or "fees_eur" in columns
    except sqlite3.Error as exc:
        return DataCapability(
            capability_id="slippage_fill_history",
            available=False,
            source_paths=(str(state_db),),
            blockers=(f"state_db_read_failed:{exc}",),
        )
    available = row_count > 0 and (has_slippage or has_fees)
    return DataCapability(
        capability_id="slippage_fill_history",
        available=available,
        source_paths=(str(state_db),),
        provider="autobot_trade_ledger",
        row_count=row_count,
        storage_size_bytes=state_db.stat().st_size,
        freshness_seconds=_freshness_seconds((state_db,)),
        quality_status="execution_history_available" if available else "ledger_without_cost_columns",
        alpha_families_unlocked=ALPHA_UNLOCKS["slippage_fill_history"] if available else (),
        blockers=() if available else ("slippage_or_fee_history_missing",),
        notes=("execution_history_not_market_alpha_source",),
    )


def _alpha_family_status(capability_by_id: Mapping[str, DataCapability]) -> dict[str, dict[str, Any]]:
    requirements = {
        "volatility_breakout": ("spot_ohlcv", "exchange_fees"),
        "long_trend": ("spot_ohlcv", "exchange_fees"),
        "cross_sectional_momentum": ("multi_symbol_ohlcv", "exchange_fees"),
        "relative_value": ("multi_symbol_ohlcv", "exchange_fees"),
        "funding_basis": ("spot_ohlcv", "funding_rates", "spot_perp_basis"),
        "liquidation_cascade": ("spot_ohlcv", "liquidation_events", "orderbook_depth_snapshots"),
        "order_flow_imbalance": ("orderbook_depth_snapshots", "spread_history"),
        "news_event_filter": ("news_sentiment",),
    }
    statuses: dict[str, dict[str, Any]] = {}
    for family, required in requirements.items():
        missing = [cap for cap in required if not capability_by_id[cap].available]
        available = [cap for cap in required if capability_by_id[cap].available]
        if family == "funding_basis" and "spot_perp_basis" in missing and capability_by_id["funding_rates"].available:
            status = "WAITING_FOR_MORE_DATA"
        elif missing:
            status = "DATA_MISSING"
        elif family in {"volatility_breakout", "long_trend", "cross_sectional_momentum", "relative_value"}:
            status = "DATA_AVAILABLE_BUT_CURRENT_CONFIG_REJECTED_OR_BENCHMARK"
        else:
            status = "DATA_AVAILABLE_RESEARCH_ONLY"
        notes = []
        if family in {"funding_basis", "liquidation_cascade"}:
            notes.append("do_not_run_until_real_derivatives_or_event_data_exists")
        if family == "order_flow_imbalance" and "orderbook_depth_snapshots" in available:
            notes.append("top_of_book_samples_are_not_full_orderbook_replay")
        blockers: list[str] = []
        for item in missing:
            capability_blockers = tuple(capability_by_id[item].blockers)
            blockers.extend(capability_blockers or (f"{item}_missing",))
        statuses[family] = {
            "status": status,
            "available_capabilities": available,
            "blockers": list(dict.fromkeys(blockers)),
            "notes": notes,
        }
    return statuses


def _rejected_family_status(memory_path: str | Path, capability_by_id: Mapping[str, DataCapability]) -> dict[str, dict[str, Any]]:
    memory = _load_memory(memory_path)
    rejected: set[str] = set()
    for record in memory.get("records", ()):
        status = str(record.get("final_status") or "").upper()
        if status in {"REJECT", "REJECTED", "REJECT_FAST", "REJECTED_CURRENT_CONFIG", "NO_GO", "RETIRED", "RETIRED_FROM_EXECUTION"}:
            rejected.add(str(record.get("hypothesis_id") or "unknown"))
            rejected.add(str(record.get("alpha_family_id") or "unknown"))
            rejected.update(str(item) for item in record.get("related_rejected_hypotheses", ()))
    current_signature = _data_signature(capability_by_id)
    status: dict[str, dict[str, Any]] = {}
    for family in sorted(item for item in rejected if item and item != "unknown"):
        retest_allowed = False
        reason = "blocked_until_new_data_signature_or_new_template"
        if family in {"funding_basis", "liquidation_cascade"}:
            reason = "blocked_by_missing_required_data"
        status[family] = {
            "status": "REJECTED_CURRENT_CONFIG",
            "retest_allowed": retest_allowed,
            "reason": reason,
            "current_data_signature": current_signature,
        }
    return status


def _build_ohlcv_backfill_plan(ohlcv: DataCapability) -> OHLCVBackfillPlan:
    multiplier = 0.0
    if ohlcv.start_at and ohlcv.end_at:
        multiplier = 365.0 / max(1.0, _coverage_days_from_isoish(ohlcv.start_at, ohlcv.end_at))
    symbols = ",".join(ohlcv.symbols) if ohlcv.symbols else "<active_symbols>"
    timeframes = ",".join(ohlcv.timeframes) if ohlcv.timeframes else "5m,15m,1h"
    commands = (
        "python -m autobot.v2.cli collect-history --run-id ohlcv_6m_bounded --symbols "
        f"{symbols} --timeframes {timeframes} --start-at <UTC_START_6M> --end-at <UTC_END> "
        "--max-pages <bounded_pages> --dedupe true --output-dir data/research/historical_long",
        "python -m autobot.v2.cli data-quality --run-id ohlcv_6m_quality --paths <deduped_csv_files> --output-dir reports/research/data_foundation",
        "python -m autobot.v2.cli data-capability-scan --state-db data/autobot_state.db --data-roots data/research,reports/research --output-dir reports/research",
    )
    return OHLCVBackfillPlan(
        current_start_at=ohlcv.start_at,
        current_end_at=ohlcv.end_at,
        current_row_count=ohlcv.row_count,
        current_symbols=ohlcv.symbols,
        current_timeframes=ohlcv.timeframes,
        bounded_commands=commands,
        estimated_storage_multiplier_for_12m=round(multiplier, 4),
        storage_policy_notes=(
            "Run as bounded batch only, never on each tick.",
            "Keep raw exports and write canonical deduped files with manifest.",
            "Do not retest rejected OHLCV hypotheses unless history grows significantly or a new template is introduced.",
        ),
    )


def _build_derivatives_plan(capability_by_id: Mapping[str, DataCapability]) -> tuple[DerivativesDataPlan, ...]:
    return (
        DerivativesDataPlan(
            data_type="funding_rates",
            required_for=("funding_basis",),
            potential_sources=("kraken_futures_public_if_supported", "ccxt_derivatives_public_if_supported", "paid_derivatives_data_vendor"),
            complexity="medium",
            estimated_storage="low",
            recommended_frequency="hourly_or_exchange_funding_interval",
            priority="high",
            current_status="AVAILABLE" if capability_by_id["funding_rates"].available else "DATA_MISSING",
            notes=("must be real funding feed, not inferred from spot OHLCV",),
        ),
        DerivativesDataPlan(
            data_type="perp_mark_index_basis",
            required_for=("funding_basis", "spot_perp_basis"),
            potential_sources=("kraken_futures_public_if_supported", "ccxt_derivatives_public_if_supported"),
            complexity="medium",
            estimated_storage="low_to_medium",
            recommended_frequency="5m_to_1h",
            priority="high",
            current_status="AVAILABLE" if capability_by_id["spot_perp_basis"].available else "DATA_MISSING",
            notes=("basis proxy from another venue must be marked proxy_low_confidence",),
        ),
        DerivativesDataPlan(
            data_type="open_interest",
            required_for=("funding_basis", "liquidation_cascade"),
            potential_sources=("kraken_futures_public_if_supported", "ccxt_derivatives_public_if_supported", "paid_derivatives_data_vendor"),
            complexity="medium",
            estimated_storage="low",
            recommended_frequency="15m_to_1h",
            priority="medium",
            current_status="AVAILABLE" if capability_by_id["open_interest"].available else "DATA_MISSING",
            notes=("use as context, not direct alpha without event validation",),
        ),
        DerivativesDataPlan(
            data_type="liquidation_events",
            required_for=("liquidation_cascade",),
            potential_sources=("paid_liquidation_feed", "exchange_public_if_available"),
            complexity="high",
            estimated_storage="medium",
            recommended_frequency="1m_to_5m_or_event_stream",
            priority="medium",
            current_status="AVAILABLE" if capability_by_id["liquidation_events"].available else "DATA_MISSING",
            notes=("do not create weak OHLCV liquidation proxy except proxy_low_confidence",),
        ),
    )


def _scheduler_data_state(
    roots: Sequence[Path],
    capability_by_id: Mapping[str, DataCapability],
    alpha_status: Mapping[str, Mapping[str, Any]],
    canonical_manifest: Mapping[str, Any] | None = None,
    derivatives_manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    manifest = dict(canonical_manifest or _latest_canonical_ohlcv_manifest(roots) or {})
    final_duplicate_count = sum(
        int(item.get("duplicate_count") or 0)
        for item in manifest.get("files", ())
        if isinstance(item, Mapping)
    )
    canonical_ready = bool(
        manifest
        and int(manifest.get("canonical_row_count") or 0) > 0
        and final_duplicate_count == 0
    )
    unlocked = [
        family
        for family, payload in alpha_status.items()
        if not payload.get("blockers")
        and payload.get("status") not in {"DATA_MISSING"}
    ]
    still_blocked = [
        family
        for family, payload in alpha_status.items()
        if payload.get("blockers") or payload.get("status") == "DATA_MISSING"
    ]
    derivatives = dict(derivatives_manifest or _latest_kraken_futures_derivatives_manifest(roots) or {})
    return {
        "canonical_ohlcv_ready": canonical_ready,
        "snapshot_id": manifest.get("snapshot_id") if manifest else None,
        "snapshot_fingerprint": manifest.get("fingerprint") if manifest else None,
        "new_data_significance": manifest.get("new_data_significance") if manifest else "no_canonical_snapshot",
        "funding_data_ready": capability_by_id["funding_rates"].available,
        "funding_history_ready": bool(derivatives.get("funding_history_ready")),
        "funding_history_start": derivatives.get("funding_history_start"),
        "funding_history_end": derivatives.get("funding_history_end"),
        "mark_candles_ready": bool(derivatives.get("mark_candles_ready")),
        "trade_candles_ready": bool(derivatives.get("trade_candles_ready")),
        "basis_data_ready": capability_by_id["spot_perp_basis"].available,
        "basis_history_ready": bool(derivatives.get("basis_history_ready")),
        "current_open_interest_ready": bool(derivatives.get("current_open_interest_ready")),
        "open_interest_ready": capability_by_id["open_interest"].available,
        "open_interest_history_ready": bool(derivatives.get("open_interest_history_ready")),
        "predicted_funding_ready": bool(derivatives.get("predicted_funding_ready")),
        "derivatives_symbols_ready": bool(derivatives.get("mappings")),
        "derivatives_snapshot_id": derivatives.get("snapshot_id"),
        "derivatives_data_quality": derivatives.get("derivatives_data_quality") if derivatives else "missing",
        "liquidation_data_ready": capability_by_id["liquidation_events"].available,
        "hypotheses_unlocked": sorted(unlocked),
        "hypotheses_still_blocked": sorted(still_blocked),
    }


def _storage_policy() -> ResearchStoragePolicy:
    return ResearchStoragePolicy(
        raw_data="Store provider-native exports under data/research/raw/<provider>/<capability>/ with immutable manifests.",
        canonical_data="Write normalized symbol/timeframe datasets under data/research/canonical/ with schema/version metadata.",
        deduped_data="Use symbol+timeframe+timestamp unique keys; deduped files are the only source for runner inputs.",
        manifests="Each run writes row counts, duplicate counts, gaps, source provider, start/end and checksum where practical.",
        retention="Keep critical ledgers, reports and manifests indefinitely; rotate raw high-frequency snapshots only after canonical verification.",
        compression="Prefer Parquet or compressed CSV for long OHLCV/orderbook history when dependencies are available.",
        safe_cleanup=("__pycache__", ".pytest_cache", "temporary smoke configs", "Docker build cache"),
        protected_paths=("data/autobot_state.db", "data/paper_trades.db", "reports/research", "reports/non_regression", "backups", "trade ledgers"),
    )


def _scheduler_notes(
    alpha_status: Mapping[str, Mapping[str, Any]],
    rejected_status: Mapping[str, Mapping[str, Any]],
    scheduler_data_state: Mapping[str, Any],
) -> tuple[str, ...]:
    notes = [
        "Do not relaunch rejected OHLCV templates solely because this scanner exists.",
        "Relaunch requires significant new data, a new historical period, a new thesis, or a genuinely different template.",
    ]
    if not scheduler_data_state.get("canonical_ohlcv_ready"):
        notes.append("canonical_ohlcv_ready is false until a deduped canonical snapshot exists.")
    elif scheduler_data_state.get("new_data_significance") in {"same_data", "minor_addition"}:
        notes.append("Existing rejections stay blocked because canonical data is unchanged or only a minor addition.")
    runnable = [
        family
        for family, payload in alpha_status.items()
        if not payload.get("blockers") and family not in rejected_status
    ]
    if not runnable:
        notes.append("No currently runnable non-rejected hypothesis is unlocked by existing data.")
    if alpha_status.get("funding_basis", {}).get("blockers"):
        notes.append("funding_basis blocked until funding, basis/perp and validated provider data exist.")
    if alpha_status.get("liquidation_cascade", {}).get("blockers"):
        notes.append("liquidation_cascade blocked until liquidation events and sufficient depth data exist.")
    if alpha_status.get("order_flow_imbalance", {}).get("blockers"):
        notes.append("order_flow_imbalance blocked until depth/spread history is sufficient for replay, not only sparse samples.")
    return tuple(notes)


def _latest_canonical_ohlcv_manifest(roots: Sequence[Path]) -> dict[str, Any] | None:
    candidates: list[Path] = []
    for root in roots:
        search_roots = [root]
        if root.name != "manifests":
            search_roots.extend(
                candidate
                for candidate in (root / "manifests", root.parent / "manifests")
                if candidate.exists()
            )
        for search_root in search_roots:
            if search_root.is_file() and "ohlcv" in search_root.name.lower() and search_root.suffix.lower() == ".json":
                candidates.append(search_root)
            elif search_root.exists():
                candidates.extend(search_root.rglob("*canonical_ohlcv*.json"))
                candidates.extend(search_root.rglob("*ohlcv*.json"))
    unique = sorted(set(candidates), key=lambda item: item.stat().st_mtime if item.exists() else 0, reverse=True)
    for path in unique:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("snapshot_id") and payload.get("fingerprint"):
            return payload
    return None


def _latest_kraken_futures_derivatives_manifest(roots: Sequence[Path]) -> dict[str, Any] | None:
    candidates: list[Path] = []
    for root in roots:
        search_roots = [root]
        if root.name != "manifests":
            search_roots.extend(
                candidate
                for candidate in (root / "manifests", root.parent / "manifests")
                if candidate.exists()
            )
        for search_root in search_roots:
            if search_root.is_file() and "kraken_futures_derivatives" in search_root.name.lower() and search_root.suffix.lower() == ".json":
                candidates.append(search_root)
            elif search_root.exists():
                candidates.extend(search_root.rglob("*kraken_futures_derivatives*.json"))
    unique = sorted(set(candidates), key=lambda item: item.stat().st_mtime if item.exists() else 0, reverse=True)
    for path in unique:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("snapshot_id") and payload.get("fingerprint") and payload.get("mappings") is not None:
            return payload
    return None


def _files_under(roots: Iterable[Path]) -> tuple[Path, ...]:
    files: list[Path] = []
    for root in roots:
        if root.is_file():
            files.append(root)
        elif root.exists():
            files.extend(path for path in root.rglob("*") if path.is_file())
    return tuple(files)


def _read_csv_sample(path: Path, *, max_rows: int | None) -> Iterable[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for index, row in enumerate(reader):
                if max_rows is not None and index >= max_rows:
                    break
                yield row
    except (OSError, UnicodeDecodeError, csv.Error):
        return


def _looks_like_ohlcv(path: Path) -> bool:
    name = str(path).lower()
    if any(token in name for token in ("spread_depth", "microstructure", "decision", "ledger")):
        return False
    if any(token in name for token in ("ohlcv", "kraken_")):
        return True
    for row in _read_csv_sample(path, max_rows=1):
        fields = set(row)
        return {"open", "high", "low", "close"}.issubset(fields)
    return False


def _looks_like_spread_depth(path: Path) -> bool:
    name = str(path).lower()
    if "spread_depth" in name or "microstructure" in name:
        return True
    for row in _read_csv_sample(path, max_rows=1):
        fields = set(row)
        return "spread_bps" in fields or {"best_bid", "best_ask"}.issubset(fields)
    return False


def _symbol_from_filename(path: Path) -> str:
    stem = path.stem.upper()
    for part in stem.replace("-", "_").split("_"):
        if part.endswith("EUR") and len(part) >= 6:
            return part
    return "UNKNOWN"


def _timeframe_from_filename(path: Path) -> str:
    stem = path.stem.lower()
    for token in ("1m", "5m", "15m", "1h", "4h", "1d"):
        if token in stem.replace("-", "_").split("_") or f"_{token}" in stem:
            return token
    return "unknown"


def _rough_csv_row_count(files: Sequence[Path]) -> int:
    total = 0
    for path in files:
        if path.suffix.lower() != ".csv":
            continue
        try:
            with path.open("r", encoding="utf-8") as handle:
                total += max(0, sum(1 for _ in handle) - 1)
        except OSError:
            continue
    return total


def _storage_size(files: Sequence[Path]) -> int:
    total = 0
    for path in files:
        try:
            total += path.stat().st_size
        except OSError:
            continue
    return total


def _freshness_seconds(files: Sequence[Path]) -> float | None:
    mtimes = []
    for path in files:
        try:
            mtimes.append(path.stat().st_mtime)
        except OSError:
            continue
    if not mtimes:
        return None
    return max(0.0, datetime.now(timezone.utc).timestamp() - max(mtimes))


def _coverage_days_from_isoish(start_at: str, end_at: str) -> float:
    start = _parse_dt(start_at)
    end = _parse_dt(end_at)
    if start is None or end is None:
        return 0.0
    return max(0.0, (end - start).total_seconds() / 86_400.0)


def _parse_dt(value: str) -> datetime | None:
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _data_signature(capability_by_id: Mapping[str, DataCapability]) -> dict[str, Any]:
    ohlcv = capability_by_id["spot_ohlcv"]
    return {
        "ohlcv_start_at": ohlcv.start_at,
        "ohlcv_end_at": ohlcv.end_at,
        "ohlcv_row_count": ohlcv.row_count,
        "symbols": list(ohlcv.symbols),
        "timeframes": list(ohlcv.timeframes),
        "funding_available": capability_by_id["funding_rates"].available,
        "liquidations_available": capability_by_id["liquidation_events"].available,
        "depth_available": capability_by_id["orderbook_depth_snapshots"].available,
    }


def _load_memory(memory_path: str | Path) -> dict[str, Any]:
    path = Path(memory_path)
    if not path.exists():
        return {"records": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"records": []}
