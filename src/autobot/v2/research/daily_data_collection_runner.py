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
from .kraken_symbol_mapping import (
    AssetPairsFetcher,
    KrakenPublicPairMapping,
    KrakenSymbolPreflight,
    detect_active_autobot_symbols,
    preflight_kraken_public_symbols,
)
from .microstructure_profile import build_microstructure_profile, write_microstructure_profile_report
from .spread_depth_recorder import (
    DepthFetcher,
    SpreadDepthRecorderConfig,
    SpreadDepthRecorderResult,
    record_spread_depth,
)
from .symbol_normalization import normalize_research_symbol


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
class DailyHighConvictionWalkForwardConfig:
    enabled: bool = False
    output_dir: Path = Path("reports/research/high_conviction_walk_forward")
    train_window_bars: int = 288
    test_window_bars: int = 192
    step_window_bars: int | None = None
    min_folds: int = 3
    min_positive_fold_ratio: float = 0.60
    min_closed_trades_for_review: int = 50
    min_expected_move_bps: float = 500.0
    risk_reward_ratio: float = 2.0
    max_hold_hours: float = 72.0
    exit_modes: tuple[str, ...] = ("fixed_tp_sl", "trailing")
    primary_exit_mode: str = "fixed_tp_sl"

    def validate(self) -> None:
        if not self.enabled:
            return
        if self.train_window_bars <= 0 or self.test_window_bars <= 0 or self.min_folds < 1:
            raise ValueError("high_conviction_walk_forward windows and folds must be positive")
        if self.step_window_bars is not None and self.step_window_bars <= 0:
            raise ValueError("high_conviction_walk_forward.step_window_bars must be positive")
        if self.min_closed_trades_for_review < 50:
            raise ValueError("high_conviction_walk_forward requires at least 50 closed trades for review")
        if not self.exit_modes or self.primary_exit_mode not in self.exit_modes:
            raise ValueError("high_conviction_walk_forward.primary_exit_mode must be one of exit_modes")


@dataclass(frozen=True)
class DailyStrategyOrchestratorConfig:
    """Configuration for the isolated multi-strategy treasury report."""

    enabled: bool = False
    output_dir: Path = Path("reports/research/strategy_orchestrator")
    instance_id: str = "research-parent-001"
    initial_treasury_eur: float = 500.0
    max_instance_exposure_pct: float = 0.60
    max_strategy_exposure_pct: float = 0.50
    max_symbol_exposure_pct: float = 0.20
    max_open_positions: int = 3
    cooldown_hours: float = 6.0
    max_daily_loss_pct: float = 0.03
    max_drawdown_pct: float = 0.10
    min_research_meta_score: float = 20.0
    signal_history_bars: int = 384

    def validate(self) -> None:
        if not self.enabled:
            return
        if not self.instance_id.strip() or self.initial_treasury_eur <= 0.0:
            raise ValueError("strategy_orchestrator requires an instance id and positive treasury")
        if self.max_open_positions < 1 or self.signal_history_bars < 24:
            raise ValueError("strategy_orchestrator limits are invalid")
        for value in (
            self.max_instance_exposure_pct,
            self.max_strategy_exposure_pct,
            self.max_symbol_exposure_pct,
            self.max_daily_loss_pct,
            self.max_drawdown_pct,
        ):
            if not 0.0 < value <= 1.0:
                raise ValueError("strategy_orchestrator risk limits must be in (0, 1]")


@dataclass(frozen=True)
class DailyStrategyEdgeReviewConfig:
    """Configuration for the isolated strategy edge review report."""

    enabled: bool = False
    output_dir: Path = Path("reports/research")
    min_candidate_trades: int = 50
    min_candidate_pf: float = 1.30
    high_quality_pf: float = 1.50
    max_drawdown_pct: float = 10.0
    max_single_symbol_positive_share: float = 0.40

    def validate(self) -> None:
        if not self.enabled:
            return
        if self.min_candidate_trades <= 0:
            raise ValueError("strategy_edge_review.min_candidate_trades must be positive")
        for value in (self.min_candidate_pf, self.high_quality_pf, self.max_drawdown_pct):
            if value <= 0.0:
                raise ValueError("strategy_edge_review thresholds must be positive")
        if not 0.0 < self.max_single_symbol_positive_share <= 1.0:
            raise ValueError("strategy_edge_review.max_single_symbol_positive_share must be in (0, 1]")


