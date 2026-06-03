"""Strict pre-trade risk manager for AUTOBOT validation and paper parity.

`RiskManagerV2` is intentionally side-effect free. It evaluates a proposed trade
against portfolio/risk state and returns a deterministic decision. It does not
submit orders, mutate positions, call Kraken, or change live trading flags.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class RiskManagerV2Config:
    default_risk_per_trade_pct: float = 0.005
    max_risk_per_trade_pct: float = 0.01
    max_symbol_exposure_pct: float = 0.20
    max_global_exposure_pct: float = 0.50
    max_order_notional_pct: float = 0.10
    max_open_trades: int = 10
    max_daily_loss_pct: float = 0.03
    max_drawdown_pct: float = 0.10
    max_consecutive_losses: int = 5
    min_order_notional_eur: float = 10.0
    max_spread_bps: float = 35.0
    max_volatility_bps: float = 300.0
    min_data_points: int = 64
    allow_leverage: bool = False
    max_leverage: float = 1.0
    forbid_martingale: bool = True
    allow_add_to_losing: bool = False
    kelly_enabled: bool = False
    kelly_min_validated_trades: int = 200
    kelly_fraction_cap: float = 0.25
    live_human_approved: bool = False

    def __post_init__(self) -> None:
        _require_pct(self.default_risk_per_trade_pct, "default_risk_per_trade_pct")
        _require_pct(self.max_risk_per_trade_pct, "max_risk_per_trade_pct")
        _require_pct(self.max_symbol_exposure_pct, "max_symbol_exposure_pct")
        _require_pct(self.max_global_exposure_pct, "max_global_exposure_pct")
        _require_pct(self.max_order_notional_pct, "max_order_notional_pct")
        if self.default_risk_per_trade_pct > self.max_risk_per_trade_pct:
            raise ValueError("default_risk_per_trade_pct cannot exceed max_risk_per_trade_pct")
        if self.max_open_trades <= 0:
            raise ValueError("max_open_trades must be positive")
        if self.max_consecutive_losses <= 0:
            raise ValueError("max_consecutive_losses must be positive")
        if self.min_order_notional_eur <= 0.0:
            raise ValueError("min_order_notional_eur must be positive")
        if self.max_spread_bps <= 0.0:
            raise ValueError("max_spread_bps must be positive")
        if self.max_volatility_bps <= 0.0:
            raise ValueError("max_volatility_bps must be positive")
        if self.min_data_points < 0:
            raise ValueError("min_data_points must not be negative")
        if self.max_leverage < 1.0:
            raise ValueError("max_leverage must be at least 1")
        if self.kelly_min_validated_trades <= 0:
            raise ValueError("kelly_min_validated_trades must be positive")
        _require_pct(self.kelly_fraction_cap, "kelly_fraction_cap")


@dataclass(frozen=True)
class RiskPortfolioState:
    equity_eur: float
    available_cash_eur: float
    open_trade_count: int = 0
    global_exposure_eur: float = 0.0
    symbol_exposure_eur: float = 0.0
    daily_realized_pnl_eur: float = 0.0
    peak_equity_eur: float | None = None
    consecutive_losses: int = 0
    validated_trade_count: int = 0
    spread_bps: float | None = None
    volatility_bps: float | None = None
    data_points: int = 0
    existing_position_unrealized_pnl_eur: float | None = None

    def __post_init__(self) -> None:
        if self.equity_eur <= 0.0 or not math.isfinite(self.equity_eur):
            raise ValueError("equity_eur must be positive and finite")
        if self.available_cash_eur < 0.0:
            raise ValueError("available_cash_eur must not be negative")
        if self.open_trade_count < 0:
            raise ValueError("open_trade_count must not be negative")
        if self.global_exposure_eur < 0.0:
            raise ValueError("global_exposure_eur must not be negative")
        if self.symbol_exposure_eur < 0.0:
            raise ValueError("symbol_exposure_eur must not be negative")
        if self.consecutive_losses < 0:
            raise ValueError("consecutive_losses must not be negative")
        if self.validated_trade_count < 0:
            raise ValueError("validated_trade_count must not be negative")
        if self.data_points < 0:
            raise ValueError("data_points must not be negative")


@dataclass(frozen=True)
class RiskTradeRequest:
    strategy_id: str
    symbol: str
    side: str
    entry_price: float
    stop_loss_price: float
    requested_notional_eur: float | None = None
    requested_quantity: float | None = None
    requested_risk_pct: float | None = None
    leverage: float = 1.0
    mode: str = "paper"
    order_type: str = "market"
    is_add_to_existing: bool = False
    use_kelly: bool = False
    kelly_fraction: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.strategy_id:
            raise ValueError("strategy_id must not be empty")
        if not self.symbol:
            raise ValueError("symbol must not be empty")
        if self.side.lower() not in {"long", "short", "buy", "sell"}:
            raise ValueError("side must be one of long/short/buy/sell")
        if self.entry_price <= 0.0 or not math.isfinite(self.entry_price):
            raise ValueError("entry_price must be positive and finite")
        if self.stop_loss_price <= 0.0 or not math.isfinite(self.stop_loss_price):
            raise ValueError("stop_loss_price must be positive and finite")
        if self.requested_notional_eur is not None and self.requested_notional_eur <= 0.0:
            raise ValueError("requested_notional_eur must be positive when provided")
        if self.requested_quantity is not None and self.requested_quantity <= 0.0:
            raise ValueError("requested_quantity must be positive when provided")
        if self.requested_risk_pct is not None:
            _require_pct(self.requested_risk_pct, "requested_risk_pct")
        if self.leverage < 1.0 or not math.isfinite(self.leverage):
            raise ValueError("leverage must be at least 1 and finite")
        if self.kelly_fraction is not None:
            _require_pct(self.kelly_fraction, "kelly_fraction")


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    reason: str
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    approved_notional_eur: float = 0.0
    approved_quantity: float = 0.0
    max_loss_eur: float = 0.0
    risk_pct: float = 0.0
    stop_distance_pct: float = 0.0
    exposure_after_eur: float = 0.0
    symbol_exposure_after_eur: float = 0.0
    effective_leverage: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["blockers"] = list(self.blockers)
        data["warnings"] = list(self.warnings)
        return data


class RiskManagerV2:
    """Evaluate proposed trades against strict paper/live-parity risk rules."""

    def __init__(self, config: RiskManagerV2Config | None = None) -> None:
        self.config = config or RiskManagerV2Config()

    def evaluate(self, request: RiskTradeRequest, state: RiskPortfolioState) -> RiskDecision:
        blockers: list[str] = []
        warnings: list[str] = []
        cfg = self.config

        mode = request.mode.strip().lower()
        if mode == "live" and not cfg.live_human_approved:
            blockers.append("live_requires_human_approval")
        elif mode not in {"paper", "shadow", "backtest", "replay", "live"}:
            blockers.append("unsupported_mode")

        stop_distance_pct = self._stop_distance_pct(request)
        if stop_distance_pct <= 0.0:
            blockers.append("invalid_stop_loss_for_side")

        if state.data_points < cfg.min_data_points:
            blockers.append("insufficient_market_data")
        if state.open_trade_count >= cfg.max_open_trades:
            blockers.append("max_open_trades_reached")
        if state.consecutive_losses >= cfg.max_consecutive_losses:
            blockers.append("consecutive_loss_pause")

        if state.daily_realized_pnl_eur <= -(state.equity_eur * cfg.max_daily_loss_pct):
            blockers.append("max_daily_loss_reached")
        peak = state.peak_equity_eur if state.peak_equity_eur is not None else state.equity_eur
        if peak > 0.0:
            drawdown_pct = max(0.0, (peak - state.equity_eur) / peak)
            if drawdown_pct >= cfg.max_drawdown_pct:
                blockers.append("max_drawdown_reached")

        if state.spread_bps is not None and state.spread_bps > cfg.max_spread_bps:
            blockers.append("spread_too_high")
        if state.volatility_bps is not None and state.volatility_bps > cfg.max_volatility_bps:
            blockers.append("volatility_too_high")

        if request.leverage > 1.0 and not cfg.allow_leverage:
            blockers.append("leverage_disabled")
        if request.leverage > cfg.max_leverage:
            blockers.append("leverage_above_limit")

        if cfg.forbid_martingale and request.is_add_to_existing and not cfg.allow_add_to_losing:
            if (state.existing_position_unrealized_pnl_eur or 0.0) < 0.0:
                blockers.append("add_to_losing_position_blocked")

        if request.use_kelly:
            if not cfg.kelly_enabled:
                blockers.append("kelly_disabled")
            elif state.validated_trade_count < cfg.kelly_min_validated_trades:
                blockers.append("kelly_insufficient_evidence")
            elif request.kelly_fraction is not None and request.kelly_fraction > cfg.kelly_fraction_cap:
                warnings.append("kelly_fraction_capped")

        if blockers:
            return RiskDecision(
                approved=False,
                reason=blockers[0],
                blockers=tuple(blockers),
                warnings=tuple(warnings),
                stop_distance_pct=max(0.0, stop_distance_pct),
                effective_leverage=request.leverage,
            )

        requested_notional = self._requested_notional(request)
        risk_pct = min(request.requested_risk_pct or cfg.default_risk_per_trade_pct, cfg.max_risk_per_trade_pct)
        risk_budget_eur = state.equity_eur * risk_pct
        max_by_risk = risk_budget_eur / stop_distance_pct
        max_by_order_cap = state.equity_eur * cfg.max_order_notional_pct
        max_by_symbol = max(0.0, state.equity_eur * cfg.max_symbol_exposure_pct - state.symbol_exposure_eur)
        max_by_global = max(0.0, state.equity_eur * cfg.max_global_exposure_pct - state.global_exposure_eur)
        max_by_cash = state.available_cash_eur if not cfg.allow_leverage else state.equity_eur * cfg.max_global_exposure_pct
        desired_notional = requested_notional or max_by_risk
        approved_notional = min(desired_notional, max_by_risk, max_by_order_cap, max_by_symbol, max_by_global, max_by_cash)

        cap_reasons = []
        if requested_notional is not None and approved_notional < requested_notional:
            cap_reasons.append("requested_notional_reduced")
        if approved_notional < max_by_risk:
            cap_reasons.append("exposure_or_cash_cap_applied")
        warnings.extend(cap_reasons)

        if approved_notional < cfg.min_order_notional_eur:
            return RiskDecision(
                approved=False,
                reason="approved_notional_below_min_order",
                blockers=("approved_notional_below_min_order",),
                warnings=tuple(warnings),
                approved_notional_eur=max(0.0, approved_notional),
                approved_quantity=max(0.0, approved_notional / request.entry_price),
                max_loss_eur=max(0.0, approved_notional * stop_distance_pct),
                risk_pct=risk_pct,
                stop_distance_pct=stop_distance_pct,
                exposure_after_eur=state.global_exposure_eur + max(0.0, approved_notional),
                symbol_exposure_after_eur=state.symbol_exposure_eur + max(0.0, approved_notional),
                effective_leverage=request.leverage,
            )

        max_loss_eur = approved_notional * stop_distance_pct
        return RiskDecision(
            approved=True,
            reason="approved",
            warnings=tuple(warnings),
            approved_notional_eur=approved_notional,
            approved_quantity=approved_notional / request.entry_price,
            max_loss_eur=max_loss_eur,
            risk_pct=risk_pct,
            stop_distance_pct=stop_distance_pct,
            exposure_after_eur=state.global_exposure_eur + approved_notional,
            symbol_exposure_after_eur=state.symbol_exposure_eur + approved_notional,
            effective_leverage=request.leverage,
        )

    @staticmethod
    def _stop_distance_pct(request: RiskTradeRequest) -> float:
        side = request.side.lower()
        if side in {"long", "buy"}:
            if request.stop_loss_price >= request.entry_price:
                return 0.0
            return (request.entry_price - request.stop_loss_price) / request.entry_price
        if request.stop_loss_price <= request.entry_price:
            return 0.0
        return (request.stop_loss_price - request.entry_price) / request.entry_price

    @staticmethod
    def _requested_notional(request: RiskTradeRequest) -> float | None:
        if request.requested_notional_eur is not None:
            return request.requested_notional_eur
        if request.requested_quantity is not None:
            return request.requested_quantity * request.entry_price
        return None


def _require_pct(value: float, name: str) -> None:
    if value <= 0.0 or value > 1.0 or not math.isfinite(value):
        raise ValueError(f"{name} must be in the interval (0, 1]")
