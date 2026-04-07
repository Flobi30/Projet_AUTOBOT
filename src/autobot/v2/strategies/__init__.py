"""
Strategy Framework - Base pour toutes les stratégies de trading
"""

import logging
import threading
from abc import ABC, abstractmethod
from collections import deque
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class SignalType(Enum):
    """Types de signaux de trading"""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    CLOSE = "close"


@dataclass(slots=True)
class TradingSignal:
    """Signal de trading généré par une stratégie"""
    type: SignalType
    symbol: str
    price: float
    volume: float
    reason: str
    timestamp: datetime
    metadata: Dict[str, Any]
    
    def to_dict(self) -> Dict:
        return {
            'type': self.type.value,
            'symbol': self.symbol,
            'price': self.price,
            'volume': self.volume,
            'reason': self.reason,
            'timestamp': self.timestamp.isoformat(),
            'metadata': self.metadata
        }


class Strategy(ABC):
    """
    Classe de base abstraite pour toutes les stratégies.
    
    Une stratégie reçoit les mises à jour de prix et décide :
    - D'ouvrir une position (BUY/SELL)
    - De fermer une position (CLOSE)
    - Ou d'attendre (HOLD)
    """
    
    def __init__(self, instance: Any, config: Optional[Dict] = None):
        """
        Args:
            instance: Instance de trading parente (TradingInstance)
            config: Configuration spécifique à la stratégie
        """
        self.instance = instance
        self.config = config or {}
        self.name = self.__class__.__name__
        
        # Callback pour émettre des signaux
        self._on_signal: Optional[Callable[[TradingSignal], None]] = None
        
        # État interne
        self._initialized = False
        # CORRECTION: Cooldown par type de signal (pas global) pour permettre batch
        self._last_signal_times: Dict[str, datetime] = {}
        self._signal_cooldown_seconds = self.config.get('signal_cooldown', 30)
        
        # CORRECTION: RLock (réentrant) pour éviter deadlock
        self._lock = threading.RLock()
        
        logger.info(f"🎯 Stratégie {self.name} initialisée")
    
    def set_signal_callback(self, callback: Callable[[TradingSignal], None]):
        """Définit le callback appelé quand un signal est généré"""
        self._on_signal = callback
    
    @abstractmethod
    def on_price(self, price: float):
        """
        Appelé à chaque mise à jour de prix.
        Doit analyser et potentiellement émettre un signal.
        """
        pass
    
    @abstractmethod
    def on_position_opened(self, position: Any):
        """Appelé quand une position est ouverte"""
        pass
    
    @abstractmethod
    def on_position_closed(self, position: Any, profit: float):
        """Appelé quand une position est fermée"""
        pass
    
    def emit_signal(self, signal: TradingSignal, bypass_cooldown: bool = False):
        """Émet un signal de trading
        
        Args:
            signal: Le signal à émettre
            bypass_cooldown: Si True, ignore le cooldown (pour batch de signaux)
        """
        signal_key = signal.type.value
        
        # CORRECTION: Cooldown par type de signal (pas global)
        if not bypass_cooldown:
            last_time = self._last_signal_times.get(signal_key)
            if last_time:
                elapsed = (datetime.now(timezone.utc) - last_time).total_seconds()
                if elapsed < self._signal_cooldown_seconds:
                    logger.debug(f"⏱️ Signal {signal_key} ignoré (cooldown): {signal.reason}")
                    return
        
        self._last_signal_times[signal_key] = datetime.now(timezone.utc)
        
        logger.info(f"📡 Signal {signal_key.upper()}: {signal.reason} @ {signal.price:.2f}")
        
        if self._on_signal:
            try:
                self._on_signal(signal)
            except Exception as e:
                logger.exception(f"❌ Erreur callback signal: {e}")
    
    def safe_on_price(self, price: float):
        """
        Wrapper thread-safe avec try/except pour on_price.
        Appeler cette méthode depuis l'instance parente.
        """
        try:
            with self._lock:
                self.on_price(price)
        except Exception as e:
            logger.exception(f"❌ Erreur stratégie {self.name}.on_price: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """Retourne le statut de la stratégie"""
        return {
            'name': self.name,
            'initialized': self._initialized,
            'last_signals': {k: v.isoformat() for k, v in self._last_signal_times.items()},
            'config': self.config
        }
    
    def reset(self):
        """Réinitialise l'état de la stratégie"""
        with self._lock:
            self._initialized = False
            self._last_signal_times.clear()
        logger.info(f"🔄 Stratégie {self.name} réinitialisée")


class PositionSizing:
    """Utilities pour le sizing des positions"""
    
    @staticmethod
    def fixed_amount(capital: float, amount: float) -> float:
        """Position fixe en €"""
        return min(amount, capital * 0.95)  # Max 95% du capital
    
    @staticmethod
    def percentage_capital(capital: float, percent: float) -> float:
        """Pourcentage du capital disponible"""
        return capital * (percent / 100)
    
    # Kelly criterion supprimé — utiliser autobot.v2.modules.kelly_criterion.KellyCriterion


def calculate_grid_levels(
    center_price: float,
    range_percent: float,
    num_levels: int,
    spacing_mode: str = None,
) -> List[float]:
    """
    Calcule les niveaux d'une grille symétrique.
    PF 3.8: supports geometric spacing mode.
    """
    import os as _os, math
    if spacing_mode is None:
        spacing_mode = _os.getenv("GRID_SPACING_MODE", "linear")
    if num_levels < 2:
        return [center_price]
    half_range = range_percent / 2
    low = center_price * (1 - half_range / 100)
    high = center_price * (1 + half_range / 100)
    if spacing_mode == "geometric" and high > low > 0:
        ratio = (high / low) ** (1.0 / (num_levels - 1))
        levels = [low * (ratio ** i) for i in range(num_levels)]
    else:
        step = range_percent / (num_levels - 1)
        levels = []
        for i in range(num_levels):
            offset = -half_range + (i * step)
            levels.append(center_price * (1 + offset / 100))
    return sorted(levels)


# ============================================================================
# OPTIMISATION: Classes pour calculs incrémentaux O(1) (meilleur que NumPy!)
# ============================================================================

class RollingMA:
    """
    Moyenne mobile simple en O(1) par mise à jour.
    Maintient une somme courante, pas besoin de recalculer tout.
    """
    def __init__(self, period: int):
        self.period = period
        self.buffer = deque(maxlen=period)
        self.running_sum = 0.0
        self.count = 0
    
    def update(self, price: float) -> Optional[float]:
        """Ajoute un prix et retourne la MA mise à jour en O(1)"""
        # Si buffer plein, soustrait l'ancienne valeur
        if len(self.buffer) == self.period:
            self.running_sum -= self.buffer[0]
        
        self.buffer.append(price)
        self.running_sum += price
        self.count = min(self.count + 1, self.period)
        
        return self.running_sum / self.count if self.count > 0 else None
    
    def get_current(self) -> Optional[float]:
        """Retourne la MA courante sans nouvelle mise à jour"""
        return self.running_sum / self.count if self.count > 0 else None


class RollingEMA:
    """
    Moyenne mobile exponentielle en O(1) par mise à jour.
    Formule incrémentale: EMA_new = (Price - EMA_old) * multiplier + EMA_old
    """
    def __init__(self, period: int):
        self.period = period
        self.multiplier = 2.0 / (period + 1)
        self.ema = None
        self.initialized = False
    
    def update(self, price: float) -> Optional[float]:
        """Ajoute un prix et retourne l'EMA mise à jour en O(1)"""
        if not self.initialized:
            # Première valeur ou SMA initiale
            self.ema = price
            self.initialized = True
            return self.ema
        
        # Formule incrémentale O(1)
        self.ema = (price - self.ema) * self.multiplier + self.ema
        return self.ema
    
    def get_current(self) -> Optional[float]:
        """Retourne l'EMA courante"""
        return self.ema


class RollingRSI:
    """
    RSI (Relative Strength Index) en O(1) par mise à jour avec Wilder's smoothing.
    Maintient les moyennes de gains/pertes, pas besoin de recalculer sur toute l'historique.
    """
    def __init__(self, period: int = 14):
        self.period = period
        self.prev_price = None
        self.avg_gain = 0.0
        self.avg_loss = 0.0
        self.count = 0
    
    def update(self, price: float) -> Optional[float]:
        """Ajoute un prix et retourne le RSI en O(1)"""
        if self.prev_price is None:
            self.prev_price = price
            return None
        
        # Calcul du changement
        change = price - self.prev_price
        gain = max(change, 0)
        loss = abs(min(change, 0))
        
        self.prev_price = price
        self.count += 1
        
        if self.count <= self.period:
            # Phase d'initialisation: SMA simple
            self.avg_gain = (self.avg_gain * (self.count - 1) + gain) / self.count
            self.avg_loss = (self.avg_loss * (self.count - 1) + loss) / self.count
        else:
            # Phase continue: Wilder's smoothing (O(1))
            self.avg_gain = (self.avg_gain * (self.period - 1) + gain) / self.period
            self.avg_loss = (self.avg_loss * (self.period - 1) + loss) / self.period
        
        if self.avg_loss == 0:
            return 100.0
        
        rs = self.avg_gain / self.avg_loss
        return 100.0 - (100.0 / (1.0 + rs))
    
    def get_current(self) -> Optional[float]:
        """Retourne le RSI courant"""
        if self.avg_loss == 0:
            return 100.0 if self.avg_gain > 0 else None
        rs = self.avg_gain / self.avg_loss
        return 100.0 - (100.0 / (1.0 + rs))


# Fonctions legacy conservées pour compatibilité
def calculate_ma(prices: List[float], period: int) -> Optional[float]:
    """Calcule une moyenne mobile simple (legacy - utiliser RollingMA pour O(1))"""
    if len(prices) < period:
        return None
    return sum(prices[-period:]) / period


def calculate_ema(prices: List[float], period: int) -> Optional[float]:
    """Calcule une moyenne mobile exponentielle (legacy - utiliser RollingEMA pour O(1))"""


def calculate_rsi(prices: List[float], period: int = 14) -> Optional[float]:
    """Calcule le RSI (Relative Strength Index)"""
    if len(prices) < period + 1:
        return None
    
    gains = []
    losses = []
    
    for i in range(1, len(prices)):
        change = prices[i] - prices[i-1]
        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))
    
    # Moyennes sur la période
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    
    if avg_loss == 0:
        return 100.0
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return rsi


def calculate_bollinger_bands(
    prices: List[float],
    period: int = 20,
    std_dev: float = 2.0
) -> Optional[Dict[str, float]]:
    """Calcule les bandes de Bollinger"""
    if len(prices) < period:
        return None
    
    sma = sum(prices[-period:]) / period
    variance = sum((p - sma) ** 2 for p in prices[-period:]) / period
    std = variance ** 0.5
    
    return {
        'upper': sma + (std_dev * std),
        'middle': sma,
        'lower': sma - (std_dev * std)
    }


# Imports des stratégies (à la fin pour éviter circular imports)
from .grid import GridStrategy
from .trend import TrendStrategy

__all__ = [
    'Strategy',
    'TradingSignal',
    'SignalType',
    'PositionSizing',
    'GridStrategy',
    'TrendStrategy',
    # OPTIMISATION: Indicateurs O(1) exportés
    'RollingMA',
    'RollingEMA',
    'RollingRSI',
    'calculate_grid_levels',
    'calculate_ma',
    'calculate_ema',
    'calculate_rsi',
    'calculate_bollinger_bands'
]
