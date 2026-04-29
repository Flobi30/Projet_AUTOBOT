"""Paper-first quantitative validation sensors for AUTOBOT.

This module exposes lightweight, dependency-free checks inspired by common
quant research practice.  They are observability tools: they do not place
orders, do not unlock live trading, and do not modify execution thresholds.
"""

from __future__ import annotations

import math
import os
import sqlite3
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float, minimum: float, maximum: float) -> float:
    raw = os.getenv(name)
    try:
        value = float(raw) if raw not in (None, "") else default
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    try:
        value = int(raw) if raw not in (None, "") else default
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _env_int_list(name: str, default: Sequence[int], minimum: int, maximum: int) -> tuple[int, ...]:
    raw = os.getenv(name)
    if raw in (None, ""):
        values = list(default)
    else:
        values = []
        for chunk in str(raw).split(","):
            try:
                values.append(int(chunk.strip()))
            except (TypeError, ValueError):
                continue
    cleaned = sorted({max(minimum, min(maximum, value)) for value in values if value > 0})
    return tuple(cleaned or default)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_timestamp(value: Any) -> float:
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    if not value:
        return 0.0
    raw = str(value)
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        return 0.0


def _stddev(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return math.sqrt(max(0.0, variance))


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


@dataclass(frozen=True)
class VolatilityForecastConfig:
    enabled: bool = True
    windows: tuple[int, ...] = (16, 32, 64)
    min_samples: int = 20
    ewma_lambda: float = 0.94
    garch_alpha: float = 0.10
    garch_beta: float = 0.85
    garch_floor_bps: float = 2.0
    low_bps: float = 8.0
    high_bps: float = 60.0
    extreme_bps: float = 160.0

    @classmethod
    def from_env(cls) -> "VolatilityForecastConfig":
        return cls(
            enabled=_env_bool("VOL_FORECAST_ENABLED", True),
            windows=_env_int_list("VOL_FORECAST_WINDOWS", (16, 32, 64), 4, 1000),
            min_samples=_env_int("VOL_FORECAST_MIN_SAMPLES", 20, 4, 5000),
            ewma_lambda=_env_float("VOL_FORECAST_EWMA_LAMBDA", 0.94, 0.50, 0.999),
            garch_alpha=_env_float("VOL_FORECAST_GARCH_ALPHA", 0.10, 0.0, 0.50),
            garch_beta=_env_float("VOL_FORECAST_GARCH_BETA", 0.85, 0.0, 0.999),
            garch_floor_bps=_env_float("VOL_FORECAST_GARCH_FLOOR_BPS", 2.0, 0.0, 1000.0),
            low_bps=_env_float("VOL_FORECAST_LOW_BPS", 8.0, 0.0, 5000.0),
            high_bps=_env_float("VOL_FORECAST_HIGH_BPS", 60.0, 0.1, 5000.0),
            extreme_bps=_env_float("VOL_FORECAST_EXTREME_BPS", 160.0, 0.1, 10000.0),
        )


@dataclass
class VolatilityForecastResult:
    symbol: str
    state: str
    sample_count: int
    forecast_vol_bps: float
    ewma_vol_bps: float
    realized_vol_bps: dict[str, float]
    trend_bps: float
    confidence: float
    reason: str
    enabled: bool = True
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "state": self.state,
            "sample_count": self.sample_count,
            "forecast_vol_bps": round(self.forecast_vol_bps, 3),
            "ewma_vol_bps": round(self.ewma_vol_bps, 3),
            "realized_vol_bps": {key: round(value, 3) for key, value in self.realized_vol_bps.items()},
            "trend_bps": round(self.trend_bps, 3),
            "confidence": round(self.confidence, 4),
            "reason": self.reason,
            "enabled": self.enabled,
            "timestamp": self.timestamp,
        }