@dataclass(frozen=True)
class DailyResearchDataCollectionConfig:
    priority_symbols: tuple[str, ...]
    secondary_symbols: tuple[str, ...]
    timeframes: tuple[str, ...]
    output_dirs: DailyResearchOutputDirs
    safety: DailyResearchSafetyConfig
    include_runtime_active_symbols: bool = False
    ohlcv_max_pages: int = 5
    ohlcv_dedupe: bool = True
    ohlcv_fail_on_gaps: bool = False
    ohlcv_export_csv: bool = True
    ohlcv_export_parquet: bool = False
    microstructure_depth_count: int = 10
    microstructure_sample_interval_seconds: float = 60.0
    microstructure_samples_per_run: int = 60
    high_conviction_walk_forward: DailyHighConvictionWalkForwardConfig = DailyHighConvictionWalkForwardConfig()
    strategy_orchestrator: DailyStrategyOrchestratorConfig = DailyStrategyOrchestratorConfig()
    strategy_edge_review: DailyStrategyEdgeReviewConfig = DailyStrategyEdgeReviewConfig()

    @property
    def all_symbols(self) -> tuple[str, ...]:
        values: list[str] = []
        if self.include_runtime_active_symbols:
            values.extend(detect_active_autobot_symbols())
        for symbol in (*self.priority_symbols, *self.secondary_symbols):
            normalized = normalize_research_symbol(symbol)
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
        self.high_conviction_walk_forward.validate()
        self.strategy_orchestrator.validate()
        self.strategy_edge_review.validate()


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
    high_conviction_walk_forward_report_path: str | None = None
    strategy_orchestrator_report_path: str | None = None
    strategy_edge_review_report_path: str | None = None
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
            "high_conviction_walk_forward_report_path": self.high_conviction_walk_forward_report_path,
            "strategy_orchestrator_report_path": self.strategy_orchestrator_report_path,
            "strategy_edge_review_report_path": self.strategy_edge_review_report_path,
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
    high_conviction = payload.get("high_conviction_walk_forward") or {}
    strategy_orchestrator = payload.get("strategy_orchestrator") or {}
    strategy_edge_review = payload.get("strategy_edge_review") or {}
    config = DailyResearchDataCollectionConfig(
        priority_symbols=_tuple_upper(payload.get("priority_symbols")),
        secondary_symbols=_tuple_upper(payload.get("secondary_symbols")),
        timeframes=_tuple_text(payload.get("timeframes")),
        output_dirs=DailyResearchOutputDirs(
            ohlcv=Path(str(output_dirs.get("ohlcv") or "data/research/daily/ohlcv")),
            microstructure=Path(str(output_dirs.get("microstructure") or "data/research/daily/microstructure")),
            reports=Path(str(output_dirs.get("reports") or "reports/research/daily_data_collection")),
        ),
        include_runtime_active_symbols=bool(payload.get("include_runtime_active_symbols", False)),
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
        high_conviction_walk_forward=DailyHighConvictionWalkForwardConfig(
            enabled=bool(high_conviction.get("enabled", False)),
            output_dir=Path(str(high_conviction.get("output_dir") or "reports/research/high_conviction_walk_forward")),
            train_window_bars=int(high_conviction.get("train_window_bars") or 288),
            test_window_bars=int(high_conviction.get("test_window_bars") or 192),
            step_window_bars=(int(high_conviction["step_window_bars"]) if high_conviction.get("step_window_bars") not in (None, "") else None),
            min_folds=int(high_conviction.get("min_folds") or 3),
            min_positive_fold_ratio=float(high_conviction.get("min_positive_fold_ratio") or 0.60),
            min_closed_trades_for_review=int(high_conviction.get("min_closed_trades_for_review") or 50),
            min_expected_move_bps=float(high_conviction.get("min_expected_move_bps") or 500.0),
            risk_reward_ratio=float(high_conviction.get("risk_reward_ratio") or 2.0),
            max_hold_hours=float(high_conviction.get("max_hold_hours") or 72.0),
            exit_modes=_tuple_text(high_conviction.get("exit_modes") or ("fixed_tp_sl", "trailing")),
            primary_exit_mode=str(high_conviction.get("primary_exit_mode") or "fixed_tp_sl"),
        ),
        strategy_orchestrator=DailyStrategyOrchestratorConfig(
            enabled=bool(strategy_orchestrator.get("enabled", False)),
            output_dir=Path(str(strategy_orchestrator.get("output_dir") or "reports/research/strategy_orchestrator")),
            instance_id=str(strategy_orchestrator.get("instance_id") or "research-parent-001"),
            initial_treasury_eur=float(strategy_orchestrator.get("initial_treasury_eur") or 500.0),
            max_instance_exposure_pct=float(strategy_orchestrator.get("max_instance_exposure_pct") or 0.60),
            max_strategy_exposure_pct=float(strategy_orchestrator.get("max_strategy_exposure_pct") or 0.50),
            max_symbol_exposure_pct=float(strategy_orchestrator.get("max_symbol_exposure_pct") or 0.20),
            max_open_positions=int(strategy_orchestrator.get("max_open_positions") or 3),
            cooldown_hours=float(strategy_orchestrator.get("cooldown_hours") or 6.0),
            max_daily_loss_pct=float(strategy_orchestrator.get("max_daily_loss_pct") or 0.03),
            max_drawdown_pct=float(strategy_orchestrator.get("max_drawdown_pct") or 0.10),
            min_research_meta_score=float(strategy_orchestrator.get("min_research_meta_score") or 20.0),
            signal_history_bars=int(strategy_orchestrator.get("signal_history_bars") or 384),
        ),
        strategy_edge_review=DailyStrategyEdgeReviewConfig(
            enabled=bool(strategy_edge_review.get("enabled", False)),
            output_dir=Path(str(strategy_edge_review.get("output_dir") or "reports/research")),
            min_candidate_trades=int(strategy_edge_review.get("min_candidate_trades") or 50),
            min_candidate_pf=float(strategy_edge_review.get("min_candidate_pf") or 1.30),
            high_quality_pf=float(strategy_edge_review.get("high_quality_pf") or 1.50),
            max_drawdown_pct=float(strategy_edge_review.get("max_drawdown_pct") or 10.0),
            max_single_symbol_positive_share=float(
                strategy_edge_review.get("max_single_symbol_positive_share") or 0.40
            ),
        ),
    )
    config.validate()
    return config


