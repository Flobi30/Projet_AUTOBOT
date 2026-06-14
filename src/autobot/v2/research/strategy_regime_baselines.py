"""Regime-level baselines for AUTOBOT research validation.

This module compares strategy/regime buckets against simple references. It is
research-only: it never changes paper/live execution, strategy routing, sizing
or registry promotion.
"""

from __future__ import annotations

import json
import argparse
import random
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
from pathlib import Path
from typing import Iterable, Sequence

from autobot.v2.cost_profiles import COST_PROFILE_NAMES, DEFAULT_RESEARCH_COST_PROFILE

from .execution_cost_model import (
    ExecutionCostConfig,
    ExecutionCostModel,
    FillRequest,
    execution_cost_config_for_profile,
)
from .market_data_repository import MarketBar, MarketDataRepository
from .regime_context import enrich_bars_with_regime_context
from .strategy_regime_report import (
    StrategyRegimeReport,
    _journal_path_from_cell,
    analyze_strategy_regime_journals,
    load_strategy_regime_report,
)


@dataclass(frozen=True)
class RegimeBaselineResult:
    name: str
    net_pnl_eur: float
    total_return_pct: float
    trade_count: int
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class StrategyRegimeBaselineBucket:
    strategy_id: str
    regime: str
    strategy_trade_count: int
    strategy_net_pnl_eur: float
    baselines: tuple[RegimeBaselineResult, ...]

    @property
    def best_baseline(self) -> RegimeBaselineResult | None:
        if not self.baselines:
            return None
        return max(self.baselines, key=lambda baseline: baseline.net_pnl_eur)

    @property
    def best_baseline_name(self) -> str | None:
        baseline = self.best_baseline
        return baseline.name if baseline else None

    @property
    def best_baseline_net_pnl_eur(self) -> float | None:
        baseline = self.best_baseline
        return baseline.net_pnl_eur if baseline else None

    @property
    def delta_vs_best_baseline_eur(self) -> float | None:
        baseline = self.best_baseline
        if baseline is None:
            return None
        return self.strategy_net_pnl_eur - baseline.net_pnl_eur

    @property
    def beats_best_baseline(self) -> bool | None:
        delta = self.delta_vs_best_baseline_eur
        return None if delta is None else delta > 0.0

    @property
    def beats_no_trade(self) -> bool:
        return self.strategy_net_pnl_eur > 0.0

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["baselines"] = [baseline.to_dict() for baseline in self.baselines]
        payload["best_baseline_name"] = self.best_baseline_name
        payload["best_baseline_net_pnl_eur"] = self.best_baseline_net_pnl_eur
        payload["delta_vs_best_baseline_eur"] = self.delta_vs_best_baseline_eur
        payload["beats_best_baseline"] = self.beats_best_baseline
        payload["beats_no_trade"] = self.beats_no_trade
        return payload


@dataclass(frozen=True)
class StrategyRegimeBaselineReport:
    run_id: str
    bucket_count: int
    buckets: tuple[StrategyRegimeBaselineBucket, ...]
    json_report_path: str | None = None
    markdown_report_path: str | None = None

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "bucket_count": self.bucket_count,
            "buckets": [bucket.to_dict() for bucket in self.buckets],
            "json_report_path": self.json_report_path,
            "markdown_report_path": self.markdown_report_path,
        }


