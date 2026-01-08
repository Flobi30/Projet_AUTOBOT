"""
AUTOBOT Risk Management Module

Comprehensive risk management including:
- Advanced risk manager with leverage, liquidation, and drawdown protection
- Meta-Learner for strategy orchestration
- Auto-healing system for fault recovery
"""

from autobot.risk.advanced_risk_manager import (
    AdvancedRiskManager,
    RiskLimits,
    RiskState,
    RiskLevel,
    TradingMode,
    RiskAlert,
    get_advanced_risk_manager,
)
from autobot.risk.meta_learner import (
    MetaLearner,
    StrategyPerformance,
    StrategyStatus,
    RiskProfile,
    AllocationDecision,
    get_meta_learner,
)
from autobot.risk.auto_healing import (
    AutoHealingSystem,
    ComponentHealth,
    ComponentStatus,
    RecoveryAction,
    RecoveryEvent,
    ConfigSnapshot,
    get_auto_healing_system,
)

__all__ = [
    # Advanced Risk Manager
    "AdvancedRiskManager",
    "RiskLimits",
    "RiskState",
    "RiskLevel",
    "TradingMode",
    "RiskAlert",
    "get_advanced_risk_manager",
    # Meta-Learner
    "MetaLearner",
    "StrategyPerformance",
    "StrategyStatus",
    "RiskProfile",
    "AllocationDecision",
    "get_meta_learner",
    # Auto-Healing
    "AutoHealingSystem",
    "ComponentHealth",
    "ComponentStatus",
    "RecoveryAction",
    "RecoveryEvent",
    "ConfigSnapshot",
    "get_auto_healing_system",
]
