"""
Strategy Framework - Base pour toutes les stratégies de trading
"""

import logging
import threading
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class SignalType(Enum):
    """Types de signaux de trading"""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    CLOSE = "close"


@dataclass
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
        
        # CORRECTION: Lock pour thread safety
        self._lock = threading.Lock()
        
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
                elapsed = (datetime.now() - last_time).total_seconds()
                if elapsed < self._signal_cooldown_seconds:
                    logger.debug(f"⏱️ Signal {signal_key} ignoré (cooldown): {signal.reason}")
                    return
        
        self._last_signal_times[signal_key] = datetime.now()
        
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
    
    @staticmethod
    def kelly_criterion(win_rate: float, avg_win: float, avg_loss: float) -> float:
        """
        Formule de Kelly pour optimiser la taille des positions.
        f* = (p*b - q) / b
        où p = win rate, q = loss rate, b = avg_win/avg_loss
        """
        if avg_loss == 0:
            return 0.1  # Default 10%
        
        loss_rate = 1 - win_rate
        b = avg_win / avg_loss
        
        kelly = (win_rate * b - loss_rate) / b
        
        # Kelly agressif → on prend la moitié (Half-Kelly)
        return max(0.0, min(kelly / 2, 0.25))  # Max 25%


def calculate_grid_levels(
    center_price: float,
    range_percent: float,
    num_levels: int
) -> List[float]:
    """
    Calcule les niveaux d'une grille symétrique.
    
    Args:
        center_price: Prix central
        range_percent: Range total en % (ex: 7 pour +/- 7%)
        num_levels: Nombre de niveaux (impair recommandé)
    
    Returns:
        Liste des prix des niveaux, triée du plus bas au plus haut
    """
    # CORRECTION: Guard contre division par zéro
    if num_levels < 2:
        return [center_price]
    
    half_range = range_percent / 2
    step = range_percent / (num_levels - 1)
    
    levels = []
    for i in range(num_levels):
        offset = -half_range + (i * step)
        level_price = center_price * (1 + offset / 100)
        levels.append(level_price)
    
    return sorted(levels)


def calculate_ma(prices: List[float], period: int) -> Optional[float]:
    """Calcule une moyenne mobile simple"""
    if len(prices) < period:
        return None
    return sum(prices[-period:]) / period


def calculate_ema(prices: List[float], period: int) -> Optional[float]:
    """Calcule une moyenne mobile exponentielle"""
    if len(prices) < period:
        return None
    
    multiplier = 2 / (period + 1)
    ema = sum(prices[:period]) / period  # SMA initiale
    
    for price in prices[period:]:
        ema = (price - ema) * multiplier + ema
    
    return ema


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
    'calculate_grid_levels',
    'calculate_ma',
    'calculate_ema',
    'calculate_rsi',
    'calculate_bollinger_bands'
]