def evaluate_strategy_regime_baselines(
    strategy_report: StrategyRegimeReport,
    bars: Sequence[MarketBar],
    *,
    initial_capital_eur: float = 1_000.0,
    order_notional_eur: float = 100.0,
    cost_config: ExecutionCostConfig | None = None,
    seed_salt: str = "",
) -> StrategyRegimeBaselineReport:
    """Compare each strategy/regime bucket to simple regime-aware baselines."""

    if initial_capital_eur <= 0.0:
        raise ValueError("initial_capital_eur must be positive")
    if order_notional_eur <= 0.0:
        raise ValueError("order_notional_eur must be positive")
    repository = MarketDataRepository()
    ordered_bars = repository.normalize(bars)
    bars_by_symbol_regime: dict[tuple[str, str], list[MarketBar]] = {}
    for bar in ordered_bars:
        bars_by_symbol_regime.setdefault((bar.symbol.upper(), _bar_regime(bar)), []).append(bar)
    cost_model = ExecutionCostModel(cost_config)
    buckets = tuple(
        StrategyRegimeBaselineBucket(
            strategy_id=bucket.strategy_id,
            regime=bucket.regime,
            strategy_trade_count=bucket.trade_count,
            strategy_net_pnl_eur=bucket.net_pnl_eur,
            baselines=(
                RegimeBaselineResult(
                    name="no_trade",
                    net_pnl_eur=0.0,
                    total_return_pct=0.0,
                    trade_count=0,
                    notes="Abstain from this strategy/regime bucket.",
                ),
                _buy_hold_regime_baseline(
                    bucket.symbols,
                    bucket.regime,
                    bars_by_symbol_regime,
                    initial_capital_eur=initial_capital_eur,
                    cost_model=cost_model,
                ),
                _random_same_frequency_regime_baseline(
                    bucket.strategy_id,
                    bucket.regime,
                    bucket.symbols,
                    bucket.trade_count,
                    bars_by_symbol_regime,
                    order_notional_eur=order_notional_eur,
                    initial_capital_eur=initial_capital_eur,
                    cost_model=cost_model,
                    seed_salt=f"{seed_salt}:{strategy_report.run_id}",
                ),
            ),
        )
        for bucket in strategy_report.buckets
    )
    return StrategyRegimeBaselineReport(
        run_id=f"{strategy_report.run_id}_baseline_comparison",
        bucket_count=len(buckets),
        buckets=tuple(
            sorted(
                buckets,
                key=lambda item: (
                    item.beats_best_baseline is not True,
                    item.delta_vs_best_baseline_eur or -10**12,
                    item.strategy_id,
                    item.regime,
                ),
            )
        ),
    )


def write_strategy_regime_baseline_report(
    result: StrategyRegimeBaselineReport,
    output_dir: str | Path,
) -> StrategyRegimeBaselineReport:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / f"{result.run_id}.json"
    md_path = output_path / f"{result.run_id}.md"
    json_path.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(render_strategy_regime_baseline_report(result), encoding="utf-8")
    return replace(result, json_report_path=str(json_path), markdown_report_path=str(md_path))


