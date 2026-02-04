"""
Risk Manager Module for AUTOBOT Grid Trading Engine.

Implements risk controls including:
- Global stop loss (-20% of capital)
- Daily loss limit (-50€)
- Emergency stop (close all positions)
- Position size limits
- Exposure monitoring
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Callable

from .grid_calculator import GridCalculator
from .order_manager import GridOrderManager
from .position_tracker import PositionTracker, TradeType, GridSide

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """Risk level classification."""
    NORMAL = "normal"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class RiskAlertType(Enum):
    """Type of risk alert."""
    DAILY_LOSS_WARNING = "daily_loss_warning"
    DAILY_LOSS_LIMIT = "daily_loss_limit"
    GLOBAL_STOP_WARNING = "global_stop_warning"
    GLOBAL_STOP_TRIGGERED = "global_stop_triggered"
    DRAWDOWN_WARNING = "drawdown_warning"
    EXPOSURE_WARNING = "exposure_warning"
    EMERGENCY_STOP = "emergency_stop"
    POSITION_SIZE_EXCEEDED = "position_size_exceeded"


@dataclass
class RiskAlert:
    """
    Represents a risk alert.
    
    Attributes:
        alert_id: Unique identifier
        alert_type: Type of alert
        level: Risk level
        message: Alert message
        current_value: Current value that triggered alert
        threshold: Threshold that was exceeded
        timestamp: Alert timestamp
        acknowledged: Whether alert has been acknowledged
    """
    alert_id: str
    alert_type: RiskAlertType
    level: RiskLevel
    message: str
    current_value: float
    threshold: float
    timestamp: datetime = field(default_factory=datetime.utcnow)
    acknowledged: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "alert_id": self.alert_id,
            "alert_type": self.alert_type.value,
            "level": self.level.value,
            "message": self.message,
            "current_value": self.current_value,
            "threshold": self.threshold,
            "timestamp": self.timestamp.isoformat(),
            "acknowledged": self.acknowledged,
        }


@dataclass
class RiskStatus:
    """
    Current risk status summary.
    
    Attributes:
        level: Overall risk level
        daily_pnl: Today's P&L
        daily_loss_limit: Daily loss limit
        daily_loss_percent: Daily loss as percentage of limit
        total_pnl: Total P&L
        total_pnl_percent: Total P&L as percentage of capital
        global_stop_percent: Distance to global stop as percentage
        max_drawdown: Maximum drawdown percentage
        exposure: Current exposure as percentage of capital
        is_trading_allowed: Whether trading is currently allowed
        active_alerts: Number of active alerts
    """
    level: RiskLevel
    daily_pnl: float
    daily_loss_limit: float
    daily_loss_percent: float
    total_pnl: float
    total_pnl_percent: float
    global_stop_percent: float
    max_drawdown: float
    exposure: float
    is_trading_allowed: bool
    active_alerts: int
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "level": self.level.value,
            "daily_pnl": round(self.daily_pnl, 2),
            "daily_loss_limit": self.daily_loss_limit,
            "daily_loss_percent": round(self.daily_loss_percent, 1),
            "total_pnl": round(self.total_pnl, 2),
            "total_pnl_percent": round(self.total_pnl_percent, 2),
            "global_stop_percent": round(self.global_stop_percent, 2),
            "max_drawdown": round(self.max_drawdown, 2),
            "exposure": round(self.exposure, 2),
            "is_trading_allowed": self.is_trading_allowed,
            "active_alerts": self.active_alerts,
        }


class GridRiskManager:
    """
    Manages risk for grid trading strategy.
    
    Risk Controls:
    - Global stop loss: -20% of initial capital triggers full close
    - Daily loss limit: -50€ stops trading for the day
    - Emergency stop: Manual trigger to close all positions
    - Exposure limits: Maximum position size controls
    
    Example:
        risk_manager = GridRiskManager(
            initial_capital=500.0,
            global_stop_percent=20.0,
            daily_loss_limit=50.0
        )
        
        # Check risk before trading
        if risk_manager.is_trading_allowed():
            # Execute trade
            pass
        
        # Update and check risk
        status = risk_manager.check_risk()
        if status.level == RiskLevel.EMERGENCY:
            await risk_manager.emergency_stop()
    """
    
    def __init__(
        self,
        initial_capital: float,
        global_stop_percent: float = 20.0,
        daily_loss_limit: float = 50.0,
        max_drawdown_percent: float = 25.0,
        max_exposure_percent: float = 100.0,
        warning_threshold_percent: float = 50.0,
        position_tracker: Optional[PositionTracker] = None,
        order_manager: Optional[GridOrderManager] = None
    ):
        """
        Initialize risk manager.
        
        Args:
            initial_capital: Starting capital
            global_stop_percent: Global stop loss percentage (default: 20%)
            daily_loss_limit: Maximum daily loss in currency (default: 50€)
            max_drawdown_percent: Maximum allowed drawdown (default: 25%)
            max_exposure_percent: Maximum exposure as % of capital (default: 100%)
            warning_threshold_percent: Threshold for warnings (default: 50%)
            position_tracker: PositionTracker instance
            order_manager: GridOrderManager instance
        """
        self.initial_capital = initial_capital
        self.global_stop_percent = global_stop_percent
        self.daily_loss_limit = daily_loss_limit
        self.max_drawdown_percent = max_drawdown_percent
        self.max_exposure_percent = max_exposure_percent
        self.warning_threshold = warning_threshold_percent
        
        self.position_tracker = position_tracker
        self.order_manager = order_manager
        
        self._global_stop_amount = initial_capital * (global_stop_percent / 100)
        self._is_trading_allowed = True
        self._is_emergency_stopped = False
        self._daily_trading_paused = False
        self._last_daily_reset: datetime = datetime.utcnow().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        
        self._alerts: List[RiskAlert] = []
        self._alert_count = 0
        
        self._on_alert_callbacks: List[Callable] = []
        self._on_stop_callbacks: List[Callable] = []
        
        logger.info(
            f"GridRiskManager initialized: capital={initial_capital}€, "
            f"global_stop={global_stop_percent}%, daily_limit={daily_loss_limit}€"
        )
    
    @property
    def alerts(self) -> List[RiskAlert]:
        """Get all alerts."""
        return self._alerts
    
    @property
    def active_alerts(self) -> List[RiskAlert]:
        """Get unacknowledged alerts."""
        return [a for a in self._alerts if not a.acknowledged]
    
    @property
    def is_emergency_stopped(self) -> bool:
        """Check if emergency stop is active."""
        return self._is_emergency_stopped
    
    def on_alert(self, callback: Callable) -> None:
        """Register callback for risk alerts."""
        self._on_alert_callbacks.append(callback)
    
    def on_stop(self, callback: Callable) -> None:
        """Register callback for stop events."""
        self._on_stop_callbacks.append(callback)
    
    def is_trading_allowed(self) -> bool:
        """
        Check if trading is currently allowed.
        
        Returns:
            True if trading is allowed
        """
        if self._is_emergency_stopped:
            return False
        
        if self._daily_trading_paused:
            self._check_daily_reset()
            if self._daily_trading_paused:
                return False
        
        return self._is_trading_allowed
    
    def _check_daily_reset(self) -> None:
        """Check if daily limits should be reset."""
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        if today_start > self._last_daily_reset:
            self._daily_trading_paused = False
            self._last_daily_reset = today_start
            logger.info("Daily trading limits reset")
    
    def check_risk(self) -> RiskStatus:
        """
        Check current risk status.
        
        Returns:
            RiskStatus with current risk metrics
        """
        self._check_daily_reset()
        
        daily_pnl = 0.0
        total_pnl = 0.0
        max_drawdown = 0.0
        exposure = 0.0
        
        if self.position_tracker:
            daily_pnl = self.position_tracker.get_today_pnl()
            total_pnl = self.position_tracker.total_pnl
            max_drawdown = self.position_tracker.max_drawdown
            
            total_position_value = sum(
                p.market_value for p in self.position_tracker.open_positions
            )
            exposure = (total_position_value / self.initial_capital) * 100
        
        daily_loss_percent = 0.0
        if self.daily_loss_limit > 0:
            daily_loss_percent = (abs(min(0, daily_pnl)) / self.daily_loss_limit) * 100
        
        total_pnl_percent = (total_pnl / self.initial_capital) * 100
        
        global_stop_distance = self.global_stop_percent + total_pnl_percent
        
        level = self._calculate_risk_level(
            daily_loss_percent=daily_loss_percent,
            total_pnl_percent=total_pnl_percent,
            max_drawdown=max_drawdown,
            exposure=exposure
        )
        
        self._check_and_create_alerts(
            daily_pnl=daily_pnl,
            daily_loss_percent=daily_loss_percent,
            total_pnl_percent=total_pnl_percent,
            max_drawdown=max_drawdown,
            exposure=exposure
        )
        
        return RiskStatus(
            level=level,
            daily_pnl=daily_pnl,
            daily_loss_limit=self.daily_loss_limit,
            daily_loss_percent=daily_loss_percent,
            total_pnl=total_pnl,
            total_pnl_percent=total_pnl_percent,
            global_stop_percent=global_stop_distance,
            max_drawdown=max_drawdown,
            exposure=exposure,
            is_trading_allowed=self.is_trading_allowed(),
            active_alerts=len(self.active_alerts),
        )
    
    def _calculate_risk_level(
        self,
        daily_loss_percent: float,
        total_pnl_percent: float,
        max_drawdown: float,
        exposure: float
    ) -> RiskLevel:
        """Calculate overall risk level."""
        if self._is_emergency_stopped:
            return RiskLevel.EMERGENCY
        
        if total_pnl_percent <= -self.global_stop_percent:
            return RiskLevel.EMERGENCY
        
        if daily_loss_percent >= 100:
            return RiskLevel.CRITICAL
        
        if max_drawdown >= self.max_drawdown_percent:
            return RiskLevel.CRITICAL
        
        if (daily_loss_percent >= self.warning_threshold or
            total_pnl_percent <= -(self.global_stop_percent * 0.5) or
            max_drawdown >= self.max_drawdown_percent * 0.7):
            return RiskLevel.WARNING
        
        return RiskLevel.NORMAL
    
    def _check_and_create_alerts(
        self,
        daily_pnl: float,
        daily_loss_percent: float,
        total_pnl_percent: float,
        max_drawdown: float,
        exposure: float
    ) -> None:
        """Check conditions and create alerts if needed."""
        import uuid
        
        if daily_loss_percent >= 100 and not self._daily_trading_paused:
            self._daily_trading_paused = True
            self._create_alert(
                alert_type=RiskAlertType.DAILY_LOSS_LIMIT,
                level=RiskLevel.CRITICAL,
                message=f"Daily loss limit reached: {daily_pnl:.2f}€",
                current_value=daily_pnl,
                threshold=-self.daily_loss_limit
            )
        elif daily_loss_percent >= self.warning_threshold:
            self._create_alert(
                alert_type=RiskAlertType.DAILY_LOSS_WARNING,
                level=RiskLevel.WARNING,
                message=f"Daily loss warning: {daily_pnl:.2f}€ ({daily_loss_percent:.0f}% of limit)",
                current_value=daily_pnl,
                threshold=-self.daily_loss_limit * (self.warning_threshold / 100)
            )
        
        if total_pnl_percent <= -self.global_stop_percent:
            self._is_trading_allowed = False
            self._create_alert(
                alert_type=RiskAlertType.GLOBAL_STOP_TRIGGERED,
                level=RiskLevel.EMERGENCY,
                message=f"Global stop triggered: {total_pnl_percent:.2f}% loss",
                current_value=total_pnl_percent,
                threshold=-self.global_stop_percent
            )
        elif total_pnl_percent <= -(self.global_stop_percent * 0.7):
            self._create_alert(
                alert_type=RiskAlertType.GLOBAL_STOP_WARNING,
                level=RiskLevel.WARNING,
                message=f"Approaching global stop: {total_pnl_percent:.2f}% loss",
                current_value=total_pnl_percent,
                threshold=-(self.global_stop_percent * 0.7)
            )
        
        if max_drawdown >= self.max_drawdown_percent * 0.8:
            self._create_alert(
                alert_type=RiskAlertType.DRAWDOWN_WARNING,
                level=RiskLevel.WARNING,
                message=f"High drawdown: {max_drawdown:.2f}%",
                current_value=max_drawdown,
                threshold=self.max_drawdown_percent * 0.8
            )
        
        if exposure > self.max_exposure_percent:
            self._create_alert(
                alert_type=RiskAlertType.EXPOSURE_WARNING,
                level=RiskLevel.WARNING,
                message=f"Exposure exceeded: {exposure:.2f}%",
                current_value=exposure,
                threshold=self.max_exposure_percent
            )
    
    def _create_alert(
        self,
        alert_type: RiskAlertType,
        level: RiskLevel,
        message: str,
        current_value: float,
        threshold: float
    ) -> RiskAlert:
        """Create and store a risk alert."""
        import uuid
        
        recent_same_type = [
            a for a in self._alerts[-10:]
            if a.alert_type == alert_type and
            (datetime.utcnow() - a.timestamp).total_seconds() < 300
        ]
        if recent_same_type:
            return recent_same_type[-1]
        
        alert = RiskAlert(
            alert_id=str(uuid.uuid4()),
            alert_type=alert_type,
            level=level,
            message=message,
            current_value=current_value,
            threshold=threshold,
        )
        
        self._alerts.append(alert)
        self._alert_count += 1
        
        if len(self._alerts) > 100:
            self._alerts = self._alerts[-100:]
        
        for callback in self._on_alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                logger.error(f"Alert callback error: {e}")
        
        logger.warning(f"Risk alert: {message}")
        
        return alert
    
    def acknowledge_alert(self, alert_id: str) -> bool:
        """
        Acknowledge a risk alert.
        
        Args:
            alert_id: Alert ID to acknowledge
            
        Returns:
            True if alert was found and acknowledged
        """
        for alert in self._alerts:
            if alert.alert_id == alert_id:
                alert.acknowledged = True
                return True
        return False
    
    def acknowledge_all_alerts(self) -> int:
        """
        Acknowledge all active alerts.
        
        Returns:
            Number of alerts acknowledged
        """
        count = 0
        for alert in self.active_alerts:
            alert.acknowledged = True
            count += 1
        return count
    
    async def emergency_stop(self, reason: str = "Manual emergency stop") -> Dict[str, Any]:
        """
        Execute emergency stop - close all positions and cancel all orders.
        
        Args:
            reason: Reason for emergency stop
            
        Returns:
            Dictionary with results
        """
        self._is_emergency_stopped = True
        self._is_trading_allowed = False
        
        self._create_alert(
            alert_type=RiskAlertType.EMERGENCY_STOP,
            level=RiskLevel.EMERGENCY,
            message=f"Emergency stop activated: {reason}",
            current_value=0,
            threshold=0
        )
        
        logger.critical(f"EMERGENCY STOP: {reason}")
        
        results = {
            "reason": reason,
            "timestamp": datetime.utcnow().isoformat(),
            "orders_canceled": 0,
            "positions_closed": 0,
            "realized_pnl": 0.0,
        }
        
        if self.order_manager:
            canceled = await self.order_manager.cancel_all_orders()
            results["orders_canceled"] = canceled
        
        if self.position_tracker:
            current_price = self.position_tracker.current_price
            
            for position in list(self.position_tracker.open_positions):
                trade = self.position_tracker.record_trade(
                    trade_type=TradeType.EMERGENCY_CLOSE,
                    side=GridSide.SELL,
                    quantity=position.quantity,
                    price=current_price,
                    level_id=position.level_id,
                )
                results["positions_closed"] += 1
                results["realized_pnl"] += trade.profit
        
        for callback in self._on_stop_callbacks:
            try:
                await callback(results)
            except Exception as e:
                logger.error(f"Stop callback error: {e}")
        
        logger.info(
            f"Emergency stop completed: canceled={results['orders_canceled']}, "
            f"closed={results['positions_closed']}, pnl={results['realized_pnl']:.2f}"
        )
        
        return results
    
    def reset_emergency_stop(self) -> bool:
        """
        Reset emergency stop to allow trading again.
        
        Returns:
            True if reset successful
        """
        if not self._is_emergency_stopped:
            return False
        
        self._is_emergency_stopped = False
        self._is_trading_allowed = True
        
        logger.info("Emergency stop reset - trading allowed")
        return True
    
    def reset_daily_limit(self) -> bool:
        """
        Manually reset daily trading limit.
        
        Returns:
            True if reset successful
        """
        self._daily_trading_paused = False
        self._last_daily_reset = datetime.utcnow()
        
        logger.info("Daily trading limit manually reset")
        return True
    
    def validate_order(
        self,
        quantity: float,
        price: float,
        side: GridSide
    ) -> tuple:
        """
        Validate if an order is allowed under current risk rules.
        
        Args:
            quantity: Order quantity
            price: Order price
            side: Order side
            
        Returns:
            Tuple of (is_valid: bool, reason: str or None)
        """
        if not self.is_trading_allowed():
            return (False, "Trading not allowed - check risk status")
        
        order_value = quantity * price
        
        if self.position_tracker:
            current_exposure = sum(
                p.market_value for p in self.position_tracker.open_positions
            )
            
            if side == GridSide.BUY:
                new_exposure = current_exposure + order_value
            else:
                new_exposure = current_exposure - order_value
            
            exposure_percent = (new_exposure / self.initial_capital) * 100
            
            if exposure_percent > self.max_exposure_percent:
                return (False, f"Order would exceed max exposure ({exposure_percent:.1f}%)")
        
        max_order_value = self.initial_capital * 0.2  # 20% max per order
        if order_value > max_order_value:
            return (False, f"Order value {order_value:.2f}€ exceeds maximum {max_order_value:.2f}€")
        
        return (True, None)
    
    def get_status(self) -> Dict[str, Any]:
        """Get risk manager status."""
        risk_status = self.check_risk()
        
        return {
            "risk_status": risk_status.to_dict(),
            "initial_capital": self.initial_capital,
            "global_stop_percent": self.global_stop_percent,
            "global_stop_amount": self._global_stop_amount,
            "daily_loss_limit": self.daily_loss_limit,
            "max_drawdown_percent": self.max_drawdown_percent,
            "max_exposure_percent": self.max_exposure_percent,
            "is_trading_allowed": self.is_trading_allowed(),
            "is_emergency_stopped": self._is_emergency_stopped,
            "daily_trading_paused": self._daily_trading_paused,
            "total_alerts": len(self._alerts),
            "active_alerts": len(self.active_alerts),
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert risk manager state to dictionary."""
        return {
            "status": self.get_status(),
            "alerts": [a.to_dict() for a in self._alerts[-20:]],
        }