def run_daily_research_data_collection(
    *,
    config_path: str | Path,
    run_id: str,
    ohlc_fetcher: OHLCFetcher | None = None,
    depth_fetcher: DepthFetcher | None = None,
    asset_pairs_fetcher: AssetPairsFetcher | None = None,
) -> DailyResearchDataCollectionResult:
    config = load_daily_research_data_collection_config(config_path)
    run_report_dir = config.output_dirs.reports / run_id
    run_ohlcv_dir = config.output_dirs.ohlcv / run_id
    run_micro_dir = config.output_dirs.microstructure / run_id
    run_report_dir.mkdir(parents=True, exist_ok=True)
    operations: list[DailyCollectionOperation] = []
    ohlcv_csv_paths: list[str] = []
    preflight = _preflight_active_symbols(config, asset_pairs_fetcher=asset_pairs_fetcher)
    symbol_mappings = preflight.mapping_by_symbol()
    collection_symbols = preflight.resolved_symbols

    for symbol in collection_symbols:
        for timeframe in config.timeframes:
            op = _collect_one_ohlcv(
                run_id=run_id,
                symbol=symbol,
                timeframe=timeframe,
                output_dir=run_ohlcv_dir,
                config=config,
                fetcher=ohlc_fetcher,
                symbol_mappings=symbol_mappings,
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
                symbols=collection_symbols,
                output_dir=run_micro_dir,
                depth_count=config.microstructure_depth_count,
                samples=config.microstructure_samples_per_run,
                sleep_seconds=config.microstructure_sample_interval_seconds,
                export_csv=True,
                continue_on_error=True,
            ),
            fetcher=depth_fetcher,
            symbol_mappings=symbol_mappings,
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

    high_conviction_path = _run_high_conviction_walk_forward(
        config=config,
        run_id=run_id,
        symbols=collection_symbols,
        operations=operations,
    )
    strategy_orchestrator_path = _run_strategy_orchestrator(
        config=config,
        run_id=run_id,
        symbols=collection_symbols,
        operations=operations,
        microstructure_profiles=profiles,
    )
    strategy_edge_review_path = _run_strategy_edge_review(
        config=config,
        run_id=run_id,
        operations=operations,
    )

    result = DailyResearchDataCollectionResult(
        run_id=run_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        config_path=str(Path(config_path)),
        operations=tuple(operations),
        microstructure_result=micro_result.to_dict() if micro_result else None,
        microstructure_profile_path=micro_profile_path,
        data_readiness_dashboard_path=dashboard_path,
        high_conviction_walk_forward_report_path=high_conviction_path,
        strategy_orchestrator_report_path=strategy_orchestrator_path,
        strategy_edge_review_report_path=strategy_edge_review_path,
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
        high_conviction_walk_forward_report_path=result.high_conviction_walk_forward_report_path,
        strategy_orchestrator_report_path=result.strategy_orchestrator_report_path,
        strategy_edge_review_report_path=result.strategy_edge_review_report_path,
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
            f"- High Conviction walk-forward: `{result.high_conviction_walk_forward_report_path or 'not enabled'}`",
            f"- Strategy orchestrator treasury report: `{result.strategy_orchestrator_report_path or 'not enabled'}`",
            f"- Strategy edge review: `{result.strategy_edge_review_report_path or 'not enabled'}`",
            "",
            "## Safety",
            "",
        ]
    )
    lines.extend(f"- {note}" for note in result.safety_notes)
    lines.append("")
    return "\n".join(lines)


