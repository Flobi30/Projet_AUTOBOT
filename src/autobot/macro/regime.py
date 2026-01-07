"""
AUTOBOT Market Regime Detection

Detects economic regimes based on macro indicators:
- Risk-on / Risk-off
- Tightening / Easing
- Expansion / Contraction
- High volatility / Low volatility
"""

import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class MarketRegime(Enum):
    """Market regime classifications"""
    RISK_ON = "risk_on"
    RISK_OFF = "risk_off"
    NEUTRAL = "neutral"
    
    # Monetary policy regimes
    TIGHTENING = "tightening"
    EASING = "easing"
    STABLE = "stable"
    
    # Economic cycle regimes
    EXPANSION = "expansion"
    CONTRACTION = "contraction"
    RECOVERY = "recovery"
    SLOWDOWN = "slowdown"
    
    # Volatility regimes
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    NORMAL_VOLATILITY = "normal_volatility"


@dataclass
class RegimeState:
    """Current state of market regimes"""
    risk_regime: MarketRegime
    monetary_regime: MarketRegime
    economic_regime: MarketRegime
    volatility_regime: MarketRegime
    confidence: float  # 0-1 confidence in regime detection
    timestamp: datetime
    signals: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "risk_regime": self.risk_regime.value,
            "monetary_regime": self.monetary_regime.value,
            "economic_regime": self.economic_regime.value,
            "volatility_regime": self.volatility_regime.value,
            "confidence": self.confidence,
            "timestamp": self.timestamp.isoformat(),
            "signals": self.signals,
        }
    
    def is_favorable_for_trading(self) -> bool:
        """Check if current regime is favorable for active trading"""
        unfavorable_conditions = [
            self.risk_regime == MarketRegime.RISK_OFF,
            self.volatility_regime == MarketRegime.HIGH_VOLATILITY,
            self.economic_regime == MarketRegime.CONTRACTION,
        ]
        return sum(unfavorable_conditions) < 2
    
    def get_risk_multiplier(self) -> float:
        """Get risk adjustment multiplier based on regime"""
        multiplier = 1.0
        
        if self.risk_regime == MarketRegime.RISK_OFF:
            multiplier *= 0.5
        elif self.risk_regime == MarketRegime.RISK_ON:
            multiplier *= 1.2
        
        if self.volatility_regime == MarketRegime.HIGH_VOLATILITY:
            multiplier *= 0.7
        elif self.volatility_regime == MarketRegime.LOW_VOLATILITY:
            multiplier *= 1.1
        
        if self.economic_regime == MarketRegime.CONTRACTION:
            multiplier *= 0.6
        elif self.economic_regime == MarketRegime.EXPANSION:
            multiplier *= 1.1
        
        return max(0.2, min(1.5, multiplier))


