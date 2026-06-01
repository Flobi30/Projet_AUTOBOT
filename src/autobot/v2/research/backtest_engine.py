"""Deterministic research backtest engine for AUTOBOT.

This engine is intentionally small and isolated. It is not a runtime paper/live
executor; it exists to replay OHLCV bars through explicit signal functions,
simulate realistic costs, write a research journal, compare baselines and emit
immutable JSON/Markdown reports.
"""

from __future__ import annotations

import json
import random
from hashlib import sha256
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable, Protocol, Sequence

from .execution_cost_model import ExecutionCostConfig, ExecutionCostModel, FillRequest, FillResult
from .market_data_repository import MarketBar, MarketDataRepository
from .metrics_engine import MetricsEngine, MetricsResult
from .trade_journal import TradeJournal, TradeRecord


class SignalGenerator(Protocol):
    def __call__(self, bar: MarketBar, history: Sequence[MarketBar]) -> Iterable["BacktestSignal"]:
        ...


@dataclass(frozen=True)
class BacktestSignal:
    symbol: str
    side: str
    price: float
    timestamp: Any
    reason: str
    quantity: float | None = None
    notional_eur: float | None = None
    order_type: str = "market"
    limit_price: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BacktestConfig:
    run_id: str
    strategy_id: str
    dataset_id: str
    hypothesis: str
    initial_capital_eur: float = 1_000.0
    default_order_notional_eur: float = 50.0
    output_dir: Path = Path("reports/backtests")
    cost_config: ExecutionCostConfig = field(default_factory=ExecutionCostConfig)
    min_closed_trades: int = 30
    min_profit_factor: float = 1.2
    max_drawdown_pct: float = 15.0
    close_open_positions_at_end: bool = True


@dataclass(frozen=True)
class BaselineResult:
    name: str
    net_pnl_eur: float
    total_return_pct: float
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BacktestDecision:
    status: str
    reason: str
    proposed_registry_status: str
    live_promotion_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BacktestResult:
    run_id: str
    strategy_id: str
    dataset_id: str
    hypothesis: str
    event_count: int
    signal_count: int
    fill_count: int
    rejected_fill_count: int
    trade_count: int
    metrics: MetricsResult
    baselines: tuple[BaselineResult, ...]
    decision: BacktestDecision
    journal_path: str | None = None
    json_report_path: str | None = None
    markdown_report_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "strategy_id": self.strategy_id,
            "dataset_id": self.dataset_id,
            "hypothesis": self.hypothesis,
            "event_count": self.event_count,
            "signal_count": self.signal_count,
            "fill_count": self.fill_count,
            "rejected_fill_count": self.rejected_fill_count,
            "trade_count": self.trade_count,
            "metrics": self.metrics.to_dict(),
            "baselines": [baseline.to_dict() for baseline in self.baselines],
            "decision": self.decision.to_dict(),
            "journal_path": self.journal_path,
            "json_report_path": self.json_report_path,
            "markdown_report_path": self.markdown_report_path,
        }


@dataclass(frozen=True)
class _OpenPosition:
    signal: BacktestSignal
    fill: FillResult
    highest_price: float
    lowest_price: float
    bars_held: int = 0