class VolatilityForecastEngine:
    """Estimate realized and next-step volatility from runtime price history."""

    def __init__(self, config: VolatilityForecastConfig | None = None) -> None:
        self.config = config or VolatilityForecastConfig.from_env()

    def analyze_symbol(self, symbol: str, price_history: Iterable[Any] | None) -> VolatilityForecastResult:
        prices = self._extract_prices(price_history)
        returns_bps = self._log_returns_bps(prices)
        sample_count = len(returns_bps)
        if not self.config.enabled:
            return self._neutral(symbol, sample_count, "disabled", enabled=False)
        if sample_count < self.config.min_samples:
            return self._neutral(symbol, sample_count, "insufficient_samples")

        realized = {
            str(window): _stddev(returns_bps[-window:])
            for window in self.config.windows
            if len(returns_bps[-window:]) >= 2
        }
        ewma_var = self._ewma_variance(returns_bps)
        garch_var = self._garch_like_variance(returns_bps)
        ewma_vol = math.sqrt(max(0.0, ewma_var))
        forecast_vol = math.sqrt(max(0.0, garch_var))
        trend_window = returns_bps[-min(16, sample_count):]
        trend_bps = sum(trend_window) / max(len(trend_window), 1)
        state, reason = self._state_from_forecast(forecast_vol, realized)
        confidence = min(1.0, sample_count / max(self.config.min_samples * 3, 1))

        return VolatilityForecastResult(
            symbol=symbol,
            state=state,
            sample_count=sample_count,
            forecast_vol_bps=forecast_vol,
            ewma_vol_bps=ewma_vol,
            realized_vol_bps=realized,
            trend_bps=trend_bps,
            confidence=confidence,
            reason=reason,
            enabled=True,
        )

    def analyze_instance(self, instance: Mapping[str, Any]) -> VolatilityForecastResult:
        symbol = str(instance.get("symbol") or instance.get("pair") or "UNKNOWN")
        history = instance.get("price_history_tail") or instance.get("price_history") or []
        return self.analyze_symbol(symbol, history)

    def build_snapshot(self, *, instances: Iterable[Mapping[str, Any]], paper_mode: bool) -> dict[str, Any]:
        symbols = [self.analyze_instance(instance).to_dict() for instance in instances]
        symbols.sort(key=lambda row: row.get("forecast_vol_bps", 0.0), reverse=True)
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": "paper" if paper_mode else "live",
            "paper_mode": paper_mode,
            "config": {
                "enabled": self.config.enabled,
                "windows": list(self.config.windows),
                "min_samples": self.config.min_samples,
                "ewma_lambda": self.config.ewma_lambda,
                "garch_alpha": self.config.garch_alpha,
                "garch_beta": self.config.garch_beta,
                "low_bps": self.config.low_bps,
                "high_bps": self.config.high_bps,
                "extreme_bps": self.config.extreme_bps,
            },
            "symbols": symbols,
        }

    def _neutral(
        self,
        symbol: str,
        sample_count: int,
        reason: str,
        *,
        enabled: bool = True,
    ) -> VolatilityForecastResult:
        return VolatilityForecastResult(
            symbol=symbol,
            state="unknown",
            sample_count=sample_count,
            forecast_vol_bps=0.0,
            ewma_vol_bps=0.0,
            realized_vol_bps={},
            trend_bps=0.0,
            confidence=0.0,
            reason=reason,
            enabled=enabled,
        )

    def _state_from_forecast(self, forecast_vol: float, realized: Mapping[str, float]) -> tuple[str, str]:
        if forecast_vol >= self.config.extreme_bps:
            return "extreme", "forecast_extreme_volatility"
        if forecast_vol >= self.config.high_bps:
            return "high", "forecast_high_volatility"
        if forecast_vol <= self.config.low_bps:
            return "low", "forecast_low_volatility"
        short_window = min((int(key) for key in realized.keys()), default=0)
        long_window = max((int(key) for key in realized.keys()), default=0)
        if short_window and long_window and realized[str(short_window)] > realized[str(long_window)] * 1.35:
            return "rising", "short_term_volatility_rising"
        return "normal", "forecast_normal_volatility"

    def _ewma_variance(self, returns_bps: Sequence[float]) -> float:
        lam = self.config.ewma_lambda
        variance = max(self.config.garch_floor_bps ** 2, _stddev(returns_bps[: min(16, len(returns_bps))]) ** 2)
        for ret in returns_bps:
            variance = lam * variance + (1.0 - lam) * (ret ** 2)
        return max(0.0, variance)

    def _garch_like_variance(self, returns_bps: Sequence[float]) -> float:
        alpha = self.config.garch_alpha
        beta = self.config.garch_beta
        persistence = min(alpha + beta, 0.999)
        floor_var = self.config.garch_floor_bps ** 2
        omega = floor_var * max(0.0, 1.0 - persistence)
        variance = max(floor_var, _stddev(returns_bps[: min(32, len(returns_bps))]) ** 2)
        for ret in returns_bps:
            variance = omega + alpha * (ret ** 2) + beta * variance
        return max(floor_var, variance)

    @staticmethod
    def _extract_prices(price_history: Iterable[Any] | None) -> list[float]:
        prices: list[float] = []
        for item in price_history or []:
            value: Any
            if isinstance(item, Mapping):
                value = (
                    item.get("price")
                    or item.get("close")
                    or item.get("value")
                    or item.get("last_price")
                    or item.get("current_price")
                )
            else:
                value = item
            price = _safe_float(value, 0.0)
            if price > 0.0:
                prices.append(price)
        return prices

    @staticmethod
    def _log_returns_bps(prices: Sequence[float]) -> list[float]:
        returns: list[float] = []
        for previous, current in zip(prices, prices[1:]):
            if previous > 0.0 and current > 0.0:
                returns.append(math.log(current / previous) * 10000.0)
        return returns


