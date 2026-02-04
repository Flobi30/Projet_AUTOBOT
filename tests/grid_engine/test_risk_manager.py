"""
Tests for Risk Manager Module.
"""

import pytest
from datetime import datetime, timedelta

import sys
sys.path.insert(0, '/home/ubuntu/repos/Projet_AUTOBOT/src')

from grid_engine.grid_calculator import GridSide
from grid_engine.position_tracker import PositionTracker, TradeType
from grid_engine.risk_manager import (
    GridRiskManager,
    RiskStatus,
    RiskAlert,
    RiskLevel,
    RiskAlertType,
)


class TestRiskLevel:
    """Tests for RiskLevel enum."""
    
    def test_values(self):
        """Test enum values."""
        assert RiskLevel.NORMAL.value == "normal"
        assert RiskLevel.WARNING.value == "warning"
        assert RiskLevel.CRITICAL.value == "critical"
        assert RiskLevel.EMERGENCY.value == "emergency"


class TestRiskAlertType:
    """Tests for RiskAlertType enum."""
    
    def test_values(self):
        """Test enum values."""
        assert RiskAlertType.DAILY_LOSS_WARNING.value == "daily_loss_warning"
        assert RiskAlertType.DAILY_LOSS_LIMIT.value == "daily_loss_limit"
        assert RiskAlertType.GLOBAL_STOP_TRIGGERED.value == "global_stop_triggered"
        assert RiskAlertType.EMERGENCY_STOP.value == "emergency_stop"


class TestRiskAlert:
    """Tests for RiskAlert dataclass."""
    
    def test_alert_creation(self):
        """Test alert creation."""
        alert = RiskAlert(
            alert_id="alert-001",
            alert_type=RiskAlertType.DAILY_LOSS_WARNING,
            level=RiskLevel.WARNING,
            message="Daily loss warning: -25€",
            current_value=-25.0,
            threshold=-50.0,
        )
        
        assert alert.alert_id == "alert-001"
        assert alert.alert_type == RiskAlertType.DAILY_LOSS_WARNING
        assert alert.level == RiskLevel.WARNING
        assert alert.acknowledged == False
    
    def test_to_dict(self):
        """Test alert serialization."""
        alert = RiskAlert(
            alert_id="alert-001",
            alert_type=RiskAlertType.DAILY_LOSS_WARNING,
            level=RiskLevel.WARNING,
            message="Daily loss warning",
            current_value=-25.0,
            threshold=-50.0,
        )
        
        result = alert.to_dict()
        
        assert result["alert_id"] == "alert-001"
        assert result["alert_type"] == "daily_loss_warning"
        assert result["level"] == "warning"


class TestRiskStatus:
    """Tests for RiskStatus dataclass."""
    
    def test_status_creation(self):
        """Test status creation."""
        status = RiskStatus(
            level=RiskLevel.NORMAL,
            daily_pnl=10.0,
            daily_loss_limit=50.0,
            daily_loss_percent=0.0,
            total_pnl=50.0,
            total_pnl_percent=10.0,
            global_stop_percent=30.0,
            max_drawdown=5.0,
            exposure=50.0,
            is_trading_allowed=True,
            active_alerts=0,
        )
        
        assert status.level == RiskLevel.NORMAL
        assert status.is_trading_allowed == True
    
    def test_to_dict(self):
        """Test status serialization."""
        status = RiskStatus(
            level=RiskLevel.NORMAL,
            daily_pnl=10.0,
            daily_loss_limit=50.0,
            daily_loss_percent=0.0,
            total_pnl=50.0,
            total_pnl_percent=10.0,
            global_stop_percent=30.0,
            max_drawdown=5.0,
            exposure=50.0,
            is_trading_allowed=True,
            active_alerts=0,
        )
        
        result = status.to_dict()
        
        assert result["level"] == "normal"
        assert result["is_trading_allowed"] == True