class BacktestEngine:
    """Run a deterministic long-only research backtest over OHLCV bars."""

    def __init__(
        self,
        config: BacktestConfig,
        *,
        market_data_repository: MarketDataRepository | None = None,
        cost_model: ExecutionCostModel | None = None,
        metrics_engine: MetricsEngine | None = None,
    ) -> None:
        if config.initial_capital_eur <= 0.0:
            raise ValueError("initial_capital_eur must be positive")
        if config.default_order_notional_eur <= 0.0:
            raise ValueError("default_order_notional_eur must be positive")
        self.config = config
        self.market_data_repository = market_data_repository or MarketDataRepository()
        self.cost_model = cost_model or ExecutionCostModel(config.cost_config)
        self.metrics_engine = metrics_engine or MetricsEngine()

    def run(
        self,
        bars: Sequence[MarketBar],
        signal_generator: SignalGenerator,
        *,
        write_reports: bool = True,
    ) -> BacktestResult:
        ordered_bars = self.market_data_repository.normalize(bars)
        self.market_data_repository.validate(ordered_bars)
        history_by_symbol: dict[str, list[MarketBar]] = {}
        positions: dict[str, _OpenPosition] = {}
        journal = TradeJournal()
        signal_count = 0
        fill_count = 0
        rejected_fill_count = 0
        latest_by_symbol: dict[str, MarketBar] = {}

        for bar in ordered_bars:
            latest_by_symbol[bar.symbol] = bar
            current_position = positions.get(bar.symbol)
            if current_position is not None:
                positions[bar.symbol] = self._update_position_path(current_position, bar)
            history = history_by_symbol.setdefault(bar.symbol, [])
            history.append(bar)
            signals = list(signal_generator(bar, tuple(history)))
            signal_count += len(signals)
            for signal in signals:
                if signal.symbol.upper() != bar.symbol.upper():
                    rejected_fill_count += 1
                    continue
                if signal.side.lower() == "buy":
                    if signal.symbol in positions:
                        rejected_fill_count += 1
                        continue
                    fill = self._simulate_signal(signal)
                    if fill.accepted:
                        fill_count += 1
                        positions[signal.symbol] = _OpenPosition(
                            signal=signal,
                            fill=fill,
                            highest_price=fill.execution_price,
                            lowest_price=fill.execution_price,
                        )
                    else:
                        rejected_fill_count += 1
                elif signal.side.lower() == "sell":
                    position = positions.pop(signal.symbol, None)
                    if position is None:
                        rejected_fill_count += 1
                        continue
                    exit_signal = self._exit_signal_from_position(signal, position)
                    fill = self._simulate_signal(exit_signal)
                    if fill.accepted:
                        fill_count += 1
                        journal.add(self._trade_record(position, exit_signal, fill))
                    else:
                        rejected_fill_count += 1
                        positions[signal.symbol] = position
                else:
                    rejected_fill_count += 1

        if self.config.close_open_positions_at_end:
            for symbol, position in list(positions.items()):
                final_bar = latest_by_symbol.get(symbol)
                if final_bar is None:
                    continue
                exit_signal = BacktestSignal(
                    symbol=symbol,
                    side="sell",
                    price=final_bar.close,
                    timestamp=final_bar.timestamp,
                    reason="end_of_run_close",
                    quantity=position.fill.quantity,
                    metadata={"forced_close": True, **dict(position.signal.metadata)},
                )
                fill = self._simulate_signal(exit_signal)
                if fill.accepted:
                    fill_count += 1
                    journal.add(self._trade_record(position, exit_signal, fill))
                else:
                    rejected_fill_count += 1

        baselines = self._baselines(ordered_bars, strategy_trade_count=len(journal.records))
        comparison_baseline = max(baselines, key=lambda baseline: baseline.total_return_pct)
        metrics = self.metrics_engine.calculate(
            journal.records,
            initial_capital_eur=self.config.initial_capital_eur,
            baseline_name=comparison_baseline.name,
            baseline_return_pct=comparison_baseline.total_return_pct,
        )
        decision = self._decide(metrics)
        result = BacktestResult(
            run_id=self.config.run_id,
            strategy_id=self.config.strategy_id,
            dataset_id=self.config.dataset_id,
            hypothesis=self.config.hypothesis,
            event_count=len(ordered_bars),
            signal_count=signal_count,
            fill_count=fill_count,
            rejected_fill_count=rejected_fill_count,
            trade_count=len(journal.records),
            metrics=metrics,
            baselines=baselines,
            decision=decision,
        )
        if write_reports:
            result = self._write_reports(result, journal)
        return result

    def _simulate_signal(self, signal: BacktestSignal) -> FillResult:
        return self.cost_model.simulate_fill(
            FillRequest(
                symbol=signal.symbol.upper(),
                side=signal.side.lower(),
                price=float(signal.price),
                quantity=signal.quantity,
                notional_eur=signal.notional_eur or self.config.default_order_notional_eur,
                timestamp=signal.timestamp,
                order_type=signal.order_type,
                limit_price=signal.limit_price,
                liquidity_eur=signal.metadata.get("liquidity_eur"),
                bid=signal.metadata.get("bid"),
                ask=signal.metadata.get("ask"),
                metadata=dict(signal.metadata),
            )
        )

    @staticmethod
    def _exit_signal_from_position(signal: BacktestSignal, position: _OpenPosition) -> BacktestSignal:
        return BacktestSignal(
            symbol=signal.symbol,
            side="sell",
            price=signal.price,
            timestamp=signal.timestamp,
            reason=signal.reason,
            quantity=position.fill.quantity,
            order_type=signal.order_type,
            limit_price=signal.limit_price,
            metadata=dict(signal.metadata),
        )

    @staticmethod
    def _update_position_path(position: _OpenPosition, bar: MarketBar) -> _OpenPosition:
        """Update post-entry path diagnostics without changing trading decisions.

        A position opened on the current bar is inserted after signal handling,
        so this method only observes bars that occur after the entry bar. That
        avoids using the entry bar high/low as an accidental look-ahead path.
        """

        return replace(
            position,
            highest_price=max(position.highest_price, float(bar.high)),
            lowest_price=min(position.lowest_price, float(bar.low)),
            bars_held=position.bars_held + 1,
        )

    def _trade_record(self, position: _OpenPosition, exit_signal: BacktestSignal, exit_fill: FillResult) -> TradeRecord:
        pnl = self.cost_model.round_trip_pnl(position.fill, exit_fill)
        return TradeRecord(
            run_id=self.config.run_id,
            strategy_id=self.config.strategy_id,
            symbol=position.fill.symbol,
            side=position.fill.side,
            opened_at=position.fill.timestamp,
            closed_at=exit_fill.timestamp,
            quantity=pnl.quantity,
            entry_price=pnl.entry_price,
            exit_price=pnl.exit_price,
            gross_pnl_eur=pnl.gross_pnl_eur,
            net_pnl_eur=pnl.net_pnl_eur,
            fees_eur=pnl.fees_eur,
            slippage_eur=pnl.slippage_eur,
            spread_cost_eur=pnl.spread_cost_eur,
            latency_cost_eur=pnl.latency_cost_eur,
            entry_reason=position.signal.reason,
            exit_reason=exit_signal.reason,
            regime=str(position.signal.metadata.get("regime") or exit_signal.metadata.get("regime") or "unknown"),
            metadata={
                "entry": position.signal.metadata,
                "exit": exit_signal.metadata,
                "path": self._trade_path_metadata(position, pnl),
            },
        )

    @staticmethod
    def _trade_path_metadata(position: _OpenPosition, pnl) -> dict[str, float | int | None]:
        entry_price = max(float(pnl.entry_price), 1e-12)
        exit_price = float(pnl.exit_price)
        quantity = float(pnl.quantity)
        entry_notional = max(float(position.fill.notional_eur), 1e-12)
        raw_mfe_bps = ((position.highest_price - entry_price) / entry_price) * 10_000.0
        raw_mae_bps = ((position.lowest_price - entry_price) / entry_price) * 10_000.0
        max_favorable_excursion_bps = max(0.0, raw_mfe_bps)
        max_adverse_excursion_bps = min(0.0, raw_mae_bps)
        entry_to_exit_bps = ((exit_price - entry_price) / entry_price) * 10_000.0
        positive_exit_capture_bps = max(0.0, entry_to_exit_bps)
        mfe_giveback_bps = max(0.0, max_favorable_excursion_bps - entry_to_exit_bps)
        total_cost_bps = (float(pnl.total_cost_eur) / entry_notional) * 10_000.0
        return {
            "bars_held": position.bars_held,
            "highest_price": position.highest_price,
            "lowest_price": position.lowest_price,
            "max_favorable_excursion_bps": max_favorable_excursion_bps,
            "max_adverse_excursion_bps": max_adverse_excursion_bps,
            "max_favorable_excursion_eur": max(0.0, (position.highest_price - entry_price) * quantity),
            "max_adverse_excursion_eur": min(0.0, (position.lowest_price - entry_price) * quantity),
            "entry_to_exit_bps": entry_to_exit_bps,
            "positive_exit_capture_bps": positive_exit_capture_bps,
            "mfe_giveback_bps": mfe_giveback_bps,
            "mfe_capture_ratio": (
                entry_to_exit_bps / max_favorable_excursion_bps if max_favorable_excursion_bps > 0.0 else None
            ),
            "positive_mfe_capture_ratio": (
                positive_exit_capture_bps / max_favorable_excursion_bps
                if max_favorable_excursion_bps > 0.0
                else None
            ),
            "net_return_bps": (float(pnl.net_pnl_eur) / entry_notional) * 10_000.0,
            "total_cost_bps": total_cost_bps,
            "mfe_to_cost_ratio": (
                max_favorable_excursion_bps / total_cost_bps if total_cost_bps > 0.0 else None
            ),
            "mae_to_cost_ratio": (
                abs(max_adverse_excursion_bps) / total_cost_bps if total_cost_bps > 0.0 else None
            ),
        }

    def _baselines(self, bars: Sequence[MarketBar], *, strategy_trade_count: int) -> tuple[BaselineResult, ...]:
        no_trade = BaselineResult(name="no_trade", net_pnl_eur=0.0, total_return_pct=0.0)
        by_symbol: dict[str, list[MarketBar]] = {}
        for bar in bars:
            by_symbol.setdefault(bar.symbol, []).append(bar)
        if not by_symbol:
            return (no_trade,)
        allocation = self.config.initial_capital_eur / len(by_symbol)
        net_pnl = 0.0
        for symbol, series in by_symbol.items():
            ordered = sorted(series, key=lambda item: item.timestamp)
            if len(ordered) < 2:
                continue
            entry = self.cost_model.simulate_fill(
                FillRequest(symbol=symbol, side="buy", price=ordered[0].close, notional_eur=allocation, timestamp=ordered[0].timestamp)
            )
            exit_fill = self.cost_model.simulate_fill(
                FillRequest(symbol=symbol, side="sell", price=ordered[-1].close, quantity=entry.quantity, timestamp=ordered[-1].timestamp)
            )
            if entry.accepted and exit_fill.accepted:
                net_pnl += self.cost_model.round_trip_pnl(entry, exit_fill).net_pnl_eur
        buy_hold = BaselineResult(
            name="buy_and_hold",
            net_pnl_eur=net_pnl,
            total_return_pct=(net_pnl / self.config.initial_capital_eur) * 100.0,
            notes="Equal capital allocation per symbol, net of configured costs.",
        )
        random_same_frequency = self._random_signal_baseline(by_symbol, strategy_trade_count=strategy_trade_count)
        return (no_trade, buy_hold, random_same_frequency)

    def _random_signal_baseline(
        self,
        by_symbol: dict[str, list[MarketBar]],
        *,
        strategy_trade_count: int,
    ) -> BaselineResult:
        if strategy_trade_count <= 0:
            return BaselineResult(
                name="random_signal_same_frequency",
                net_pnl_eur=0.0,
                total_return_pct=0.0,
                notes="Not computed because the strategy produced no closed trades.",
            )
        eligible = {
            symbol: sorted(series, key=lambda item: item.timestamp)
            for symbol, series in by_symbol.items()
            if len(series) >= 2
        }
        if not eligible:
            return BaselineResult(
                name="random_signal_same_frequency",
                net_pnl_eur=0.0,
                total_return_pct=0.0,
                notes="Not computed because no symbol has enough bars.",
            )
        rng = random.Random(self._baseline_seed())
        symbols = sorted(eligible)
        net_pnl = 0.0
        executed = 0
        for _ in range(strategy_trade_count):
            symbol = rng.choice(symbols)
            series = eligible[symbol]
            entry_index = rng.randrange(0, len(series) - 1)
            exit_index = rng.randrange(entry_index + 1, len(series))
            entry_bar = series[entry_index]
            exit_bar = series[exit_index]
            entry = self.cost_model.simulate_fill(
                FillRequest(
                    symbol=symbol,
                    side="buy",
                    price=entry_bar.close,
                    notional_eur=self.config.default_order_notional_eur,
                    timestamp=entry_bar.timestamp,
                )
            )
            exit_fill = self.cost_model.simulate_fill(
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
                net_pnl += self.cost_model.round_trip_pnl(entry, exit_fill).net_pnl_eur
        return BaselineResult(
            name="random_signal_same_frequency",
            net_pnl_eur=net_pnl,
            total_return_pct=(net_pnl / self.config.initial_capital_eur) * 100.0,
            notes=f"Deterministic random long baseline, requested trades={strategy_trade_count}, executed={executed}.",
        )

    def _baseline_seed(self) -> int:
        payload = f"{self.config.run_id}:{self.config.strategy_id}:{self.config.dataset_id}".encode("utf-8")
        return int.from_bytes(sha256(payload).digest()[:8], "big")

    def _decide(self, metrics: MetricsResult) -> BacktestDecision:
        if metrics.trade_count < self.config.min_closed_trades:
            return BacktestDecision(
                status="keep_testing",
                reason="insufficient_closed_trades",
                proposed_registry_status="candidate",
            )
        if metrics.total_net_pnl_eur <= 0.0:
            return BacktestDecision(status="reject", reason="negative_net_pnl", proposed_registry_status="rejected")
        if metrics.beats_baseline is False:
            return BacktestDecision(status="modify", reason="does_not_beat_baseline", proposed_registry_status="candidate")
        if metrics.profit_factor is None or metrics.profit_factor < self.config.min_profit_factor:
            return BacktestDecision(status="modify", reason="profit_factor_below_threshold", proposed_registry_status="candidate")
        if metrics.max_drawdown_pct > self.config.max_drawdown_pct:
            return BacktestDecision(status="modify", reason="drawdown_above_threshold", proposed_registry_status="candidate")
        return BacktestDecision(
            status="promote_candidate",
            reason="backtest_criteria_passed_for_human_review",
            proposed_registry_status="backtest_passed",
        )

    def _write_reports(self, result: BacktestResult, journal: TradeJournal) -> BacktestResult:
        output_dir = Path(self.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        journal_path = journal.to_json(output_dir / f"{self.config.run_id}_journal.json")
        json_path = output_dir / f"{self.config.run_id}.json"
        md_path = output_dir / f"{self.config.run_id}.md"
        json_path.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        md_path.write_text(render_backtest_report(result), encoding="utf-8")
        return BacktestResult(
            **{
                **result.to_dict(),
                "metrics": result.metrics,
                "baselines": result.baselines,
                "decision": result.decision,
                "journal_path": str(journal_path),
                "json_report_path": str(json_path),
                "markdown_report_path": str(md_path),
            }
        )


def render_backtest_report(result: BacktestResult) -> str:
    metrics = result.metrics
    lines = [
        f"# Backtest Run - {result.run_id}",
        "",
        f"Strategy: `{result.strategy_id}`",
        f"Dataset: `{result.dataset_id}`",
        f"Hypothesis: {result.hypothesis}",
        "",
        "## Replay",
        "",
        f"- Events: {result.event_count}",
        f"- Signals: {result.signal_count}",
        f"- Fills: {result.fill_count}",
        f"- Rejected fills/signals: {result.rejected_fill_count}",
        f"- Closed trades: {result.trade_count}",
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Initial capital | {metrics.initial_capital_eur:.2f} |",
        f"| Final equity | {metrics.final_equity_eur:.2f} |",
        f"| Net PnL | {metrics.total_net_pnl_eur:.6f} |",
        f"| Total return | {metrics.total_return_pct:.4f}% |",
        f"| Max drawdown | {metrics.max_drawdown_pct:.4f}% |",
        f"| Profit factor | {_fmt(metrics.profit_factor)} |",
        f"| Winrate | {_fmt(metrics.winrate_pct)}% |",
        f"| Expectancy | {_fmt(metrics.expectancy_eur)} |",
        f"| Fees | {metrics.total_fees_eur:.6f} |",
        f"| Spread cost | {metrics.total_spread_cost_eur:.6f} |",
        f"| Slippage | {metrics.total_slippage_eur:.6f} |",
        "",
        "## Baselines",
        "",
        "| Baseline | Net PnL | Return | Notes |",
        "| --- | ---: | ---: | --- |",
    ]
    for baseline in result.baselines:
        lines.append(
            f"| {baseline.name} | {baseline.net_pnl_eur:.6f} | {baseline.total_return_pct:.4f}% | {baseline.notes} |"
        )
    lines.extend(
        [
            "",
            "## Decision",
            "",
            f"Decision: `{result.decision.status}`",
            f"Registry proposal: `{result.decision.proposed_registry_status}`",
            f"Reason: `{result.decision.reason}`",
            f"Live promotion allowed: `{result.decision.live_promotion_allowed}`",
            "",
        ]
    )
    return "\n".join(lines)


def _fmt(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.6f}"