@dataclass(frozen=True)
class BacktestQualityConfig:
    enabled: bool = True
    min_trades: int = 30
    pbo_folds: int = 4
    trials: int = 20
    pbo_caution: float = 0.30
    pbo_block: float = 0.50
    dsr_min_probability: float = 0.50

    @classmethod
    def from_env(cls) -> "BacktestQualityConfig":
        return cls(
            enabled=_env_bool("QUANT_VALIDATION_ENABLED", True),
            min_trades=_env_int("BACKTEST_QUALITY_MIN_TRADES", 30, 5, 10000),
            pbo_folds=_env_int("BACKTEST_QUALITY_PBO_FOLDS", 4, 2, 20),
            trials=_env_int("BACKTEST_QUALITY_TRIALS", 20, 1, 100000),
            pbo_caution=_env_float("BACKTEST_QUALITY_PBO_CAUTION", 0.30, 0.0, 1.0),
            pbo_block=_env_float("BACKTEST_QUALITY_PBO_BLOCK", 0.50, 0.0, 1.0),
            dsr_min_probability=_env_float("BACKTEST_QUALITY_DSR_MIN_PROBABILITY", 0.50, 0.0, 1.0),
        )


@dataclass
class TradeObservation:
    symbol: str
    side: str
    volume: float
    price: float
    fees: float
    timestamp: str
    realized_pnl: float | None = None
    is_closing_leg: bool = False
    source: str = "unknown"

    @property
    def notional(self) -> float:
        return abs(self.volume * self.price)


@dataclass
class RealizedTradeResult:
    symbol: str
    pnl_eur: float
    return_pct: float
    timestamp: str
    source: str