class RegimeDetector:
    """
    Detects market regimes based on macro-economic indicators.
    
    Uses multiple signals to determine:
    - Risk appetite (VIX, credit spreads, safe haven flows)
    - Monetary policy stance (interest rates, central bank communications)
    - Economic cycle position (GDP, PMI, employment)
    - Market volatility (VIX, realized volatility)
    """
    
    # Thresholds for regime detection
    VIX_HIGH_THRESHOLD = 25.0
    VIX_LOW_THRESHOLD = 15.0
    
    def __init__(self):
        self.current_state: Optional[RegimeState] = None
        self.history: List[RegimeState] = []
    
    def detect_risk_regime(self, indicators: Dict[str, Any]) -> MarketRegime:
        """Detect risk-on/risk-off regime"""
        vix = indicators.get("vix", {}).get("value", 20.0)
        dxy = indicators.get("dxy", {}).get("value", 100.0)
        
        risk_off_signals = 0
        risk_on_signals = 0
        
        # VIX analysis
        if vix > self.VIX_HIGH_THRESHOLD:
            risk_off_signals += 2
        elif vix < self.VIX_LOW_THRESHOLD:
            risk_on_signals += 2
        
        # DXY analysis (strong dollar = risk-off)
        if dxy > 105:
            risk_off_signals += 1
        elif dxy < 95:
            risk_on_signals += 1
        
        if risk_off_signals > risk_on_signals:
            return MarketRegime.RISK_OFF
        elif risk_on_signals > risk_off_signals:
            return MarketRegime.RISK_ON
        return MarketRegime.NEUTRAL
    
    def detect_monetary_regime(self, indicators: Dict[str, Any]) -> MarketRegime:
        """Detect monetary policy regime"""
        fed_rate = indicators.get("fed_rate", {}).get("value", 5.0)
        fed_rate_change = indicators.get("fed_rate", {}).get("change_pct", 0)
        
        if fed_rate_change > 0:
            return MarketRegime.TIGHTENING
        elif fed_rate_change < 0:
            return MarketRegime.EASING
        return MarketRegime.STABLE
    
    def detect_economic_regime(self, indicators: Dict[str, Any]) -> MarketRegime:
        """Detect economic cycle regime"""
        gdp_growth = indicators.get("gdp", {}).get("change_pct", 2.0)
        unemployment = indicators.get("unemployment", {}).get("value", 4.0)
        unemployment_change = indicators.get("unemployment", {}).get("change_pct", 0)
        
        # GDP-based detection
        if gdp_growth > 3:
            gdp_signal = "expansion"
        elif gdp_growth < 0:
            gdp_signal = "contraction"
        elif gdp_growth < 1:
            gdp_signal = "slowdown"
        else:
            gdp_signal = "recovery"
        
        # Unemployment-based adjustment
        if unemployment_change > 0.5:
            if gdp_signal == "expansion":
                gdp_signal = "slowdown"
        elif unemployment_change < -0.3:
            if gdp_signal == "slowdown":
                gdp_signal = "recovery"
        
        regime_map = {
            "expansion": MarketRegime.EXPANSION,
            "contraction": MarketRegime.CONTRACTION,
            "recovery": MarketRegime.RECOVERY,
            "slowdown": MarketRegime.SLOWDOWN,
        }
        
        return regime_map.get(gdp_signal, MarketRegime.RECOVERY)
    
    def detect_volatility_regime(self, indicators: Dict[str, Any]) -> MarketRegime:
        """Detect volatility regime"""
        vix = indicators.get("vix", {}).get("value", 20.0)
        
        if vix > self.VIX_HIGH_THRESHOLD:
            return MarketRegime.HIGH_VOLATILITY
        elif vix < self.VIX_LOW_THRESHOLD:
            return MarketRegime.LOW_VOLATILITY
        return MarketRegime.NORMAL_VOLATILITY
    
    def detect(self, indicators: Dict[str, Any]) -> RegimeState:
        """
        Detect all market regimes based on current indicators.
        
        Args:
            indicators: Dictionary of indicator name -> MacroIndicator data
            
        Returns:
            RegimeState with all detected regimes
        """
        # Convert MacroIndicator objects to dicts if needed
        ind_dict = {}
        for name, ind in indicators.items():
            if hasattr(ind, "to_dict"):
                ind_dict[name] = ind.to_dict()
            elif isinstance(ind, dict):
                ind_dict[name] = ind
            else:
                ind_dict[name] = {"value": ind}
        
        risk_regime = self.detect_risk_regime(ind_dict)
        monetary_regime = self.detect_monetary_regime(ind_dict)
        economic_regime = self.detect_economic_regime(ind_dict)
        volatility_regime = self.detect_volatility_regime(ind_dict)
        
        # Calculate confidence based on data availability
        available_indicators = len([v for v in ind_dict.values() if v.get("value") is not None])
        confidence = min(1.0, available_indicators / 5.0)
        
        state = RegimeState(
            risk_regime=risk_regime,
            monetary_regime=monetary_regime,
            economic_regime=economic_regime,
            volatility_regime=volatility_regime,
            confidence=confidence,
            timestamp=datetime.utcnow(),
            signals={
                "vix": ind_dict.get("vix", {}).get("value"),
                "dxy": ind_dict.get("dxy", {}).get("value"),
                "fed_rate": ind_dict.get("fed_rate", {}).get("value"),
                "gdp_growth": ind_dict.get("gdp", {}).get("change_pct"),
            },
        )
        
        self.current_state = state
        self.history.append(state)
        
        # Keep only last 100 states
        if len(self.history) > 100:
            self.history = self.history[-100:]
        
        return state
    
    def get_current_state(self) -> Optional[RegimeState]:
        """Get the most recently detected regime state"""
        return self.current_state
    
    def get_regime_summary(self) -> Dict[str, Any]:
        """Get a summary of current regime conditions"""
        if not self.current_state:
            return {"status": "no_data", "message": "No regime detection performed yet"}
        
        return {
            "status": "active",
            "regimes": self.current_state.to_dict(),
            "favorable_for_trading": self.current_state.is_favorable_for_trading(),
            "risk_multiplier": self.current_state.get_risk_multiplier(),
        }
