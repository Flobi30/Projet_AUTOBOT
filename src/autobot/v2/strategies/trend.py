"""
Trend Following Strategy - Suivi de tendance
Achat en tendance haussière, vente en baissière
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from collections import deque

from . import Strategy, TradingSignal, SignalType, calculate_ma, calculate_ema, calculate_rsi

logger = logging.getLogger(__name__)


class TrendStrategy(Strategy):
    """
    Stratégie de suivi de tendance (Trend Following).
    
    Principe:
    - Détecte la tendance avec des moyennes mobiles (MA)
    - Achète quand la tendance est haussière (golden cross)
    - Vend quand la tendance est baissière (death cross)
    - Utilise le RSI pour éviter les entrées en surachat/survente
    
    Configuration:
    - fast_ma: Période MA rapide (défaut: 10)
    - slow_ma: Période MA lente (défaut: 30)
    - rsi_period: Période RSI (défaut: 14)
    - rsi_overbought: Seuil surachat (défaut: 70)
    - rsi_oversold: Seuil survente (défaut: 30)
    - min_trend_strength: Force min. tendance en % (défaut: 1.0)
    """
    
    def __init__(self, instance: Any, config: Optional[Dict] = None):
        super().__init__(instance, config)
        
        # Configuration
        self.fast_period = self.config.get('fast_ma', 10)
        self.slow_period = self.config.get('slow_ma', 30)
        self.rsi_period = self.config.get('rsi_period', 14)
        self.rsi_overbought = self.config.get('rsi_overbought', 70)
        self.rsi_oversold = self.config.get('rsi_oversold', 30)
        self.min_trend_strength = self.config.get('min_trend_strength', 1.0)
        
        # Historique des prix
        self._price_history: deque = deque(maxlen=200)
        
        # État
        self._initialized = True
        self._current_trend = "neutral"  # "up", "down", "neutral"
        self._position_open = False
        self._entry_price: Optional[float] = None
        
        logger.info(f"📈 Trend Strategy: MA{self.fast_period}/MA{self.slow_period}, "
                   f"RSI({self.rsi_period})")
    
    def _calculate_indicators(self) -> Dict[str, Any]:
        """Calcule tous les indicateurs techniques"""
        prices = list(self._price_history)
        
        if len(prices) < self.slow_period:
            return {'ready': False}
        
        # Moyennes mobiles
        fast_ma = calculate_ma(prices, self.fast_period)
        slow_ma = calculate_ma(prices, self.slow_period)
        
        # RSI
        rsi = calculate_rsi(prices, self.rsi_period)
        
        # Tendance
        if fast_ma and slow_ma:
            diff_pct = (fast_ma - slow_ma) / slow_ma * 100
            
            if diff_pct > self.min_trend_strength:
                trend = "up"
            elif diff_pct < -self.min_trend_strength:
                trend = "down"
            else:
                trend = "neutral"
        else:
            trend = "neutral"
            diff_pct = 0
        
        return {
            'ready': True,
            'fast_ma': fast_ma,
            'slow_ma': slow_ma,
            'rsi': rsi,
            'trend': trend,
            'diff_pct': diff_pct,
            'prices_count': len(prices)
        }
    
    def _should_buy(self, indicators: Dict) -> bool:
        """Conditions d'achat"""
        if not indicators['ready']:
            return False
        
        # Tendance haussière
        if indicators['trend'] != "up":
            return False
        
        # Golden cross : fast MA > slow MA avec momentum
        if indicators['diff_pct'] < self.min_trend_strength:
            return False
        
        # RSI pas en surachat
        if indicators['rsi'] and indicators['rsi'] > self.rsi_overbought:
            logger.debug(f"⏱️ Achat bloqué: RSI surachat ({indicators['rsi']:.1f})")
            return False
        
        return True
    
    def _should_sell(self, indicators: Dict, current_price: float) -> bool:
        """Conditions de vente"""
        if not indicators['ready']:
            return False
        
        # Death cross : tendance baissière
        if indicators['trend'] == "down":
            return True
        
        # RSI en surachat extrême (take profit)
        if indicators['rsi'] and indicators['rsi'] > 80:
            return True
        
        # Stop loss si perte > 5%
        if self._entry_price and current_price < self._entry_price * 0.95:
            return True
        
        return False
    
    def on_price(self, price: float):
        """Analyse le prix et émet des signaux"""
        if not self._initialized:
            return
        
        self._price_history.append(price)
        
        # Besoin d'historique suffisant
        if len(self._price_history) < self.slow_period:
            return
        
        indicators = self._calculate_indicators()
        symbol = self.instance.config.symbol
        
        # Log périodique
        if len(self._price_history) % 50 == 0:
            logger.debug(f"📈 MA{self.fast_period}={indicators.get('fast_ma', 0):.0f} "
                        f"MA{self.slow_period}={indicators.get('slow_ma', 0):.0f} "
                        f"RSI={indicators.get('rsi', 0):.1f} "
                        f"Trend={indicators['trend']}")
        
        # Vérification vente (si position ouverte)
        if self._position_open:
            if self._should_sell(indicators, price):
                signal = TradingSignal(
                    type=SignalType.SELL,
                    symbol=symbol,
                    price=price,
                    volume=0,  # Ferme toute la position
                    reason=f"Trend reversal: {indicators['trend']} "
                           f"(MA diff: {indicators['diff_pct']:.2f}%)",
                    timestamp=datetime.now(),
                    metadata={
                        'fast_ma': indicators['fast_ma'],
                        'slow_ma': indicators['slow_ma'],
                        'rsi': indicators['rsi'],
                        'trend': indicators['trend'],
                        'strategy': 'trend'
                    }
                )
                
                self.emit_signal(signal)
        
        # Vérification achat (si pas de position)
        else:
            if self._should_buy(indicators):
                # Calcul du volume (50% du capital disponible)
                available = self.instance.get_available_capital()
                volume_pct = 0.5
                volume = (available * volume_pct) / price
                
                signal = TradingSignal(
                    type=SignalType.BUY,
                    symbol=symbol,
                    price=price,
                    volume=volume,
                    reason=f"Uptrend detected: MA{self.fast_period} > MA{self.slow_period} "
                           f"({indicators['diff_pct']:.2f}%)",
                    timestamp=datetime.now(),
                    metadata={
                        'fast_ma': indicators['fast_ma'],
                        'slow_ma': indicators['slow_ma'],
                        'rsi': indicators['rsi'],
                        'trend': indicators['trend'],
                        'strategy': 'trend'
                    }
                )
                
                self.emit_signal(signal)
    
    def on_position_opened(self, position: Any):
        """Position ouverte"""
        self._position_open = True
        self._entry_price = position.buy_price
        
        logger.info(f"📈 Position trend ouverte @ {position.buy_price:.0f}€ "
                   f"x {position.volume:.6f}")
    
    def on_position_closed(self, position: Any, profit: float):
        """Position fermée"""
        self._position_open = False
        self._entry_price = None
        
        logger.info(f"📈 Position trend fermée: P&L = {profit:+.2f}€")
    
    def get_status(self) -> Dict[str, Any]:
        """Statut de la stratégie Trend"""
        base_status = super().get_status()
        
        indicators = self._calculate_indicators()
        
        return {
            **base_status,
            'trend': {
                'current': self._current_trend,
                'position_open': self._position_open,
                'entry_price': self._entry_price,
                'indicators': {
                    k: round(v, 2) if isinstance(v, float) else v
                    for k, v in indicators.items()
                    if v is not None
                }
            }
        }
    
    def reset(self):
        """Réinitialise"""
        self._position_open = False
        self._entry_price = None
        self._current_trend = "neutral"
        self._price_history.clear()
        super().reset()
        logger.info("📈 Trend Strategy réinitialisée")
