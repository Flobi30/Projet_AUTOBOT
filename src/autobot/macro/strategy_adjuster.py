"""
AUTOBOT Macro Strategy Adjuster

Adjusts trading strategies based on macro-economic conditions:
- Reduces exposure during dangerous macro periods
- Reinforces signals when macro validates trends
- Adjusts risk parameters based on regime
"""

import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime

from autobot.macro.regime import RegimeDetector, RegimeState, MarketRegime
from autobot.macro.indicators import MacroIndicatorManager

logger = logging.getLogger(__name__)


@dataclass
class StrategyAdjustment:
    """Adjustment recommendations for trading strategy"""
    position_size_multiplier: float  # 0.0 to 1.5
    leverage_cap: float  # Maximum allowed leverage
    trade_frequency_multiplier: float  # 0.0 to 1.5
    stop_loss_tightening: float  # 0.8 to 1.2 (< 1 = tighter stops)
    take_profit_adjustment: float  # 0.8 to 1.2
    asset_class_weights: Dict[str, float]  # Adjustments per asset class
    reason: str
    confidence: float
    timestamp: datetime
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "position_size_multiplier": self.position_size_multiplier,
            "leverage_cap": self.leverage_cap,
            "trade_frequency_multiplier": self.trade_frequency_multiplier,
            "stop_loss_tightening": self.stop_loss_tightening,
            "take_profit_adjustment": self.take_profit_adjustment,
            "asset_class_weights": self.asset_class_weights,
            "reason": self.reason,
            "confidence": self.confidence,
            "timestamp": self.timestamp.isoformat(),
        }