class TestGridRiskManager:
    """Tests for GridRiskManager class."""
    
    @pytest.fixture
    def position_tracker(self):
        """Create test position tracker."""
        return PositionTracker(
            symbol="BTC/USDT",
            initial_capital=500.0
        )
    
    @pytest.fixture
    def risk_manager(self, position_tracker):
        """Create test risk manager."""
        return GridRiskManager(
            initial_capital=500.0,
            global_stop_percent=20.0,
            daily_loss_limit=50.0,
            position_tracker=position_tracker
        )
    
    def test_initialization(self, risk_manager):
        """Test risk manager initialization."""
        assert risk_manager.initial_capital == 500.0
        assert risk_manager.global_stop_percent == 20.0
        assert risk_manager.daily_loss_limit == 50.0
        assert risk_manager._global_stop_amount == 100.0
    
    def test_is_trading_allowed_default(self, risk_manager):
        """Test trading is allowed by default."""
        assert risk_manager.is_trading_allowed() == True
    
    def test_check_risk_normal(self, risk_manager):
        """Test risk check returns normal status."""
        status = risk_manager.check_risk()
        
        assert status.level == RiskLevel.NORMAL
        assert status.is_trading_allowed == True
    
    def test_daily_loss_limit_trigger(self, risk_manager, position_tracker):
        """Test daily loss limit triggers trading pause."""
        position_tracker.record_trade(
            trade_type=TradeType.GRID_BUY,
            side=GridSide.BUY,
            quantity=0.001,
            price=50000.0,
            level_id=5,
        )
        position_tracker.record_trade(
            trade_type=TradeType.GRID_SELL,
            side=GridSide.SELL,
            quantity=0.001,
            price=45000.0,
            level_id=5,
        )
        
        status = risk_manager.check_risk()
        
        if status.daily_loss_percent >= 100:
            assert status.level in [RiskLevel.CRITICAL, RiskLevel.EMERGENCY]
    
    def test_global_stop_calculation(self, risk_manager):
        """Test global stop amount calculation."""
        expected = 500.0 * 0.20
        assert risk_manager._global_stop_amount == expected
    
    @pytest.mark.asyncio
    async def test_emergency_stop(self, risk_manager):
        """Test emergency stop execution."""
        result = await risk_manager.emergency_stop("Test emergency")
        
        assert risk_manager.is_emergency_stopped == True
        assert risk_manager.is_trading_allowed() == False
        assert "reason" in result
        assert result["reason"] == "Test emergency"
    
    def test_reset_emergency_stop(self, risk_manager):
        """Test emergency stop reset."""
        risk_manager._is_emergency_stopped = True
        risk_manager._is_trading_allowed = False
        
        success = risk_manager.reset_emergency_stop()
        
        assert success == True
        assert risk_manager.is_emergency_stopped == False
        assert risk_manager.is_trading_allowed() == True
    
    def test_reset_daily_limit(self, risk_manager):
        """Test daily limit reset."""
        risk_manager._daily_trading_paused = True
        
        success = risk_manager.reset_daily_limit()
        
        assert success == True
        assert risk_manager._daily_trading_paused == False
    
    def test_validate_order_allowed(self, risk_manager):
        """Test order validation when trading allowed."""
        is_valid, reason = risk_manager.validate_order(
            quantity=0.001,
            price=50000.0,
            side=GridSide.BUY
        )
        
        assert is_valid == True
        assert reason is None
    
    def test_validate_order_trading_not_allowed(self, risk_manager):
        """Test order validation when trading not allowed."""
        risk_manager._is_emergency_stopped = True
        
        is_valid, reason = risk_manager.validate_order(
            quantity=0.001,
            price=50000.0,
            side=GridSide.BUY
        )
        
        assert is_valid == False
        assert reason is not None
    
    def test_validate_order_exceeds_max(self, risk_manager):
        """Test order validation when order too large."""
        is_valid, reason = risk_manager.validate_order(
            quantity=10.0,
            price=50000.0,
            side=GridSide.BUY
        )
        
        assert is_valid == False
        assert "exceeds maximum" in reason
    
    def test_acknowledge_alert(self, risk_manager):
        """Test alert acknowledgment."""
        alert = RiskAlert(
            alert_id="alert-001",
            alert_type=RiskAlertType.DAILY_LOSS_WARNING,
            level=RiskLevel.WARNING,
            message="Test alert",
            current_value=-25.0,
            threshold=-50.0,
        )
        risk_manager._alerts.append(alert)
        
        success = risk_manager.acknowledge_alert("alert-001")
        
        assert success == True
        assert alert.acknowledged == True
    
    def test_acknowledge_all_alerts(self, risk_manager):
        """Test acknowledging all alerts."""
        for i in range(3):
            alert = RiskAlert(
                alert_id=f"alert-{i}",
                alert_type=RiskAlertType.DAILY_LOSS_WARNING,
                level=RiskLevel.WARNING,
                message=f"Test alert {i}",
                current_value=-25.0,
                threshold=-50.0,
            )
            risk_manager._alerts.append(alert)
        
        count = risk_manager.acknowledge_all_alerts()
        
        assert count == 3
        assert len(risk_manager.active_alerts) == 0
    
    def test_callback_registration(self, risk_manager):
        """Test callback registration."""
        callback_called = []
        
        def on_alert(alert):
            callback_called.append(alert)
        
        risk_manager.on_alert(on_alert)
        
        assert len(risk_manager._on_alert_callbacks) == 1
    
    def test_get_status(self, risk_manager):
        """Test status retrieval."""
        status = risk_manager.get_status()
        
        assert "risk_status" in status
        assert "initial_capital" in status
        assert "global_stop_percent" in status
        assert "daily_loss_limit" in status
        assert "is_trading_allowed" in status
    
    def test_to_dict(self, risk_manager):
        """Test full serialization."""
        result = risk_manager.to_dict()
        
        assert "status" in result
        assert "alerts" in result
    
    def test_risk_level_calculation_warning(self, risk_manager, position_tracker):
        """Test warning level calculation."""
        position_tracker.record_trade(
            trade_type=TradeType.GRID_BUY,
            side=GridSide.BUY,
            quantity=0.001,
            price=50000.0,
            level_id=5,
        )
        position_tracker.record_trade(
            trade_type=TradeType.GRID_SELL,
            side=GridSide.SELL,
            quantity=0.001,
            price=49500.0,
            level_id=5,
        )
        
        status = risk_manager.check_risk()
        
        assert status.level in [RiskLevel.NORMAL, RiskLevel.WARNING]
    
    def test_daily_reset_check(self, risk_manager):
        """Test daily limit reset check."""
        risk_manager._daily_trading_paused = True
        risk_manager._last_daily_reset = datetime.utcnow() - timedelta(days=2)
        
        risk_manager._check_daily_reset()
        
        assert risk_manager._daily_trading_paused == False
