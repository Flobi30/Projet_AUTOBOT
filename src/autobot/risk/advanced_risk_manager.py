"""
AUTOBOT Advanced Risk Manager

Comprehensive risk management system with:
- Leverage management and limits
- Liquidation protection
- Daily loss barriers
- Maximum drawdown protection
- Stop cascading prevention
- HF trading rate caps
- Circuit breakers
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any
import json
import os

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """Risk level classification"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class TradingMode(Enum):
    """Trading mode based on risk conditions"""
    NORMAL = "normal"
    REDUCED = "reduced"
    SAFE = "safe"
    HALTED = "halted"


@dataclass
class RiskLimits:
    """Risk limits configuration"""
    # Position limits
    max_position_size_pct: float = 10.0  # Max % of capital per position
    max_leverage: float = 3.0  # Maximum leverage allowed
    max_open_positions: int = 10  # Maximum concurrent positions
    
    # Loss limits
    max_daily_loss_pct: float = 5.0  # Max daily loss as % of capital
    max_weekly_loss_pct: float = 10.0  # Max weekly loss
    max_drawdown_pct: float = 20.0  # Max drawdown before halt
    
    # Trading frequency limits (HF protection)
    max_trades_per_minute: int = 10
    max_trades_per_hour: int = 100
    max_trades_per_day: int = 500
    
    # Cost limits
    max_cost_per_trade_pct: float = 0.5  # Max fees + slippage per trade
    max_daily_fees_pct: float = 2.0  # Max daily fees as % of capital
    
    # Slippage tolerance
    max_slippage_pct: float = 1.0  # Max acceptable slippage
    
    # Liquidation protection
    liquidation_buffer_pct: float = 20.0  # Buffer before liquidation price
    margin_call_threshold_pct: float = 50.0  # Margin level for warning
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_position_size_pct": self.max_position_size_pct,
            "max_leverage": self.max_leverage,
            "max_open_positions": self.max_open_positions,
            "max_daily_loss_pct": self.max_daily_loss_pct,
            "max_weekly_loss_pct": self.max_weekly_loss_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            "max_trades_per_minute": self.max_trades_per_minute,
            "max_trades_per_hour": self.max_trades_per_hour,
            "max_trades_per_day": self.max_trades_per_day,
            "max_cost_per_trade_pct": self.max_cost_per_trade_pct,
            "max_daily_fees_pct": self.max_daily_fees_pct,
            "max_slippage_pct": self.max_slippage_pct,
            "liquidation_buffer_pct": self.liquidation_buffer_pct,
            "margin_call_threshold_pct": self.margin_call_threshold_pct,
        }


@dataclass
class RiskState:
    """Current risk state"""
    current_capital: float = 0.0
    initial_capital: float = 0.0
    peak_capital: float = 0.0
    
    # Daily tracking
    daily_start_capital: float = 0.0
    daily_pnl: float = 0.0
    daily_fees: float = 0.0
    daily_trades: int = 0
    
    # Weekly tracking
    weekly_start_capital: float = 0.0
    weekly_pnl: float = 0.0
    
    # Drawdown tracking
    current_drawdown_pct: float = 0.0
    max_drawdown_reached_pct: float = 0.0
    
    # Position tracking
    open_positions: int = 0
    total_exposure: float = 0.0
    current_leverage: float = 0.0
    
    # Trading frequency tracking
    trades_this_minute: int = 0
    trades_this_hour: int = 0
    trades_this_day: int = 0
    last_trade_time: Optional[datetime] = None
    
    # Mode
    trading_mode: TradingMode = TradingMode.NORMAL
    risk_level: RiskLevel = RiskLevel.LOW
    
    # Timestamps
    last_daily_reset: Optional[datetime] = None
    last_weekly_reset: Optional[datetime] = None
    last_minute_reset: Optional[datetime] = None
    last_hour_reset: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "current_capital": self.current_capital,
            "initial_capital": self.initial_capital,
            "peak_capital": self.peak_capital,
            "daily_start_capital": self.daily_start_capital,
            "daily_pnl": self.daily_pnl,
            "daily_fees": self.daily_fees,
            "daily_trades": self.daily_trades,
            "weekly_start_capital": self.weekly_start_capital,
            "weekly_pnl": self.weekly_pnl,
            "current_drawdown_pct": self.current_drawdown_pct,
            "max_drawdown_reached_pct": self.max_drawdown_reached_pct,
            "open_positions": self.open_positions,
            "total_exposure": self.total_exposure,
            "current_leverage": self.current_leverage,
            "trades_this_minute": self.trades_this_minute,
            "trades_this_hour": self.trades_this_hour,
            "trades_this_day": self.trades_this_day,
            "last_trade_time": self.last_trade_time.isoformat() if self.last_trade_time else None,
            "trading_mode": self.trading_mode.value,
            "risk_level": self.risk_level.value,
        }


