"""
Trend Following Strategy - Suivi de tendance
Achat en tendance haussière, vente en baissière
"""

import logging
import math
from typing import Dict, List, Optional, Any
from datetime import datetime
from collections import deque

# CORRECTION: Utilisation des indicateurs O(1) pour maximale performance
from . import Strategy, TradingSignal, SignalType, RollingMA, RollingEMA, RollingRSI

logger = logging.getLogger(__name__)


class TrendStrategy(Strategy):
    """
    Stratégie de suivi de tendance (Trend Following) — version synchrone.

    DEPRECATED: Remplacée par TrendStrategyAsync (src/autobot/v2/strategies/trend_async.py).
    Cette version synchrone est maintenue pour compatibilité avec instance.py.
    Toute nouvelle instance de production doit utiliser TrendStrategyAsync.

    PRODUCTION_READY = False — W2: utiliser TrendStrategyAsync pour la production.

    Configuration:
    - fast_ma: Période MA rapide (défaut: 10)
    - slow_ma: Période MA lente (défaut: 30)
    - rsi_period: Période RSI (défaut: 14)
    - rsi_overbought: Seuil surachat (défaut: 70)
    - rsi_oversold: Seuil survente (défaut: 30)
    - min_trend_strength: Force min. tendance en % (défaut: 1.0)
    """

    PRODUCTION_READY = False  # W2: utiliser TrendStrategyAsync en production

    def __init__(self, instance: Any, config: Optional[Dict] = None):
        if not self.PRODUCTION_READY:
            logger.warning(
                "⚠️ TrendStrategy (sync) est dépréciée. "
                "Migrer vers TrendStrategyAsync pour la production."
            )
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
        
        # CORRECTION: Indicateurs O(1) pour calcul incrémental ultra-rapide
        self._fast_ma = RollingEMA(self.fast_period)
        self._slow_ma = RollingEMA(self.slow_period)
        self._rsi = RollingRSI(self.rsi_period)
        
        # État
        self._initialized = True
        self._current_trend = "neutral"  # "up", "down", "neutral"
        self._entry_price: Optional[float] = None
        # CORRECTION: Pas de _position_open bool -> check dynamique instance
        
        logger.info(f"📈 Trend Strategy: MA{self.fast_period}/MA{self.slow_period}, "
                   f"RSI({self.rsi_period}) [Optimisé O(1)]")
    
    def _calculate_indicators(self) -> Dict[str, Any]:
        """Calcule tous les indicateurs techniques en O(1) - ULTRA RAPIDE"""
        # CORRECTION: Utilise les valeurs courantes des indicateurs O(1)
        # Pas besoin de recalculer sur tout l'historique!
        
        fast_ma = self._fast_ma.get_current()
        slow_ma = self._slow_ma.get_current()
        rsi = self._rsi.get_current()
        
        # Vérifie si on a assez d'historique
        if fast_ma is None or slow_ma is None or rsi is None:
            return {'ready': False}
        
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
            'prices_count': len(self._price_history)
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
    
    def _has_open_position(self) -> bool:
        """CORRECTION: Vérifie si une position est réellement ouverte sur l'instance (thread-safe)"""
        try:
            # CORRECTION: Utilise méthode thread-safe au lieu d'accès direct
            positions = self.instance.get_positions_snapshot()
            return len(positions) > 0
        except Exception as e:
            # CORRECTION: Log warning au lieu de fail silencieux
            logger.warning(f"⚠️ Erreur accès positions: {e}. Assume pas de position.")
            return False
    
    def on_price(self, price: float):
        """Analyse le prix et émet des signaux - OPTIMISÉ O(1)"""
        if not self._initialized:
            return

        if not math.isfinite(price) or price <= 0:
            logger.warning(f"❌ Prix invalide ignoré: {price}")
            return

        with self._lock:
            self._price_history.append(price)
            
            # CORRECTION: Mise à jour incrémentale O(1) des indicateurs
            self._fast_ma.update(price)
            self._slow_ma.update(price)
            self._rsi.update(price)
            
            indicators = self._calculate_indicators()
            # CORRECTION: Mettre à jour _current_trend
            self._current_trend = indicators.get('trend', 'neutral')
        
        symbol = self.instance.config.symbol
        
        # Log périodique
        if len(self._price_history) % 50 == 0:
            logger.debug(f"📈 MA{self.fast_period}={indicators.get('fast_ma', 0):.0f} "
                        f"MA{self.slow_period}={indicators.get('slow_ma', 0):.0f} "
                        f"RSI={indicators.get('rsi', 0):.1f} "
                        f"Trend={indicators['trend']}")
        
        # CORRECTION: Vérification dynamique position (pas booléen)
        position_open = self._has_open_position()
        
        # Vérification vente (si position ouverte)
        if position_open:
            if self._should_sell(indicators, price):
                # CORRECTION: Volume = -1 signifie "close all" (pas 0)
                signal = TradingSignal(
                    type=SignalType.SELL,
                    symbol=symbol,
                    price=price,
                    volume=-1,  # CORRECTION: -1 = close all, pas 0
                    reason=f"Trend reversal: {indicators['trend']} "
                           f"(MA diff: {indicators['diff_pct']:.2f}%)",
                    timestamp=datetime.now(),
                    metadata={
                        'fast_ma': indicators['fast_ma'],
                        'slow_ma': indicators['slow_ma'],
                        'rsi': indicators['rsi'],
                        'trend': indicators['trend'],
                        'strategy': 'trend',
                        'close_all': True  # Flag explicite
                    }
                )
                
                self.emit_signal(signal)
        
        # Vérification achat (si pas de position)
        else:
            if self._should_buy(indicators):
                # CORRECTION: Utiliser get_current_capital() et PositionSizing
                with self._lock:
                    available = self.instance.get_current_capital()
                
                # CQ-06: Risk-based sizing — 2% du capital risqué par trade
                # Stop-loss à 5% sous l'entrée → volume = (capital * 0.02) / (prix * 0.05)
                risk_amount = available * 0.02
                stop_distance_pct = 0.05
                volume = risk_amount / (price * stop_distance_pct)
                
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
        try:
            if not hasattr(position, 'buy_price') or not hasattr(position, 'volume'):
                logger.error("❌ Position object manque buy_price ou volume")
                return
            
            with self._lock:
                self._entry_price = position.buy_price
            
            logger.info(f"📈 Position trend ouverte @ {position.buy_price:.0f}€ "
                       f"x {position.volume:.6f}")
        except Exception as e:
            logger.exception(f"❌ Erreur on_position_opened: {e}")
    
    def on_position_closed(self, position: Any, profit: float):
        """Position fermée"""
        try:
            with self._lock:
                self._entry_price = None
            
            logger.info(f"📈 Position trend fermée: P&L = {profit:+.2f}€")
        except Exception as e:
            logger.exception(f"❌ Erreur on_position_closed: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """Statut de la stratégie Trend"""
        base_status = super().get_status()
        
        with self._lock:
            indicators = self._calculate_indicators()
            entry_price = self._entry_price
            current_trend = self._current_trend
        
        # CORRECTION: Utiliser _has_open_position() pour cohérence
        position_open = self._has_open_position()
        
        return {
            **base_status,
            'trend': {
                'current': current_trend,
                'position_open': position_open,
                'entry_price': entry_price,
                'indicators': {
                    k: round(v, 2) if isinstance(v, float) else v
                    for k, v in indicators.items()
                    if v is not None
                }
            }
        }
    
    def reset(self):
        """Réinitialise"""
        with self._lock:
            self._entry_price = None
            self._current_trend = "neutral"
            self._price_history.clear()
        super().reset()
        logger.info("📈 Trend Strategy réinitialisée")