class MacroStrategyAdjuster:
    """
    Adjusts trading strategies based on macro-economic analysis.
    
    Integrates with:
    - Risk management (leverage, position sizing)
    - Trade frequency planning
    - Asset allocation
    - Stop-loss/take-profit levels
    """
    
    # Default safe parameters
    DEFAULT_LEVERAGE_CAP = 3.0
    SAFE_MODE_LEVERAGE_CAP = 1.0
    
    def __init__(
        self,
        indicator_manager: Optional[MacroIndicatorManager] = None,
        regime_detector: Optional[RegimeDetector] = None,
    ):
        self.indicator_manager = indicator_manager or MacroIndicatorManager()
        self.regime_detector = regime_detector or RegimeDetector()
        self.current_adjustment: Optional[StrategyAdjustment] = None
        self.safe_mode = False
    
    def analyze_and_adjust(self) -> StrategyAdjustment:
        """
        Analyze current macro conditions and generate strategy adjustments.
        
        Returns:
            StrategyAdjustment with recommended parameter changes
        """
        # Get current indicators
        indicators = self.indicator_manager.get_all_indicators()
        
        # Detect regime
        regime_state = self.regime_detector.detect(indicators)
        
        # Generate adjustments based on regime
        adjustment = self._generate_adjustment(regime_state)
        
        self.current_adjustment = adjustment
        
        return adjustment
    
    def _generate_adjustment(self, regime: RegimeState) -> StrategyAdjustment:
        """Generate strategy adjustment based on regime state"""
        # Start with neutral adjustments
        position_multiplier = 1.0
        leverage_cap = self.DEFAULT_LEVERAGE_CAP
        frequency_multiplier = 1.0
        stop_tightening = 1.0
        tp_adjustment = 1.0
        
        reasons = []
        
        # Risk regime adjustments
        if regime.risk_regime == MarketRegime.RISK_OFF:
            position_multiplier *= 0.5
            leverage_cap = min(leverage_cap, 1.5)
            frequency_multiplier *= 0.7
            stop_tightening *= 0.9  # Tighter stops
            reasons.append("Risk-off environment detected")
        elif regime.risk_regime == MarketRegime.RISK_ON:
            position_multiplier *= 1.1
            tp_adjustment *= 1.1  # Wider take profits
            reasons.append("Risk-on environment supports larger positions")
        
        # Volatility regime adjustments
        if regime.volatility_regime == MarketRegime.HIGH_VOLATILITY:
            position_multiplier *= 0.6
            leverage_cap = min(leverage_cap, 1.0)
            stop_tightening *= 0.85  # Much tighter stops
            frequency_multiplier *= 0.5
            reasons.append("High volatility requires reduced exposure")
        elif regime.volatility_regime == MarketRegime.LOW_VOLATILITY:
            position_multiplier *= 1.1
            reasons.append("Low volatility allows normal positioning")
        
        # Economic regime adjustments
        if regime.economic_regime == MarketRegime.CONTRACTION:
            position_multiplier *= 0.7
            leverage_cap = min(leverage_cap, 1.5)
            reasons.append("Economic contraction warrants caution")
        elif regime.economic_regime == MarketRegime.EXPANSION:
            position_multiplier *= 1.1
            reasons.append("Economic expansion supports growth assets")
        
        # Monetary regime adjustments
        if regime.monetary_regime == MarketRegime.TIGHTENING:
            # Tightening typically negative for risk assets
            position_multiplier *= 0.9
            reasons.append("Monetary tightening in progress")
        elif regime.monetary_regime == MarketRegime.EASING:
            position_multiplier *= 1.1
            reasons.append("Monetary easing supports risk assets")
        
        # Asset class weights based on regime
        asset_weights = self._calculate_asset_weights(regime)
        
        # Check for safe mode trigger
        if position_multiplier < 0.4 or leverage_cap <= 1.0:
            self.safe_mode = True
            leverage_cap = self.SAFE_MODE_LEVERAGE_CAP
            reasons.append("SAFE MODE ACTIVATED")
        else:
            self.safe_mode = False
        
        # Clamp values to reasonable ranges
        position_multiplier = max(0.2, min(1.5, position_multiplier))
        frequency_multiplier = max(0.3, min(1.5, frequency_multiplier))
        stop_tightening = max(0.7, min(1.2, stop_tightening))
        tp_adjustment = max(0.8, min(1.3, tp_adjustment))
        
        return StrategyAdjustment(
            position_size_multiplier=position_multiplier,
            leverage_cap=leverage_cap,
            trade_frequency_multiplier=frequency_multiplier,
            stop_loss_tightening=stop_tightening,
            take_profit_adjustment=tp_adjustment,
            asset_class_weights=asset_weights,
            reason="; ".join(reasons) if reasons else "Normal conditions",
            confidence=regime.confidence,
            timestamp=datetime.utcnow(),
        )
    
    def _calculate_asset_weights(self, regime: RegimeState) -> Dict[str, float]:
        """Calculate asset class weight adjustments based on regime"""
        weights = {
            "crypto": 1.0,
            "forex": 1.0,
        }
        
        # Risk-off: reduce crypto, maintain forex
        if regime.risk_regime == MarketRegime.RISK_OFF:
            weights["crypto"] *= 0.6
            weights["forex"] *= 0.9
        
        # High volatility: reduce all
        if regime.volatility_regime == MarketRegime.HIGH_VOLATILITY:
            weights["crypto"] *= 0.7
            weights["forex"] *= 0.8
        
        # Contraction: reduce crypto more
        if regime.economic_regime == MarketRegime.CONTRACTION:
            weights["crypto"] *= 0.7
        
        return weights
    
    def get_current_adjustment(self) -> Optional[StrategyAdjustment]:
        """Get the most recent strategy adjustment"""
        return self.current_adjustment
    
    def is_safe_mode(self) -> bool:
        """Check if safe mode is currently active"""
        return self.safe_mode
    
    def should_reduce_exposure(self) -> bool:
        """Quick check if exposure should be reduced"""
        if not self.current_adjustment:
            return False
        return self.current_adjustment.position_size_multiplier < 0.8
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of current macro strategy state"""
        regime_summary = self.regime_detector.get_regime_summary()
        
        return {
            "safe_mode": self.safe_mode,
            "should_reduce_exposure": self.should_reduce_exposure(),
            "regime": regime_summary,
            "adjustment": self.current_adjustment.to_dict() if self.current_adjustment else None,
            "indicator_count": len(self.indicator_manager.get_all_indicators()),
        }