class BacktestQualityEngine:
    """Evaluate whether paper results are trustworthy enough to consider live."""

    def __init__(self, config: BacktestQualityConfig | None = None) -> None:
        self.config = config or BacktestQualityConfig.from_env()

    def build_snapshot(
        self,
        *,
        trades: Iterable[TradeObservation],
        capital_base: float,
        paper_mode: bool,
    ) -> dict[str, Any]:
        observations = sorted(list(trades), key=lambda trade: _parse_timestamp(trade.timestamp))
        realized = self._realized_results(observations)
        returns = [item.return_pct for item in realized]
        pnls = [item.pnl_eur for item in realized]
        metrics = self._metrics(returns, pnls, max(capital_base, 1.0))
        pbo = self._pbo_proxy(returns)
        dsr = self._deflated_sharpe_proxy(returns, metrics["sharpe"])
        status, recommendation = self._status(metrics, pbo, dsr)
        by_symbol = self._by_symbol(realized)

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": "paper" if paper_mode else "live",
            "paper_mode": paper_mode,
            "enabled": self.config.enabled,
            "status": status,
            "recommendation": recommendation,
            "method": {
                "pbo": "folded_proxy_not_cpcv",
                "dsr": "selection_adjusted_proxy",
                "note": "Operational validation signal only; not a guarantee of future returns.",
            },
            "config": {
                "min_trades": self.config.min_trades,
                "pbo_folds": self.config.pbo_folds,
                "trials": self.config.trials,
                "pbo_caution": self.config.pbo_caution,
                "pbo_block": self.config.pbo_block,
                "dsr_min_probability": self.config.dsr_min_probability,
            },
            "sample": {
                "executions_count": len(observations),
                "realized_trade_count": len(realized),
                "min_trades": self.config.min_trades,
                "sources": sorted({trade.source for trade in observations}),
            },
            "metrics": metrics,
            "pbo": pbo,
            "dsr": dsr,
            "by_symbol": by_symbol,
        }

    def _realized_results(self, trades: Sequence[TradeObservation]) -> list[RealizedTradeResult]:
        realized: list[RealizedTradeResult] = []
        lots: dict[str, deque[tuple[float, float, float]]] = defaultdict(deque)

        for trade in trades:
            side = trade.side.lower()
            if trade.realized_pnl is not None and (trade.is_closing_leg or side in {"sell", "close"}):
                notional = max(trade.notional, 1.0)
                realized.append(
                    RealizedTradeResult(
                        symbol=trade.symbol,
                        pnl_eur=float(trade.realized_pnl),
                        return_pct=float(trade.realized_pnl) / notional,
                        timestamp=trade.timestamp,
                        source=trade.source,
                    )
                )
                continue

            if side == "buy":
                lots[trade.symbol].append((trade.volume, trade.price, trade.fees))
                continue
            if side != "sell":
                continue

            remaining = trade.volume
            sell_fee_left = trade.fees
            while remaining > 0.0 and lots[trade.symbol]:
                buy_volume, buy_price, buy_fee = lots[trade.symbol].popleft()
                matched = min(remaining, buy_volume)
                buy_fee_part = buy_fee * (matched / max(buy_volume, 1e-12))
                sell_fee_part = sell_fee_left * (matched / max(trade.volume, 1e-12))
                pnl = (trade.price - buy_price) * matched - buy_fee_part - sell_fee_part
                basis = max(buy_price * matched + buy_fee_part, 1.0)
                realized.append(
                    RealizedTradeResult(
                        symbol=trade.symbol,
                        pnl_eur=pnl,
                        return_pct=pnl / basis,
                        timestamp=trade.timestamp,
                        source=trade.source,
                    )
                )
                remaining -= matched
                sell_fee_left = max(0.0, sell_fee_left - sell_fee_part)
                if buy_volume > matched:
                    lots[trade.symbol].appendleft((buy_volume - matched, buy_price, buy_fee - buy_fee_part))

        return realized

    def _metrics(self, returns: Sequence[float], pnls: Sequence[float], capital_base: float) -> dict[str, Any]:
        trade_count = len(returns)
        wins = [pnl for pnl in pnls if pnl > 0.0]
        losses = [pnl for pnl in pnls if pnl < 0.0]
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        profit_factor = gross_profit / gross_loss if gross_loss > 0.0 else (999.0 if gross_profit > 0.0 else 0.0)
        mean_ret = sum(returns) / trade_count if trade_count else 0.0
        std_ret = _stddev(returns)
        sharpe = (mean_ret / std_ret * math.sqrt(trade_count)) if std_ret > 0.0 and trade_count > 1 else 0.0
        cumulative = 0.0
        peak = capital_base
        max_dd_eur = 0.0
        for pnl in pnls:
            cumulative += pnl
            equity = capital_base + cumulative
            peak = max(peak, equity)
            max_dd_eur = max(max_dd_eur, peak - equity)
        max_dd_pct = max_dd_eur / peak if peak > 0.0 else 0.0
        return {
            "trade_count": trade_count,
            "net_pnl_eur": round(sum(pnls), 4),
            "gross_profit_eur": round(gross_profit, 4),
            "gross_loss_eur": round(gross_loss, 4),
            "profit_factor": round(profit_factor, 4),
            "win_rate": round(len(wins) / trade_count, 4) if trade_count else 0.0,
            "avg_return_pct": round(mean_ret * 100.0, 4),
            "vol_return_pct": round(std_ret * 100.0, 4),
            "sharpe": round(sharpe, 4),
            "max_drawdown_eur": round(max_dd_eur, 4),
            "max_drawdown_pct": round(max_dd_pct * 100.0, 4),
        }

    def _pbo_proxy(self, returns: Sequence[float]) -> dict[str, Any]:
        if len(returns) < self.config.min_trades or len(returns) < self.config.pbo_folds * 3:
            return {
                "status": "insufficient_data",
                "probability": None,
                "folds": self.config.pbo_folds,
                "reason": "not_enough_realized_trades",
            }
        folds = self._folds(returns, self.config.pbo_folds)
        events = 0
        tested = 0
        for index, oos in enumerate(folds):
            train = [value for fold_index, fold in enumerate(folds) if fold_index != index for value in fold]
            train_sharpe = self._simple_sharpe(train)
            oos_sharpe = self._simple_sharpe(oos)
            if train_sharpe > 0.0:
                tested += 1
                if oos_sharpe <= 0.0 or oos_sharpe < train_sharpe * 0.25:
                    events += 1
        probability = events / tested if tested else 0.0
        if probability >= self.config.pbo_block:
            status = "high_overfit_risk"
        elif probability >= self.config.pbo_caution:
            status = "caution"
        else:
            status = "acceptable"
        return {
            "status": status,
            "probability": round(probability, 4),
            "folds": len(folds),
            "events": events,
            "tested": tested,
            "reason": "proxy_train_oos_degradation",
        }

    def _deflated_sharpe_proxy(self, returns: Sequence[float], sharpe: float) -> dict[str, Any]:
        count = len(returns)
        if count < self.config.min_trades or count < 4:
            return {
                "status": "insufficient_data",
                "probability": None,
                "deflated_sharpe_z": None,
                "reason": "not_enough_realized_trades",
            }
        mean = sum(returns) / count
        std = _stddev(returns)
        if std <= 0.0:
            return {
                "status": "flat_returns",
                "probability": 0.0,
                "deflated_sharpe_z": None,
                "reason": "zero_return_variance",
            }
        centered = [(value - mean) / std for value in returns]
        skew = sum(value ** 3 for value in centered) / count
        kurtosis = sum(value ** 4 for value in centered) / count
        denom = max(1e-9, 1.0 - skew * sharpe + ((kurtosis - 1.0) / 4.0) * sharpe ** 2)
        standard_error = math.sqrt(denom / max(count - 1, 1))
        selection_penalty = math.sqrt(2.0 * math.log(max(self.config.trials, 1))) / max(math.sqrt(count), 1.0)
        z_score = (sharpe - selection_penalty) / max(standard_error, 1e-9)
        probability = _normal_cdf(z_score)
        status = "acceptable" if probability >= self.config.dsr_min_probability else "weak"
        return {
            "status": status,
            "probability": round(probability, 4),
            "deflated_sharpe_z": round(z_score, 4),
            "selection_penalty": round(selection_penalty, 4),
            "skew": round(skew, 4),
            "kurtosis": round(kurtosis, 4),
            "reason": "selection_and_nonnormality_adjusted_proxy",
        }

    def _status(self, metrics: Mapping[str, Any], pbo: Mapping[str, Any], dsr: Mapping[str, Any]) -> tuple[str, str]:
        if not self.config.enabled:
            return "disabled", "Validation quant desactivee."
        if int(metrics.get("trade_count") or 0) < self.config.min_trades:
            return "learning", "En attente de trades paper clotures pour juger la robustesse."
        pbo_prob = pbo.get("probability")
        dsr_prob = dsr.get("probability")
        if isinstance(pbo_prob, (int, float)) and pbo_prob >= self.config.pbo_block:
            return "unsafe", "Risque de surapprentissage eleve, ne pas promouvoir."
        if isinstance(dsr_prob, (int, float)) and dsr_prob < self.config.dsr_min_probability:
            return "weak", "Sharpe deflate insuffisant, rester en paper."
        if float(metrics.get("profit_factor") or 0.0) <= 1.0:
            return "weak", "Profit factor net insuffisant, rester en paper."
        return "candidate", "Resultats paper prometteurs, validation humaine encore requise avant live."

    @staticmethod
    def _simple_sharpe(values: Sequence[float]) -> float:
        if len(values) < 2:
            return 0.0
        std = _stddev(values)
        return (sum(values) / len(values)) / std if std > 0.0 else 0.0

    @staticmethod
    def _folds(values: Sequence[float], count: int) -> list[list[float]]:
        count = max(2, min(count, len(values)))
        folds: list[list[float]] = [[] for _ in range(count)]
        for index, value in enumerate(values):
            folds[index % count].append(value)
        return [fold for fold in folds if fold]

    @staticmethod
    def _by_symbol(results: Sequence[RealizedTradeResult]) -> list[dict[str, Any]]:
        grouped: dict[str, list[RealizedTradeResult]] = defaultdict(list)
        for result in results:
            grouped[result.symbol].append(result)
        rows = []
        for symbol, values in grouped.items():
            pnls = [value.pnl_eur for value in values]
            wins = sum(1 for pnl in pnls if pnl > 0.0)
            rows.append(
                {
                    "symbol": symbol,
                    "trade_count": len(values),
                    "net_pnl_eur": round(sum(pnls), 4),
                    "win_rate": round(wins / len(values), 4) if values else 0.0,
                    "avg_pnl_eur": round(sum(pnls) / len(values), 4) if values else 0.0,
                }
            )
        rows.sort(key=lambda row: row["net_pnl_eur"], reverse=True)
        return rows


