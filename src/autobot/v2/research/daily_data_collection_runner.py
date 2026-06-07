"""Daily research-data collection runner for AUTOBOT.

This runner orchestrates public OHLCV and public spread/depth collection. It is
deliberately isolated from paper/live runtime and cannot create orders.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .data_readiness_dashboard import build_data_readiness_dashboard, write_data_readiness_dashboard
from .historical_data_collector import (
    HistoricalDataCollectionResult,
    HistoricalDataCollectorConfig,
    OHLCFetcher,
    collect_historical_ohlcv,
)
from .microstructure_profile import build_microstructure_profile, write_microstructure_profile_report
from .spread_depth_recorder import (
    DepthFetcher,
    SpreadDepthRecorderConfig,
    SpreadDepthRecorderResult,
    record_spread_depth,
)


@dataclass(frozen=True)
class DailyResearchOutputDirs:
    ohlcv: Path
    microstructure: Path
    reports: Path


@dataclass(frozen=True)
class DailyResearchSafetyConfig:
    public_endpoints_only: bool
    no_private_keys: bool
    no_orders: bool
    research_only: bool

    def validate(self) -> None:
        if not self.public_endpoints_only:
            raise ValueError("safety.public_endpoints_only must be true")
        if not self.no_private_keys:
            raise ValueError("safety.no_private_keys must be true")
        if not self.no_orders:
            raise ValueError("safety.no_orders must be true")
        if not self.research_only:
            raise ValueError("safety.research_only must be true")


@dataclass(frozen=True)
class DailyResearchDataCollectionConfig:
    priority_symbols: tuple[str, ...]
    secondary_symbols: tuple[str, ...]
    timeframes: tuple[str, ...]
    output_dirs: DailyResearchOutputDirs
    safety: DailyResearchSafetyConfig
    ohlcv_max_pages: int = 5
    ohlcv_dedupe: bool = True
    ohlcv_fail_on_gaps: bool = False
    ohlcv_export_csv: bool = True
    ohlcv_export_parquet: bool = False
    microstructure_depth_count: int = 10
    microstructure_sample_interval_seconds: float = 60.0
    microstructure_samples_per_run: int = 60

    @property
    def all_symbols(self) -> tuple[str, ...]:
        values: list[str] = []
        for symbol in (*self.priority_symbols, *self.secondary_symbols):
            normalized = str(symbol).strip().upper()
            if normalized and normalized not in values:
                values.append(normalized)
        return tuple(values)

    def validate(self) -> None:
        self.safety.validate()
        if not self.priority_symbols:
            raise ValueError("priority_symbols must not be empty")
        if not self.timeframes:
            raise ValueError("timeframes must not be empty")
        if self.ohlcv_max_pages <= 0:
            raise ValueError("ohlcv.max_pages must be positive")
        if self.microstructure_depth_count <= 0:
            raise ValueError("microstructure.depth_count must be positive")
        if self.microstructure_samples_per_run <= 0:
            raise ValueError("microstructure.samples_per_run must be positive")
        if self.microstructure_sample_interval_seconds < 0.0:
            raise ValueError("microstructure.sample_interval_seconds cannot be negative")


@dataclass(frozen=True)
class DailyCollectionOperation:
    operation_type: str
    symbol: str | None
    timeframe: str | None
    status: str
    row_count: int = 0
    duplicate_count: int = 0
    gap_count: int = 0
    output_path: str | None = None
    manifest_path: str | None = None
    markdown_report_path: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DailyResearchDataCollectionResult:
    run_id: str
    generated_at: str
    config_path: str
    operations: tuple[DailyCollectionOperation, ...]
    microstructure_result: dict[str, Any] | None
    microstructure_profile_path: str | None
    data_readiness_dashboard_path: str | None
    manifest_path: str | None = None
    markdown_report_path: str | None = None
    live_promotion_allowed: bool = False
    safety_notes: tuple[str, ...] = (
        "Daily research collection is research-only.",
        "Public market-data endpoints only.",
        "No API key is read or exposed.",
        "No paper or live order is created.",
        "No runtime paper/live service is started or modified.",
        "No live trading permission is granted.",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "config_path": self.config_path,
            "operations": [item.to_dict() for item in self.operations],
            "microstructure_result": self.microstructure_result,
            "microstructure_profile_path": self.microstructure_profile_path,
            "data_readiness_dashboard_path": self.data_readiness_dashboard_path,
            "manifest_path": self.manifest_path,
            "markdown_report_path": self.markdown_report_path,
            "live_promotion_allowed": self.live_promotion_allowed,
            "safety_notes": list(self.safety_notes),
        }


def load_daily_research_data_collection_config(path: str | Path) -> DailyResearchDataCollectionConfig:
    payload = _load_yaml_mapping(path)
    output_dirs = payload.get("output_dirs") or {}
    safety = payload.get("safety") or {}
    ohlcv = payload.get("ohlcv") or {}
    microstructure = payload.get("microstructure") or {}
    config = DailyResearchDataCollectionConfig(
        priority_symbols=_tuple_upper(payload.get("priority_symbols")),
        secondary_symbols=_tuple_upper(payload.get("secondary_symbols")),
        timeframes=_tuple_text(payload.get("timeframes")),
        output_dirs=DailyResearchOutputDirs(
            ohlcv=Path(str(output_dirs.get("ohlcv") or "data/research/daily/ohlcv")),
            microstructure=Path(str(output_dirs.get("microstructure") or "data/research/daily/microstructure")),
            reports=Path(str(output_dirs.get("reports") or "reports/research/daily_data_collection")),
        ),
        safety=DailyResearchSafetyConfig(
            public_endpoints_only=bool(safety.get("public_endpoints_only")),
            no_private_keys=bool(safety.get("no_private_keys")),
            no_orders=bool(safety.get("no_orders")),
            research_only=bool(safety.get("research_only")),
        ),
        ohlcv_max_pages=int(ohlcv.get("max_pages") or 5),
        ohlcv_dedupe=bool(ohlcv.get("dedupe", True)),
        ohlcv_fail_on_gaps=bool(ohlcv.get("fail_on_gaps", False)),
        ohlcv_export_csv=bool(ohlcv.get("export_csv", True)),
        ohlcv_export_parquet=bool(ohlcv.get("export_parquet", False)),
        microstructure_depth_count=int(microstructure.get("depth_count") or 10),
        microstructure_sample_interval_seconds=float(microstructure.get("sample_interval_seconds") or 60.0),
        microstructure_samples_per_run=int(microstructure.get("samples_per_run") or 60),
    )
    config.validate()
    return config


def run_daily_research_data_collection(
    *,
    config_path: str | Path,
    run_id: str,
    ohlc_fetcher: OHLCFetcher | None = None,
    depth_fetcher: DepthFetcher | None = None,
) -> DailyResearchDataCollectionResult:
    config = load_daily_research_data_collection_config(config_path)
    run_report_dir = config.output_dirs.reports / run_id
    run_ohlcv_dir = config.output_dirs.ohlcv / run_id
    run_micro_dir = config.output_dirs.microstructure / run_id
    run_report_dir.mkdir(parents=True, exist_ok=True)
    operations: list[DailyCollectionOperation] = []
    ohlcv_csv_paths: list[str] = []

    for symbol in config.all_symbols:
        for timeframe in config.timeframes:
            op = _collect_one_ohlcv(
                run_id=run_id,
                symbol=symbol,
                timeframe=timeframe,
                output_dir=run_ohlcv_dir,
                config=config,
                fetcher=ohlc_fetcher,
            )
            operations.append(op)
            if op.status == "ok" and op.output_path:
                ohlcv_csv_paths.append(op.output_path)

    micro_result: SpreadDepthRecorderResult | None = None
    micro_profile_path: str | None = None
    try:
        micro_result = record_spread_depth(
            SpreadDepthRecorderConfig(
                run_id=f"{run_id}_spread_depth",
                symbols=config.all_symbols,
                output_dir=run_micro_dir,
                depth_count=config.microstructure_depth_count,
                samples=config.microstructure_samples_per_run,
                sleep_seconds=config.microstructure_sample_interval_seconds,
                export_csv=True,
                continue_on_error=True,
            ),
            fetcher=depth_fetcher,
        )
        operations.append(
            DailyCollectionOperation(
                operation_type="spread_depth",
                symbol=None,
                timeframe=None,
                status="ok" if not micro_result.errors else "partial",
                row_count=len(micro_result.snapshots),
                output_path=micro_result.csv_path,
                markdown_report_path=micro_result.markdown_report_path,
                error=f"{len(micro_result.errors)} public depth errors" if micro_result.errors else None,
            )
        )
    except Exception as exc:
        operations.append(
            DailyCollectionOperation(
                operation_type="spread_depth",
                symbol=None,
                timeframe=None,
                status="error",
                error=str(exc),
            )
        )

    profiles = ()
    if micro_result and micro_result.csv_path:
        profile_report = write_microstructure_profile_report(
            build_microstructure_profile((micro_result.csv_path,), run_id=f"{run_id}_microstructure_profile"),
            run_report_dir,
        )
        profiles = profile_report.profiles
        micro_profile_path = profile_report.markdown_report_path

    dashboard_path = None
    if ohlcv_csv_paths:
        dashboard = write_data_readiness_dashboard(
            build_data_readiness_dashboard(
                run_id=run_id,
                dataset_paths=ohlcv_csv_paths,
                microstructure_profiles=profiles,
            ),
            run_report_dir,
        )
        dashboard_path = dashboard.markdown_report_path

    result = DailyResearchDataCollectionResult(
        run_id=run_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        config_path=str(Path(config_path)),
        operations=tuple(operations),
        microstructure_result=micro_result.to_dict() if micro_result else None,
        microstructure_profile_path=micro_profile_path,
        data_readiness_dashboard_path=dashboard_path,
    )
    return write_daily_research_data_collection_report(result, run_report_dir)


def write_daily_research_data_collection_report(
    result: DailyResearchDataCollectionResult,
    output_dir: str | Path,
) -> DailyResearchDataCollectionResult:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    manifest_path = output_path / f"{result.run_id}_daily_collection_manifest.json"
    markdown_path = output_path / f"{result.run_id}_daily_collection.md"
    manifest_path.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(render_daily_research_data_collection_report(result), encoding="utf-8")
    return DailyResearchDataCollectionResult(
        run_id=result.run_id,
        generated_at=result.generated_at,
        config_path=result.config_path,
        operations=result.operations,
        microstructure_result=result.microstructure_result,
        microstructure_profile_path=result.microstructure_profile_path,
        data_readiness_dashboard_path=result.data_readiness_dashboard_path,
        manifest_path=str(manifest_path),
        markdown_report_path=str(markdown_path),
        live_promotion_allowed=result.live_promotion_allowed,
        safety_notes=result.safety_notes,
    )


def render_daily_research_data_collection_report(result: DailyResearchDataCollectionResult) -> str:
    lines = [
        f"# Daily Research Data Collection - {result.run_id}",
        "",
        f"Generated at: `{result.generated_at}`",
        f"Config: `{result.config_path}`",
        f"Live promotion allowed: `{result.live_promotion_allowed}`",
        "",
        "## Operations",
        "",
        "| Type | Symbol | Timeframe | Status | Rows | Duplicates | Gaps | Output | Error |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | --- | --- |",
    ]
    for op in result.operations:
        lines.append(
            f"| {op.operation_type} | {op.symbol or '-'} | {op.timeframe or '-'} | {op.status} | "
            f"{op.row_count} | {op.duplicate_count} | {op.gap_count} | {op.output_path or op.markdown_report_path or '-'} | "
            f"{op.error or '-'} |"
        )
    lines.extend(
        [
            "",
            "## Derived Reports",
            "",
            f"- Microstructure profile: `{result.microstructure_profile_path or 'not generated'}`",
            f"- Data readiness dashboard: `{result.data_readiness_dashboard_path or 'not generated'}`",
            "",
            "## Safety",
            "",
        ]
    )
    lines.extend(f"- {note}" for note in result.safety_notes)
    lines.append("")
    return "\n".join(lines)


def _collect_one_ohlcv(
    *,
    run_id: str,
    symbol: str,
    timeframe: str,
    output_dir: Path,
    config: DailyResearchDataCollectionConfig,
    fetcher: OHLCFetcher | None,
) -> DailyCollectionOperation:
    try:
        result = collect_historical_ohlcv(
            HistoricalDataCollectorConfig(
                run_id=f"{run_id}_{symbol}_{timeframe}",
                symbols=(symbol,),
                timeframes=(timeframe,),
                output_dir=output_dir,
                max_pages=config.ohlcv_max_pages,
                dedupe=config.ohlcv_dedupe,
                fail_on_gaps=config.ohlcv_fail_on_gaps,
                export_csv=config.ohlcv_export_csv,
                export_parquet=config.ohlcv_export_parquet,
            ),
            fetcher=fetcher,
        )
    except Exception as exc:
        return DailyCollectionOperation(
            operation_type="ohlcv",
            symbol=symbol,
            timeframe=timeframe,
            status="error",
            error=str(exc),
        )
    return _operation_from_ohlcv_result(result, symbol=symbol, timeframe=timeframe)


def _operation_from_ohlcv_result(
    result: HistoricalDataCollectionResult,
    *,
    symbol: str,
    timeframe: str,
) -> DailyCollectionOperation:
    item = result.files[0] if result.files else None
    quality = result.readiness.files[0] if result.readiness.files else None
    return DailyCollectionOperation(
        operation_type="ohlcv",
        symbol=symbol,
        timeframe=timeframe,
        status="ok",
        row_count=item.row_count if item else 0,
        duplicate_count=item.duplicate_count if item else 0,
        gap_count=quality.gap_count if quality else 0,
        output_path=item.csv_path if item else None,
        manifest_path=result.manifest_path,
        markdown_report_path=result.markdown_report_path,
        error=", ".join(item.warnings) if item and item.warnings else None,
    )


def _load_yaml_mapping(path: str | Path) -> Mapping[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise RuntimeError("PyYAML is required to read research data collection YAML config") from exc
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("research data collection config must be a YAML mapping")
    return payload


def _tuple_upper(value: Any) -> tuple[str, ...]:
    return tuple(str(item).strip().upper() for item in (value or ()) if str(item).strip())


def _tuple_text(value: Any) -> tuple[str, ...]:
    return tuple(str(item).strip() for item in (value or ()) if str(item).strip())