def write_matrix_strategy_regime_baseline_report(matrix_config, matrix_result, output_dir: str | Path):
    journal_paths = [
        path
        for path in (_journal_path_from_cell(getattr(cell, "report_path", None)) for cell in matrix_result.results)
        if path is not None and path.exists()
    ]
    strategy_report = analyze_strategy_regime_journals(
        journal_paths,
        run_id=f"{matrix_result.run_id}_strategy_regime",
    )
    bars = _load_matrix_bars(matrix_config)
    if matrix_config.include_regime_context:
        bars = enrich_bars_with_regime_context(bars)
    return write_strategy_regime_baseline_report(
        evaluate_strategy_regime_baselines(
            strategy_report,
            bars,
            initial_capital_eur=matrix_config.initial_capital_eur,
            order_notional_eur=matrix_config.order_notional_eur,
            cost_config=matrix_config.cost_config,
            seed_salt=matrix_result.run_id,
        ),
        output_dir,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write AUTOBOT strategy/regime baseline report")
    parser.add_argument("--strategy-regime-report", required=True)
    parser.add_argument("--data-source", choices=["csv", "autobot_state_db"], required=True)
    parser.add_argument("--data-path", required=True)
    parser.add_argument("--symbols", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--include-regime-context", action="store_true")
    parser.add_argument("--initial-capital-eur", type=float, default=1_000.0)
    parser.add_argument("--order-notional-eur", type=float, default=100.0)
    parser.add_argument("--cost-profile", choices=COST_PROFILE_NAMES, default=DEFAULT_RESEARCH_COST_PROFILE)
    parser.add_argument("--fee-bps", type=float, default=None)
    parser.add_argument("--spread-bps", type=float, default=None)
    parser.add_argument("--slippage-bps", type=float, default=None)
    parser.add_argument("--start-at", default=None)
    parser.add_argument("--end-at", default=None)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)

    symbols = tuple(item.strip().upper() for item in args.symbols.split(",") if item.strip())
    report = load_strategy_regime_report(args.strategy_regime_report)
    bars = _load_bars(
        data_source=args.data_source,
        data_path=Path(args.data_path),
        symbols=symbols,
        start_at=args.start_at,
        end_at=args.end_at,
        limit=args.limit,
    )
    if args.include_regime_context:
        bars = enrich_bars_with_regime_context(bars)
    result = write_strategy_regime_baseline_report(
        evaluate_strategy_regime_baselines(
            report,
            bars,
            initial_capital_eur=args.initial_capital_eur,
            order_notional_eur=args.order_notional_eur,
            cost_config=execution_cost_config_for_profile(
                args.cost_profile,
                fee_bps=args.fee_bps,
                spread_bps=args.spread_bps,
                slippage_bps=args.slippage_bps,
            ),
            seed_salt=report.run_id,
        ),
        args.output_dir,
    )
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0


def render_strategy_regime_baseline_report(result: StrategyRegimeBaselineReport) -> str:
    lines = [
        f"# Strategy Regime Baseline Report - {result.run_id}",
        "",
        "## Summary",
        "",
        f"Buckets: `{result.bucket_count}`",
        "",
        "## Results",
        "",
        "| Strategy | Regime | Trades | Strategy Net | Best Baseline | Baseline Net | Delta | Beats No-Trade | Beats Best |",
        "| --- | --- | ---: | ---: | --- | ---: | ---: | --- | --- |",
    ]
    if not result.buckets:
        lines.append("| none | none | 0 | 0.000000 | none | 0.000000 | 0.000000 | false | false |")
    for bucket in result.buckets:
        lines.append(
            f"| {bucket.strategy_id} | {bucket.regime} | {bucket.strategy_trade_count} | "
            f"{bucket.strategy_net_pnl_eur:.6f} | {bucket.best_baseline_name or 'none'} | "
            f"{_fmt(bucket.best_baseline_net_pnl_eur)} | {_fmt(bucket.delta_vs_best_baseline_eur)} | "
            f"{str(bucket.beats_no_trade).lower()} | {str(bucket.beats_best_baseline).lower()} |"
        )
    lines.extend(
        [
            "",
            "## Baseline Details",
            "",
        ]
    )
    for bucket in result.buckets:
        lines.append(f"### {bucket.strategy_id} / {bucket.regime}")
        lines.append("")
        lines.append("| Baseline | Net PnL | Return | Trades | Notes |")
        lines.append("| --- | ---: | ---: | ---: | --- |")
        for baseline in bucket.baselines:
            lines.append(
                f"| {baseline.name} | {baseline.net_pnl_eur:.6f} | "
                f"{baseline.total_return_pct:.6f}% | {baseline.trade_count} | {baseline.notes} |"
            )
        lines.append("")
    lines.extend(
        [
            "## Safety",
            "",
            "This report is research-only. It does not authorize paper or live execution.",
            "",
        ]
    )
    return "\n".join(lines)


def _buy_hold_regime_baseline(
    symbols: Iterable[str],
    regime: str,
    bars_by_symbol_regime: dict[tuple[str, str], list[MarketBar]],
    *,
    initial_capital_eur: float,
    cost_model: ExecutionCostModel,
) -> RegimeBaselineResult:
    series_by_symbol = _eligible_series(symbols, regime, bars_by_symbol_regime)
    if not series_by_symbol:
        return RegimeBaselineResult(
            name="buy_and_hold_regime_segments",
            net_pnl_eur=0.0,
            total_return_pct=0.0,
            trade_count=0,
            notes="No matching regime bars with at least two observations.",
        )
    allocation = initial_capital_eur / len(series_by_symbol)
    net_pnl = 0.0
    executed = 0
    for symbol, series in series_by_symbol.items():
        entry_bar = series[0]
        exit_bar = series[-1]
        entry = cost_model.simulate_fill(
            FillRequest(
                symbol=symbol,
                side="buy",
                price=entry_bar.close,
                notional_eur=allocation,
                timestamp=entry_bar.timestamp,
            )
        )
        exit_fill = cost_model.simulate_fill(
            FillRequest(
                symbol=symbol,
                side="sell",
                price=exit_bar.close,
                quantity=entry.quantity,
                timestamp=exit_bar.timestamp,
            )
        )
        if entry.accepted and exit_fill.accepted:
            executed += 1
            net_pnl += cost_model.round_trip_pnl(entry, exit_fill).net_pnl_eur
    return RegimeBaselineResult(
        name="buy_and_hold_regime_segments",
        net_pnl_eur=net_pnl,
        total_return_pct=(net_pnl / initial_capital_eur) * 100.0,
        trade_count=executed,
        notes="One first-to-last long per symbol inside matching regime bars, net of costs.",
    )


def _random_same_frequency_regime_baseline(
    strategy_id: str,
    regime: str,
    symbols: Iterable[str],
    trade_count: int,
    bars_by_symbol_regime: dict[tuple[str, str], list[MarketBar]],
    *,
    order_notional_eur: float,
    initial_capital_eur: float,
    cost_model: ExecutionCostModel,
    seed_salt: str,
) -> RegimeBaselineResult:
    if trade_count <= 0:
        return RegimeBaselineResult(
            name="random_signal_same_frequency_regime",
            net_pnl_eur=0.0,
            total_return_pct=0.0,
            trade_count=0,
            notes="Not computed because the strategy bucket has no trades.",
        )
    series_by_symbol = _eligible_series(symbols, regime, bars_by_symbol_regime)
    if not series_by_symbol:
        return RegimeBaselineResult(
            name="random_signal_same_frequency_regime",
            net_pnl_eur=0.0,
            total_return_pct=0.0,
            trade_count=0,
            notes="No matching regime bars with at least two observations.",
        )
    rng = random.Random(_seed(seed_salt, strategy_id, regime, sorted(series_by_symbol), trade_count))
    eligible_symbols = sorted(series_by_symbol)
    net_pnl = 0.0
    executed = 0
    for _ in range(trade_count):
        symbol = rng.choice(eligible_symbols)
        series = series_by_symbol[symbol]
        entry_index = rng.randrange(0, len(series) - 1)
        exit_index = rng.randrange(entry_index + 1, len(series))
        entry_bar = series[entry_index]
        exit_bar = series[exit_index]
        entry = cost_model.simulate_fill(
            FillRequest(
                symbol=symbol,
                side="buy",
                price=entry_bar.close,
                notional_eur=order_notional_eur,
                timestamp=entry_bar.timestamp,
            )
        )
        exit_fill = cost_model.simulate_fill(
            FillRequest(
                symbol=symbol,
                side="sell",
                price=exit_bar.close,
                quantity=entry.quantity,
                timestamp=exit_bar.timestamp,
            )
        )
        if entry.accepted and exit_fill.accepted:
            executed += 1
            net_pnl += cost_model.round_trip_pnl(entry, exit_fill).net_pnl_eur
    return RegimeBaselineResult(
        name="random_signal_same_frequency_regime",
        net_pnl_eur=net_pnl,
        total_return_pct=(net_pnl / initial_capital_eur) * 100.0,
        trade_count=executed,
        notes=f"Deterministic random long baseline in same regime, requested trades={trade_count}.",
    )


def _eligible_series(
    symbols: Iterable[str],
    regime: str,
    bars_by_symbol_regime: dict[tuple[str, str], list[MarketBar]],
) -> dict[str, list[MarketBar]]:
    result: dict[str, list[MarketBar]] = {}
    for symbol in sorted({str(value).upper() for value in symbols}):
        series = sorted(bars_by_symbol_regime.get((symbol, regime), ()), key=lambda bar: bar.timestamp)
        if len(series) >= 2:
            result[symbol] = series
    return result


def _load_matrix_bars(matrix_config) -> list[MarketBar]:
    return _load_bars(
        data_source=matrix_config.data_source,
        data_path=matrix_config.data_path,
        symbols=matrix_config.symbols,
        start_at=matrix_config.start_at,
        end_at=matrix_config.end_at,
        limit=matrix_config.limit,
    )


def _load_bars(
    *,
    data_source: str,
    data_path: Path,
    symbols: Sequence[str],
    start_at=None,
    end_at=None,
    limit: int | None = None,
) -> list[MarketBar]:
    repository = MarketDataRepository()
    bars: list[MarketBar] = []
    if data_source == "autobot_state_db":
        for symbol in symbols:
            bars.extend(
                repository.load_autobot_state_db(
                    data_path,
                    symbol=symbol,
                    start_at=start_at,
                    end_at=end_at,
                    limit=limit,
                )
            )
        return repository.normalize(bars)
    if data_source == "csv":
        for symbol in symbols:
            bars.extend(
                repository.load_csv(
                    data_path,
                    default_symbol=symbol,
                    default_timeframe="csv",
                )
            )
        return repository.normalize(bars)
    raise ValueError(f"unsupported data_source: {data_source}")


def _bar_regime(bar: MarketBar) -> str:
    metadata = bar.metadata if isinstance(bar.metadata, dict) else {}
    regime = str(metadata.get("regime") or "unknown").strip().lower()
    return regime or "unknown"


def _seed(seed_salt: str, strategy_id: str, regime: str, symbols: Sequence[str], trade_count: int) -> int:
    payload = f"{seed_salt}:{strategy_id}:{regime}:{','.join(symbols)}:{trade_count}".encode("utf-8")
    return int.from_bytes(sha256(payload).digest()[:8], "big")


def _fmt(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.6f}"


if __name__ == "__main__":
    raise SystemExit(main())