def load_paper_trade_observations(db_path: Any) -> list[TradeObservation]:
    path = Path(str(db_path)) if db_path else Path("data/paper_trades.db")
    if not path.exists():
        return []
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            rows = conn.execute(
                """
                SELECT symbol, side, volume, price, fees, timestamp, status
                FROM trades
                WHERE status IN ('filled', 'closed')
                ORDER BY timestamp ASC, created_at ASC
                """
            ).fetchall()
        finally:
            conn.close()
    except Exception:
        return []
    return [
        TradeObservation(
            symbol=str(row[0] or "UNKNOWN"),
            side=str(row[1] or "").lower(),
            volume=_safe_float(row[2]),
            price=_safe_float(row[3]),
            fees=_safe_float(row[4]),
            timestamp=str(row[5] or ""),
            source="paper_trades_db",
        )
        for row in rows
        if _safe_float(row[2]) > 0.0 and _safe_float(row[3]) > 0.0
    ]


def load_trade_ledger_observations(db_path: Any) -> list[TradeObservation]:
    path = Path(str(db_path)) if db_path else Path("data/autobot_state.db")
    if not path.exists():
        return []
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='trade_ledger'"
            ).fetchone()
            if not row:
                return []
            rows = conn.execute(
                """
                SELECT symbol, side, volume, executed_price, fees, created_at, realized_pnl, is_closing_leg
                FROM trade_ledger
                ORDER BY created_at ASC
                """
            ).fetchall()
        finally:
            conn.close()
    except Exception:
        return []
    return [
        TradeObservation(
            symbol=str(row[0] or "UNKNOWN"),
            side=str(row[1] or "").lower(),
            volume=_safe_float(row[2]),
            price=_safe_float(row[3]),
            fees=_safe_float(row[4]),
            timestamp=str(row[5] or ""),
            realized_pnl=None if row[6] is None else _safe_float(row[6]),
            is_closing_leg=bool(row[7]),
            source="trade_ledger",
        )
        for row in rows
        if _safe_float(row[2]) > 0.0 and _safe_float(row[3]) > 0.0
    ]


