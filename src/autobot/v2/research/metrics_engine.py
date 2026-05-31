"""Research metrics engine for AUTOBOT validation runs."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from statistics import mean, pstdev
from typing import Any, Sequence

from .trade_journal import TradeRecord


@dataclass(frozen=True)
class MetricsResult:
    initial_capital_eur: float
    final_equity_eur: float
    total_return_pct: float
    trade_count: int
    closed_trade_count: int
    total_gross_pnl_eur: float
    total_net_pnl_eur: float
    total_fees_eur: float
    total_spread_cost_eur: float
    total_slippage_eur: float
    total_latency_cost_eur: float
    winrate_pct: float | None
    profit_factor: float | None
    expectancy_eur: float | None
    average_win_eur: float | None
    average_loss_eur: float | None
    max_drawdown_eur: float
    max_drawdown_pct: float
    average_trade_duration_seconds: float | None
    sharpe_like: float | None
    sortino_like: float | None
    baseline_name: str | None = None
    baseline_return_pct: float | None = None
    baseline_delta_pct: float | None = None
    performance_by_regime: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def beats_baseline(self) -> bool | None:
        if self.baseline_delta_pct is None:
            return None
        return self.baseline_delta_pct > 0.0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["beats_baseline"] = self.beats_baseline
        return data


class MetricsEngine:
    """Calculate net-of-cost research metrics from closed trade records."""

    def calculate(
        self,
        trades: Sequence[TradeRecord],
        *,
        initial_capital_eur: float,
        baseline_name: str | None = None,
        baseline_return_pct: float | None = None,
    ) -> MetricsResult:
        if initial_capital_eur <= 0.0 or not math.isfinite(initial_capital_eur):
            raise ValueError("initial_capital_eur must be positive and finite")
        closed_trades = list(trades)
        total_gross = sum(trade.gross_pnl_eur for trade in closed_trades)
        total_net = sum(trade.net_pnl_eur for trade in closed_trades)
        total_fees = sum(trade.fees_eur for trade in closed_trades)
        total_spread = sum(trade.spread_cost_eur for trade in closed_trades)
        total_slippage = sum(trade.slippage_eur for trade in closed_trades)
        total_latency = sum(trade.latency_cost_eur for trade in closed_trades)
        wins = [trade.net_pnl_eur for trade in closed_trades if trade.net_pnl_eur > 0.0]
        losses = [trade.net_pnl_eur for trade in closed_trades if trade.net_pnl_eur < 0.0]
        final_equity = initial_capital_eur + total_net
        total_return_pct = (total_net / initial_capital_eur) * 100.0
        winrate = (len(wins) / len(closed_trades) * 100.0) if closed_trades else None
        gross_wins = sum(wins)
        gross_losses = abs(sum(losses))
        profit_factor = self._profit_factor(gross_wins, gross_losses, closed_trades)
        expectancy = (total_net / len(closed_trades)) if closed_trades else None
        avg_win = mean(wins) if wins else None
        avg_loss = mean(losses) if losses else None
        max_dd_eur, max_dd_pct = self._max_drawdown(closed_trades, initial_capital_eur)
        durations = [trade.duration_seconds for trade in closed_trades]
        avg_duration = mean(durations) if durations else None
        returns = [trade.net_pnl_eur / initial_capital_eur for trade in closed_trades]
        sharpe = self._sharpe_like(returns)
        sortino = self._sortino_like(returns)
        baseline_delta = None
        if baseline_return_pct is not None:
            baseline_delta = total_return_pct - baseline_return_pct
        return MetricsResult(
            initial_capital_eur=initial_capital_eur,
            final_equity_eur=final_equity,
            total_return_pct=total_return_pct,
            trade_count=len(closed_trades),
            closed_trade_count=len(closed_trades),
            total_gross_pnl_eur=total_gross,
            total_net_pnl_eur=total_net,
            total_fees_eur=total_fees,
            total_spread_cost_eur=total_spread,
            total_slippage_eur=total_slippage,
            total_latency_cost_eur=total_latency,
            winrate_pct=winrate,
            profit_factor=profit_factor,
            expectancy_eur=expectancy,
            average_win_eur=avg_win,
            average_loss_eur=avg_loss,
            max_drawdown_eur=max_dd_eur,
            max_drawdown_pct=max_dd_pct,
            average_trade_duration_seconds=avg_duration,
            sharpe_like=sharpe,
            sortino_like=sortino,
            baseline_name=baseline_name,
            baseline_return_pct=baseline_return_pct,
            baseline_delta_pct=baseline_delta,
            performance_by_regime=self._performance_by_regime(closed_trades),
        )

    @staticmethod
    def _profit_factor(gross_wins: float, gross_losses: float, trades: Sequence[TradeRecord]) -> float | None:
        if not trades:
            return None
        if gross_losses == 0.0:
            return None
        return gross_wins / gross_losses

    @staticmethod
    def _max_drawdown(trades: Sequence[TradeRecord], initial_capital_eur: float) -> tuple[float, float]:
        equity = initial_capital_eur
        peak = initial_capital_eur
        max_drawdown = 0.0
        max_drawdown_pct = 0.0
        for trade in sorted(trades, key=lambda item: item.closed_at):
            equity += trade.net_pnl_eur
            peak = max(peak, equity)
            drawdown = max(0.0, peak - equity)
            max_drawdown = max(max_drawdown, drawdown)
            if peak > 0.0:
                max_drawdown_pct = max(max_drawdown_pct, (drawdown / peak) * 100.0)
        return max_drawdown, max_drawdown_pct

    @staticmethod
    def _sharpe_like(returns: Sequence[float]) -> float | None:
        if len(returns) < 2:
            return None
        deviation = pstdev(returns)
        if deviation == 0.0:
            return None
        return (mean(returns) / deviation) * math.sqrt(len(returns))

    @staticmethod
    def _sortino_like(returns: Sequence[float]) -> float | None:
        if len(returns) < 2:
            return None
        downside = [value for value in returns if value < 0.0]
        if not downside:
            return None
        downside_deviation = math.sqrt(mean([value * value for value in downside]))
        if downside_deviation == 0.0:
            return None
        return (mean(returns) / downside_deviation) * math.sqrt(len(returns))

    def _performance_by_regime(self, trades: Sequence[TradeRecord]) -> dict[str, dict[str, Any]]:
        regimes = sorted({trade.regime or "unknown" for trade in trades})
        result: dict[str, dict[str, Any]] = {}
        for regime in regimes:
            subset = [trade for trade in trades if (trade.regime or "unknown") == regime]
            net = sum(trade.net_pnl_eur for trade in subset)
            wins = sum(1 for trade in subset if trade.net_pnl_eur > 0.0)
            result[regime] = {
                "trade_count": len(subset),
                "net_pnl_eur": net,
                "winrate_pct": (wins / len(subset) * 100.0) if subset else None,
                "expectancy_eur": (net / len(subset)) if subset else None,
            }
        return result