def _run_high_conviction_walk_forward(
    *,
    config: DailyResearchDataCollectionConfig,
    run_id: str,
    symbols: tuple[str, ...],
    operations: list[DailyCollectionOperation],
) -> str | None:
    scheduled = config.high_conviction_walk_forward
    if not scheduled.enabled:
        return None
    try:
        from .high_conviction_walk_forward import (
            HighConvictionWalkForwardConfig,
            build_high_conviction_walk_forward_report,
            write_high_conviction_walk_forward_report,
        )

        report = write_high_conviction_walk_forward_report(
            build_high_conviction_walk_forward_report(
                HighConvictionWalkForwardConfig(
                    run_id=f"{run_id}_high_conviction_walk_forward",
                    data_paths=(config.output_dirs.ohlcv,),
                    output_dir=scheduled.output_dir,
                    symbols=symbols,
                    min_expected_move_bps=scheduled.min_expected_move_bps,
                    risk_reward_ratio=scheduled.risk_reward_ratio,
                    max_hold_hours=scheduled.max_hold_hours,
                    exit_modes=scheduled.exit_modes,
                    primary_exit_mode=scheduled.primary_exit_mode,
                    train_window_bars=scheduled.train_window_bars,
                    test_window_bars=scheduled.test_window_bars,
                    step_window_bars=scheduled.step_window_bars,
                    min_folds=scheduled.min_folds,
                    min_positive_fold_ratio=scheduled.min_positive_fold_ratio,
                    min_closed_trades_for_review=scheduled.min_closed_trades_for_review,
                )
            ),
            scheduled.output_dir,
        )
        operations.append(
            DailyCollectionOperation(
                operation_type="high_conviction_walk_forward",
                symbol=None,
                timeframe=None,
                status="ok",
                row_count=report.deduplicated_bar_count,
                output_path=report.json_report_path,
                markdown_report_path=report.markdown_report_path,
                error=report.decision.status,
            )
        )
        return report.markdown_report_path
    except Exception as exc:
        operations.append(
            DailyCollectionOperation(
                operation_type="high_conviction_walk_forward",
                symbol=None,
                timeframe=None,
                status="error",
                error=str(exc),
            )
        )
        return None


def _run_strategy_orchestrator(
    *,
    config: DailyResearchDataCollectionConfig,
    run_id: str,
    symbols: tuple[str, ...],
    operations: list[DailyCollectionOperation],
    microstructure_profiles: tuple[Any, ...] = (),
) -> str | None:
    scheduled = config.strategy_orchestrator
    if not scheduled.enabled:
        return None
    try:
        from .strategy_orchestrator import (
            StrategyOrchestratorConfig,
            build_strategy_orchestrator_report,
            write_strategy_orchestrator_report,
        )

        report = write_strategy_orchestrator_report(
            build_strategy_orchestrator_report(
                StrategyOrchestratorConfig(
                    run_id=f"{run_id}_strategy_orchestrator",
                    data_paths=(config.output_dirs.ohlcv,),
                    output_dir=scheduled.output_dir,
                    instance_id=scheduled.instance_id,
                    initial_treasury_eur=scheduled.initial_treasury_eur,
                    symbols=symbols,
                    microstructure_profiles=tuple(
                        profile.to_dict() if hasattr(profile, "to_dict") else dict(profile)
                        for profile in microstructure_profiles
                    ),
                    max_instance_exposure_pct=scheduled.max_instance_exposure_pct,
                    max_strategy_exposure_pct=scheduled.max_strategy_exposure_pct,
                    max_symbol_exposure_pct=scheduled.max_symbol_exposure_pct,
                    max_open_positions=scheduled.max_open_positions,
                    cooldown_hours=scheduled.cooldown_hours,
                    max_daily_loss_pct=scheduled.max_daily_loss_pct,
                    max_drawdown_pct=scheduled.max_drawdown_pct,
                    min_research_meta_score=scheduled.min_research_meta_score,
                    signal_history_bars=scheduled.signal_history_bars,
                )
            ),
            scheduled.output_dir,
        )
        operations.append(
            DailyCollectionOperation(
                operation_type="strategy_orchestrator",
                symbol=None,
                timeframe=None,
                status="ok",
                row_count=len(report.standardized_signals),
                output_path=report.json_report_path,
                markdown_report_path=report.markdown_report_path,
                error=report.final_status,
            )
        )
        return report.markdown_report_path
    except Exception as exc:
        operations.append(
            DailyCollectionOperation(
                operation_type="strategy_orchestrator",
                symbol=None,
                timeframe=None,
                status="error",
                error=str(exc),
            )
        )
        return None