class QuantValidationEngine:
    """Build the combined validation snapshot used by API and dashboard."""

    def __init__(
        self,
        volatility: VolatilityForecastEngine | None = None,
        backtest_quality: BacktestQualityEngine | None = None,
    ) -> None:
        self.volatility = volatility or VolatilityForecastEngine()
        self.backtest_quality = backtest_quality or BacktestQualityEngine()

    def build_snapshot(
        self,
        *,
        instances: Iterable[Mapping[str, Any]],
        trades: Iterable[TradeObservation],
        paper_mode: bool,
        capital_base: float,
    ) -> dict[str, Any]:
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": "paper" if paper_mode else "live",
            "paper_mode": paper_mode,
            "live_shadow_policy": self._live_shadow_policy(paper_mode=paper_mode),
            "volatility": self.volatility.build_snapshot(instances=instances, paper_mode=paper_mode),
            "backtest_quality": self.backtest_quality.build_snapshot(
                trades=trades,
                capital_base=capital_base,
                paper_mode=paper_mode,
            ),
        }

    @staticmethod
    def _live_shadow_policy(*, paper_mode: bool) -> dict[str, Any]:
        live_ack = _env_bool("LIVE_TRADING_CONFIRMATION", False)
        live_selection = _env_bool("OPPORTUNITY_SELECTION_LIVE_ENABLED", False)
        live_stage = os.getenv("DEPLOYMENT_STAGE", "paper")
        shadow_enabled = _env_bool("ENABLE_SHADOW_TRADING", True)
        shadow_continue = _env_bool("SHADOW_TRADING_CONTINUE_IN_LIVE", True)
        live_execution_enabled = (not paper_mode) and live_ack and live_selection and live_stage != "paper"
        return {
            "paper_shadow_continues_in_live": bool(shadow_enabled and shadow_continue),
            "shadow_trading_enabled": shadow_enabled,
            "shadow_continue_in_live": shadow_continue,
            "live_execution_enabled": bool(live_execution_enabled),
            "live_selection_enabled": live_selection,
            "live_confirmation": live_ack,
            "deployment_stage": live_stage,
            "message": (
                "Paper/shadow validation remains active alongside live gates."
                if shadow_enabled and shadow_continue
                else "Shadow validation is disabled by configuration."
            ),
        }