@dataclass
class RiskAlert:
    """Risk alert record"""
    alert_id: str
    timestamp: datetime
    level: RiskLevel
    category: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    acknowledged: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "timestamp": self.timestamp.isoformat(),
            "level": self.level.value,
            "category": self.category,
            "message": self.message,
            "details": self.details,
            "acknowledged": self.acknowledged,
        }


class AdvancedRiskManager:
    """
    Advanced Risk Manager for AUTOBOT.
    
    Provides comprehensive risk management including:
    - Leverage limits and monitoring
    - Liquidation protection
    - Daily/weekly loss barriers
    - Maximum drawdown protection
    - HF trading rate caps
    - Stop cascading prevention
    - Circuit breakers
    """
    
    def __init__(
        self,
        initial_capital: float,
        limits: Optional[RiskLimits] = None,
        data_dir: str = "/app/data",
    ):
        self.limits = limits or RiskLimits()
        self.data_dir = data_dir
        
        self.state = RiskState(
            current_capital=initial_capital,
            initial_capital=initial_capital,
            peak_capital=initial_capital,
            daily_start_capital=initial_capital,
            weekly_start_capital=initial_capital,
        )
        
        self.alerts: List[RiskAlert] = []
        self.alert_counter = 0
        
        # Circuit breaker state
        self.circuit_breaker_triggered = False
        self.circuit_breaker_reset_time: Optional[datetime] = None
        
        # Stop cascade tracking
        self.recent_stops: List[datetime] = []
        self.stop_cascade_threshold = 3  # 3 stops in 5 minutes = cascade
        self.stop_cascade_window = timedelta(minutes=5)
        
        # Initialize time tracking
        now = datetime.utcnow()
        self.state.last_daily_reset = now
        self.state.last_weekly_reset = now
        self.state.last_minute_reset = now
        self.state.last_hour_reset = now
        
        # Ensure data directory exists
        os.makedirs(data_dir, exist_ok=True)
        
        logger.info(f"Advanced Risk Manager initialized with {initial_capital} capital")
    
    # =========================================================================
    # Pre-Trade Validation
    # =========================================================================
    
    def validate_trade(
        self,
        symbol: str,
        side: str,
        size: float,
        entry_price: float,
        stop_loss: Optional[float] = None,
        leverage: float = 1.0,
        estimated_fees: float = 0.0,
        estimated_slippage: float = 0.0,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Validate a trade against all risk limits.
        
        Returns:
            Tuple of (is_valid, reason, details)
        """
        self._reset_counters_if_needed()
        
        details = {
            "checks_passed": [],
            "checks_failed": [],
            "warnings": [],
            "adjusted_size": size,
        }
        
        # Check trading mode
        if self.state.trading_mode == TradingMode.HALTED:
            return False, "Trading is halted due to risk limits", details
        
        # Check circuit breaker
        if self.circuit_breaker_triggered:
            if self.circuit_breaker_reset_time and datetime.utcnow() < self.circuit_breaker_reset_time:
                return False, f"Circuit breaker active until {self.circuit_breaker_reset_time}", details
            else:
                self._reset_circuit_breaker()
        
        # 1. Check leverage limit
        effective_leverage = leverage * (size * entry_price) / self.state.current_capital
        if effective_leverage > self.limits.max_leverage:
            details["checks_failed"].append(f"Leverage {effective_leverage:.2f}x exceeds max {self.limits.max_leverage}x")
            return False, "Leverage limit exceeded", details
        details["checks_passed"].append("leverage_limit")
        
        # 2. Check position size limit
        position_value = size * entry_price
        position_pct = (position_value / self.state.current_capital) * 100
        if position_pct > self.limits.max_position_size_pct:
            # Adjust size instead of rejecting
            max_size = (self.limits.max_position_size_pct / 100) * self.state.current_capital / entry_price
            details["adjusted_size"] = max_size
            details["warnings"].append(f"Position size reduced from {size} to {max_size}")
            size = max_size
        details["checks_passed"].append("position_size_limit")
        
        # 3. Check open positions limit
        if self.state.open_positions >= self.limits.max_open_positions:
            details["checks_failed"].append(f"Max open positions ({self.limits.max_open_positions}) reached")
            return False, "Maximum open positions reached", details
        details["checks_passed"].append("open_positions_limit")
        
        # 4. Check daily loss limit
        daily_loss_pct = abs(min(0, self.state.daily_pnl)) / self.state.daily_start_capital * 100
        if daily_loss_pct >= self.limits.max_daily_loss_pct:
            details["checks_failed"].append(f"Daily loss {daily_loss_pct:.2f}% exceeds max {self.limits.max_daily_loss_pct}%")
            return False, "Daily loss limit reached", details
        details["checks_passed"].append("daily_loss_limit")
        
        # 5. Check weekly loss limit
        weekly_loss_pct = abs(min(0, self.state.weekly_pnl)) / self.state.weekly_start_capital * 100
        if weekly_loss_pct >= self.limits.max_weekly_loss_pct:
            details["checks_failed"].append(f"Weekly loss {weekly_loss_pct:.2f}% exceeds max {self.limits.max_weekly_loss_pct}%")
            return False, "Weekly loss limit reached", details
        details["checks_passed"].append("weekly_loss_limit")
        
        # 6. Check drawdown limit
        if self.state.current_drawdown_pct >= self.limits.max_drawdown_pct:
            details["checks_failed"].append(f"Drawdown {self.state.current_drawdown_pct:.2f}% exceeds max {self.limits.max_drawdown_pct}%")
            return False, "Maximum drawdown reached", details
        details["checks_passed"].append("drawdown_limit")
        
        # 7. Check trading frequency (HF protection)
        if self.state.trades_this_minute >= self.limits.max_trades_per_minute:
            details["checks_failed"].append(f"Trades per minute ({self.state.trades_this_minute}) exceeds max ({self.limits.max_trades_per_minute})")
            return False, "Trading rate limit (per minute) exceeded", details
        
        if self.state.trades_this_hour >= self.limits.max_trades_per_hour:
            details["checks_failed"].append(f"Trades per hour ({self.state.trades_this_hour}) exceeds max ({self.limits.max_trades_per_hour})")
            return False, "Trading rate limit (per hour) exceeded", details
        
        if self.state.trades_this_day >= self.limits.max_trades_per_day:
            details["checks_failed"].append(f"Trades per day ({self.state.trades_this_day}) exceeds max ({self.limits.max_trades_per_day})")
            return False, "Trading rate limit (per day) exceeded", details
        details["checks_passed"].append("trading_frequency_limit")
        
        # 8. Check cost limits
        total_cost_pct = (estimated_fees + estimated_slippage) / (size * entry_price) * 100
        if total_cost_pct > self.limits.max_cost_per_trade_pct:
            details["warnings"].append(f"Trade cost {total_cost_pct:.2f}% exceeds recommended max {self.limits.max_cost_per_trade_pct}%")
        
        # 9. Check slippage tolerance
        slippage_pct = estimated_slippage / (size * entry_price) * 100
        if slippage_pct > self.limits.max_slippage_pct:
            details["checks_failed"].append(f"Slippage {slippage_pct:.2f}% exceeds max {self.limits.max_slippage_pct}%")
            return False, "Slippage tolerance exceeded", details
        details["checks_passed"].append("slippage_limit")
        
        # 10. Check liquidation buffer (if stop loss provided)
        if stop_loss and leverage > 1:
            if side.lower() == "buy":
                liquidation_price = entry_price * (1 - 1/leverage)
                buffer_pct = (stop_loss - liquidation_price) / entry_price * 100
            else:
                liquidation_price = entry_price * (1 + 1/leverage)
                buffer_pct = (liquidation_price - stop_loss) / entry_price * 100
            
            if buffer_pct < self.limits.liquidation_buffer_pct:
                details["warnings"].append(f"Stop loss is only {buffer_pct:.2f}% from liquidation price")
        
        # 11. Check stop cascade
        if self._is_stop_cascade_risk():
            details["warnings"].append("Stop cascade risk detected - consider reducing position size")
            details["adjusted_size"] = size * 0.5  # Reduce size by 50%
        
        # Update adjusted size in details
        details["adjusted_size"] = size
        
        return True, "Trade validated", details
    
    # =========================================================================
    # Trade Recording
    # =========================================================================
    
    def record_trade_open(
        self,
        symbol: str,
        side: str,
        size: float,
        entry_price: float,
        leverage: float = 1.0,
        fees: float = 0.0,
    ):
        """Record a new trade opening"""
        self._reset_counters_if_needed()
        
        # Update counters
        self.state.trades_this_minute += 1
        self.state.trades_this_hour += 1
        self.state.trades_this_day += 1
        self.state.daily_trades += 1
        self.state.open_positions += 1
        self.state.last_trade_time = datetime.utcnow()
        
        # Update exposure
        position_value = size * entry_price * leverage
        self.state.total_exposure += position_value
        self.state.current_leverage = self.state.total_exposure / self.state.current_capital
        
        # Update fees
        self.state.daily_fees += fees
        
        # Check if we need to change trading mode
        self._update_trading_mode()
        
        logger.info(f"Trade opened: {symbol} {side} {size} @ {entry_price} (leverage: {leverage}x)")
    
    def record_trade_close(
        self,
        symbol: str,
        side: str,
        size: float,
        entry_price: float,
        exit_price: float,
        leverage: float = 1.0,
        fees: float = 0.0,
        is_stop_loss: bool = False,
    ):
        """Record a trade closing"""
        # Calculate P&L
        if side.lower() == "buy":
            pnl = (exit_price - entry_price) * size * leverage
        else:
            pnl = (entry_price - exit_price) * size * leverage
        
        pnl -= fees  # Subtract fees
        
        # Update state
        self.state.open_positions = max(0, self.state.open_positions - 1)
        self.state.daily_pnl += pnl
        self.state.weekly_pnl += pnl
        self.state.daily_fees += fees
        
        # Update capital
        self.state.current_capital += pnl
        
        # Update peak and drawdown
        if self.state.current_capital > self.state.peak_capital:
            self.state.peak_capital = self.state.current_capital
        
        self.state.current_drawdown_pct = (
            (self.state.peak_capital - self.state.current_capital) / self.state.peak_capital * 100
        )
        self.state.max_drawdown_reached_pct = max(
            self.state.max_drawdown_reached_pct,
            self.state.current_drawdown_pct
        )
        
        # Update exposure
        position_value = size * entry_price * leverage
        self.state.total_exposure = max(0, self.state.total_exposure - position_value)
        self.state.current_leverage = (
            self.state.total_exposure / self.state.current_capital
            if self.state.current_capital > 0 else 0
        )
        
        # Track stop losses for cascade detection
        if is_stop_loss:
            self.recent_stops.append(datetime.utcnow())
            self._check_stop_cascade()
        
        # Check if we need to change trading mode
        self._update_trading_mode()
        
        # Generate alerts if needed
        self._check_and_generate_alerts()
        
        logger.info(f"Trade closed: {symbol} {side} {size} @ {exit_price} (P&L: {pnl:.2f})")
    
    # =========================================================================
    # Risk Monitoring
    # =========================================================================
    
    def get_risk_status(self) -> Dict[str, Any]:
        """Get current risk status"""
        self._reset_counters_if_needed()
        
        return {
            "state": self.state.to_dict(),
            "limits": self.limits.to_dict(),
            "trading_mode": self.state.trading_mode.value,
            "risk_level": self.state.risk_level.value,
            "circuit_breaker_active": self.circuit_breaker_triggered,
            "active_alerts": len([a for a in self.alerts if not a.acknowledged]),
            "daily_loss_pct": abs(min(0, self.state.daily_pnl)) / self.state.daily_start_capital * 100 if self.state.daily_start_capital > 0 else 0,
            "weekly_loss_pct": abs(min(0, self.state.weekly_pnl)) / self.state.weekly_start_capital * 100 if self.state.weekly_start_capital > 0 else 0,
            "available_risk_budget_pct": self._calculate_available_risk_budget(),
        }
    
    def get_alerts(self, unacknowledged_only: bool = False) -> List[Dict[str, Any]]:
        """Get risk alerts"""
        alerts = self.alerts
        if unacknowledged_only:
            alerts = [a for a in alerts if not a.acknowledged]
        return [a.to_dict() for a in alerts]
    
    def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge an alert"""
        for alert in self.alerts:
            if alert.alert_id == alert_id:
                alert.acknowledged = True
                return True
        return False
    
    # =========================================================================
    # Circuit Breaker
    # =========================================================================
    
    def trigger_circuit_breaker(self, reason: str, duration_minutes: int = 30):
        """Trigger the circuit breaker to halt trading"""
        self.circuit_breaker_triggered = True
        self.circuit_breaker_reset_time = datetime.utcnow() + timedelta(minutes=duration_minutes)
        self.state.trading_mode = TradingMode.HALTED
        
        self._create_alert(
            RiskLevel.EMERGENCY,
            "circuit_breaker",
            f"Circuit breaker triggered: {reason}. Trading halted for {duration_minutes} minutes.",
            {"reason": reason, "duration_minutes": duration_minutes}
        )
        
        logger.warning(f"Circuit breaker triggered: {reason}")
    
    def _reset_circuit_breaker(self):
        """Reset the circuit breaker"""
        self.circuit_breaker_triggered = False
        self.circuit_breaker_reset_time = None
        self._update_trading_mode()
        
        logger.info("Circuit breaker reset")
    
    # =========================================================================
    # Position Sizing
    # =========================================================================
    
    def calculate_safe_position_size(
        self,
        entry_price: float,
        stop_loss: float,
        leverage: float = 1.0,
        risk_pct: Optional[float] = None,
    ) -> float:
        """
        Calculate a safe position size based on current risk state.
        
        Args:
            entry_price: Entry price
            stop_loss: Stop loss price
            leverage: Leverage to use
            risk_pct: Risk percentage (uses default if not provided)
            
        Returns:
            Safe position size
        """
        # Use default risk or provided
        if risk_pct is None:
            risk_pct = 2.0  # Default 2% risk per trade
        
        # Adjust risk based on trading mode
        if self.state.trading_mode == TradingMode.REDUCED:
            risk_pct *= 0.5
        elif self.state.trading_mode == TradingMode.SAFE:
            risk_pct *= 0.25
        elif self.state.trading_mode == TradingMode.HALTED:
            return 0.0
        
        # Calculate risk amount
        risk_amount = self.state.current_capital * (risk_pct / 100)
        
        # Calculate stop distance
        stop_distance = abs(entry_price - stop_loss)
        stop_distance_pct = stop_distance / entry_price
        
        # Calculate position size
        position_size = risk_amount / (stop_distance * leverage)
        
        # Apply position size limit
        max_position_value = self.state.current_capital * (self.limits.max_position_size_pct / 100)
        max_size = max_position_value / entry_price
        
        position_size = min(position_size, max_size)
        
        # Check available risk budget
        available_budget = self._calculate_available_risk_budget()
        if available_budget < risk_pct:
            position_size *= (available_budget / risk_pct)
        
        return max(0, position_size)
    
    # =========================================================================
    # Internal Methods
    # =========================================================================
    
    def _reset_counters_if_needed(self):
        """Reset time-based counters if needed"""
        now = datetime.utcnow()
        
        # Reset minute counter
        if self.state.last_minute_reset and (now - self.state.last_minute_reset) >= timedelta(minutes=1):
            self.state.trades_this_minute = 0
            self.state.last_minute_reset = now
        
        # Reset hour counter
        if self.state.last_hour_reset and (now - self.state.last_hour_reset) >= timedelta(hours=1):
            self.state.trades_this_hour = 0
            self.state.last_hour_reset = now
        
        # Reset daily counters
        if self.state.last_daily_reset and (now - self.state.last_daily_reset) >= timedelta(days=1):
            self.state.daily_start_capital = self.state.current_capital
            self.state.daily_pnl = 0.0
            self.state.daily_fees = 0.0
            self.state.daily_trades = 0
            self.state.trades_this_day = 0
            self.state.last_daily_reset = now
        
        # Reset weekly counters
        if self.state.last_weekly_reset and (now - self.state.last_weekly_reset) >= timedelta(weeks=1):
            self.state.weekly_start_capital = self.state.current_capital
            self.state.weekly_pnl = 0.0
            self.state.last_weekly_reset = now
    
    def _update_trading_mode(self):
        """Update trading mode based on current risk state"""
        if self.circuit_breaker_triggered:
            self.state.trading_mode = TradingMode.HALTED
            self.state.risk_level = RiskLevel.EMERGENCY
            return
        
        # Check drawdown
        if self.state.current_drawdown_pct >= self.limits.max_drawdown_pct:
            self.state.trading_mode = TradingMode.HALTED
            self.state.risk_level = RiskLevel.EMERGENCY
            return
        
        # Check daily loss
        daily_loss_pct = abs(min(0, self.state.daily_pnl)) / self.state.daily_start_capital * 100 if self.state.daily_start_capital > 0 else 0
        
        if daily_loss_pct >= self.limits.max_daily_loss_pct:
            self.state.trading_mode = TradingMode.HALTED
            self.state.risk_level = RiskLevel.CRITICAL
            return
        
        # Determine mode based on risk levels
        if daily_loss_pct >= self.limits.max_daily_loss_pct * 0.8:
            self.state.trading_mode = TradingMode.SAFE
            self.state.risk_level = RiskLevel.HIGH
        elif daily_loss_pct >= self.limits.max_daily_loss_pct * 0.5:
            self.state.trading_mode = TradingMode.REDUCED
            self.state.risk_level = RiskLevel.MEDIUM
        else:
            self.state.trading_mode = TradingMode.NORMAL
            self.state.risk_level = RiskLevel.LOW
    
    def _calculate_available_risk_budget(self) -> float:
        """Calculate available risk budget as percentage"""
        # Start with max daily loss
        daily_loss_pct = abs(min(0, self.state.daily_pnl)) / self.state.daily_start_capital * 100 if self.state.daily_start_capital > 0 else 0
        available = self.limits.max_daily_loss_pct - daily_loss_pct
        
        # Also consider drawdown
        drawdown_budget = self.limits.max_drawdown_pct - self.state.current_drawdown_pct
        
        return max(0, min(available, drawdown_budget))
    
    def _is_stop_cascade_risk(self) -> bool:
        """Check if there's a risk of stop cascade"""
        now = datetime.utcnow()
        cutoff = now - self.stop_cascade_window
        
        # Clean old stops
        self.recent_stops = [s for s in self.recent_stops if s > cutoff]
        
        return len(self.recent_stops) >= self.stop_cascade_threshold - 1
    
    def _check_stop_cascade(self):
        """Check for stop cascade and trigger circuit breaker if needed"""
        now = datetime.utcnow()
        cutoff = now - self.stop_cascade_window
        
        # Clean old stops
        self.recent_stops = [s for s in self.recent_stops if s > cutoff]
        
        if len(self.recent_stops) >= self.stop_cascade_threshold:
            self.trigger_circuit_breaker(
                f"Stop cascade detected: {len(self.recent_stops)} stops in {self.stop_cascade_window.total_seconds()/60:.0f} minutes",
                duration_minutes=15
            )
    
    def _check_and_generate_alerts(self):
        """Check conditions and generate alerts"""
        # Daily loss warning
        daily_loss_pct = abs(min(0, self.state.daily_pnl)) / self.state.daily_start_capital * 100 if self.state.daily_start_capital > 0 else 0
        
        if daily_loss_pct >= self.limits.max_daily_loss_pct * 0.8:
            self._create_alert(
                RiskLevel.HIGH,
                "daily_loss",
                f"Daily loss at {daily_loss_pct:.2f}% - approaching limit of {self.limits.max_daily_loss_pct}%",
                {"daily_loss_pct": daily_loss_pct}
            )
        
        # Drawdown warning
        if self.state.current_drawdown_pct >= self.limits.max_drawdown_pct * 0.7:
            self._create_alert(
                RiskLevel.HIGH,
                "drawdown",
                f"Drawdown at {self.state.current_drawdown_pct:.2f}% - approaching limit of {self.limits.max_drawdown_pct}%",
                {"drawdown_pct": self.state.current_drawdown_pct}
            )
        
        # Leverage warning
        if self.state.current_leverage >= self.limits.max_leverage * 0.8:
            self._create_alert(
                RiskLevel.MEDIUM,
                "leverage",
                f"Leverage at {self.state.current_leverage:.2f}x - approaching limit of {self.limits.max_leverage}x",
                {"current_leverage": self.state.current_leverage}
            )
    
    def _create_alert(self, level: RiskLevel, category: str, message: str, details: Dict[str, Any]):
        """Create a new alert"""
        self.alert_counter += 1
        alert = RiskAlert(
            alert_id=f"alert_{self.alert_counter}",
            timestamp=datetime.utcnow(),
            level=level,
            category=category,
            message=message,
            details=details,
        )
        self.alerts.append(alert)
        
        # Keep only last 100 alerts
        if len(self.alerts) > 100:
            self.alerts = self.alerts[-100:]
        
        logger.warning(f"Risk Alert [{level.value}]: {message}")
    
    # =========================================================================
    # Persistence
    # =========================================================================
    
    def save_state(self):
        """Save current state to file"""
        state_file = os.path.join(self.data_dir, "risk_state.json")
        
        data = {
            "state": self.state.to_dict(),
            "limits": self.limits.to_dict(),
            "alerts": [a.to_dict() for a in self.alerts[-50:]],  # Keep last 50 alerts
            "saved_at": datetime.utcnow().isoformat(),
        }
        
        with open(state_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"Risk state saved to {state_file}")
    
    def load_state(self) -> bool:
        """Load state from file"""
        state_file = os.path.join(self.data_dir, "risk_state.json")
        
        if not os.path.exists(state_file):
            return False
        
        try:
            with open(state_file, 'r') as f:
                data = json.load(f)
            
            # Restore state (partial - some fields need special handling)
            state_data = data.get("state", {})
            self.state.current_capital = state_data.get("current_capital", self.state.current_capital)
            self.state.peak_capital = state_data.get("peak_capital", self.state.peak_capital)
            self.state.max_drawdown_reached_pct = state_data.get("max_drawdown_reached_pct", 0)
            
            logger.info(f"Risk state loaded from {state_file}")
            return True
            
        except Exception as e:
            logger.error(f"Error loading risk state: {e}")
            return False


# Singleton instance
_risk_manager_instance: Optional[AdvancedRiskManager] = None


def get_advanced_risk_manager(
    initial_capital: float = 10000.0,
    limits: Optional[RiskLimits] = None,
    data_dir: str = "/app/data",
) -> AdvancedRiskManager:
    """Get or create the singleton AdvancedRiskManager instance"""
    global _risk_manager_instance
    
    if _risk_manager_instance is None:
        _risk_manager_instance = AdvancedRiskManager(
            initial_capital=initial_capital,
            limits=limits,
            data_dir=data_dir,
        )
    
    return _risk_manager_instance