def _run_strategy_edge_review(
    *,
    config: DailyResearchDataCollectionConfig,
    run_id: str,
    operations: list[DailyCollectionOperation],
) -> str | None:
    scheduled = config.strategy_edge_review
    if not scheduled.enabled:
        return None
    high_conviction_json = _operation_output_path(operations, "high_conviction_walk_forward")
    strategy_orchestrator_json = _operation_output_path(operations, "strategy_orchestrator")
    if not high_conviction_json or not strategy_orchestrator_json:
        missing = []
        if not high_conviction_json:
            missing.append("high_conviction_walk_forward")
        if not strategy_orchestrator_json:
            missing.append("strategy_orchestrator")
        operations.append(
            DailyCollectionOperation(
                operation_type="strategy_edge_review",
                symbol=None,
                timeframe=None,
                status="skipped",
                error="missing prerequisite report(s): " + ", ".join(missing),
            )
        )
        return None
    try:
        from .strategy_edge_improvement import (
            StrategyEdgeReviewConfig,
            build_strategy_edge_improvement_report,
            write_strategy_edge_improvement_report,
        )

        report_date = datetime.now(timezone.utc).date().isoformat()
        edge_output_dir = scheduled.output_dir / run_id
        written = write_strategy_edge_improvement_report(
            build_strategy_edge_improvement_report(
                StrategyEdgeReviewConfig(
                    run_id=f"{run_id}_strategy_edge_review",
                    output_dir=edge_output_dir,
                    report_date=report_date,
                    strategy_orchestrator_report_path=Path(strategy_orchestrator_json),
                    high_conviction_report_path=Path(high_conviction_json),
                    min_candidate_trades=scheduled.min_candidate_trades,
                    min_candidate_pf=scheduled.min_candidate_pf,
                    high_quality_pf=scheduled.high_quality_pf,
                    max_drawdown_pct=scheduled.max_drawdown_pct,
                    max_single_symbol_positive_share=scheduled.max_single_symbol_positive_share,
                )
            ),
            edge_output_dir,
        )
        operations.append(
            DailyCollectionOperation(
                operation_type="strategy_edge_review",
                symbol=None,
                timeframe=None,
                status="ok",
                output_path=written.json_report_path,
                markdown_report_path=written.improvement_markdown_path,
                error="research_only_no_promotion",
            )
        )
        return written.improvement_markdown_path
    except Exception as exc:
        operations.append(
            DailyCollectionOperation(
                operation_type="strategy_edge_review",
                symbol=None,
                timeframe=None,
                status="error",
                error=str(exc),
            )
        )
        return None


def _operation_output_path(operations: list[DailyCollectionOperation], operation_type: str) -> str | None:
    for operation in reversed(operations):
        if operation.operation_type == operation_type and operation.status == "ok" and operation.output_path:
            return operation.output_path
    return None


def _collect_one_ohlcv(
    *,
    run_id: str,
    symbol: str,
    timeframe: str,
    output_dir: Path,
    config: DailyResearchDataCollectionConfig,
    fetcher: OHLCFetcher | None,
    symbol_mappings: Mapping[str, KrakenPublicPairMapping],
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
            symbol_mappings=symbol_mappings,
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


def _preflight_active_symbols(
    config: DailyResearchDataCollectionConfig,
    *,
    asset_pairs_fetcher: AssetPairsFetcher | None = None,
) -> KrakenSymbolPreflight:
    return preflight_kraken_public_symbols(
        config.all_symbols,
        asset_pairs_fetcher=asset_pairs_fetcher,
    )
