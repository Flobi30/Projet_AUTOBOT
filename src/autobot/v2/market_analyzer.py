"""
Market Analyzer - Analyse et comparaison des marchés pour auto-sélection
Analyse la qualité des marchés en temps réel
"""

import logging
import statistics
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from enum import Enum
import threading

from .markets import MarketConfig, MarketType, get_market_config

logger = logging.getLogger(__name__)


class MarketQualityScore(Enum):
    """Score qualité d'un marché"""
    EXCELLENT = 5   # Idéal pour trading
    GOOD = 4        # Bon pour trading
    ACCEPTABLE = 3  # Acceptable avec précaution
    POOR = 2        # Éviter si possible
    BAD = 1         # Ne pas trader


@dataclass
class MarketMetrics:
    """Métriques calculées pour un marché"""
    symbol: str
    market_type: MarketType
    
    # Volatilité (ATR %)
    volatility_24h: float
    volatility_7d: float
    
    # Tendance
    trend_direction: str  # "up", "down", "sideways"
    trend_strength: float  # 0-1
    
    # Liquidité
    volume_24h: float
    spread_avg: float  # en %
    
    # Qualité marché
    market_quality: MarketQualityScore
    
    # Score composite (0-100)
    composite_score: float
    
    # Recommandation
    recommended_strategy: str
    recommended_allocation: float  # % du capital


class MarketAnalyzer:
    """
    Analyseur de marchés en temps réel.
    Calcule les métriques et scores pour sélection auto.
    """
    
    def __init__(self):
        self._price_history: Dict[str, List[Tuple[datetime, float]]] = {}
        self._lock = threading.Lock()
        self._cache: Dict[str, MarketMetrics] = {}
        self._cache_time: Dict[str, datetime] = {}
        self._cache_ttl = timedelta(minutes=5)
        
    def add_price(self, symbol: str, price: float):
        """Ajoute un point de prix à l'historique"""
        with self._lock:
            if symbol not in self._price_history:
                self._price_history[symbol] = []
            
            self._price_history[symbol].append((datetime.now(timezone.utc), price))
            
            # Garde seulement 7 jours d'historique
            cutoff = datetime.now(timezone.utc) - timedelta(days=7)
            self._price_history[symbol] = [
                (t, p) for t, p in self._price_history[symbol] if t > cutoff
            ]
    
    def analyze_market(self, symbol: str) -> Optional[MarketMetrics]:
        """
        Analyse complète d'un marché.
        Retourne None si pas assez d'historique.
        """
        # Check cache
        if symbol in self._cache:
            last_update = self._cache_time.get(symbol)
            if last_update and datetime.now(timezone.utc) - last_update < self._cache_ttl:
                return self._cache[symbol]
        
        with self._lock:
            if symbol not in self._price_history:
                return None
            
            history = self._price_history[symbol]
            if len(history) < 20:  # Minimum 20 points (was 100 — too strict for startup)
                return None
            
            prices = [p for _, p in history]
            config = get_market_config(symbol)
            
            # Calcul métriques
            volatility_24h = self._calc_volatility(history, hours=24)
            volatility_7d = self._calc_volatility(history, hours=168)
            trend_dir, trend_str = self._calc_trend(history)
            volume = self._estimate_volume(history)
            spread = self._estimate_spread(symbol, prices)
            
            # Score qualité
            quality = self._assess_quality(
                volatility_24h, volatility_7d, trend_str, spread, config
            )
            
            # Score composite (0-100)
            composite = self._calc_composite_score(
                volatility_24h, trend_str, volume, spread, config
            )
            
            # Stratégie recommandée
            strategy, allocation = self._recommend_strategy(
                quality, volatility_24h, trend_str, config
            )
            
            metrics = MarketMetrics(
                symbol=symbol,
                market_type=config.market_type if config else MarketType.CRYPTO,
                volatility_24h=volatility_24h,
                volatility_7d=volatility_7d,
                trend_direction=trend_dir,
                trend_strength=trend_str,
                volume_24h=volume,
                spread_avg=spread,
                market_quality=quality,
                composite_score=composite,
                recommended_strategy=strategy,
                recommended_allocation=allocation
            )
            
            # Cache
            self._cache[symbol] = metrics
            self._cache_time[symbol] = datetime.now(timezone.utc)
            
            return metrics
    
    def get_best_markets(self, min_score: float = 50.0) -> List[MarketMetrics]:
        """
        Retourne les marchés classés par score composite.
        Filtre ceux avec score < min_score.
        """
        all_metrics = []
        
        with self._lock:
            symbols = list(self._price_history.keys())
        
        for symbol in symbols:
            metrics = self.analyze_market(symbol)
            if metrics and metrics.composite_score >= min_score:
                all_metrics.append(metrics)
        
        # Tri par score décroissant
        return sorted(all_metrics, key=lambda m: m.composite_score, reverse=True)
    
    def _calc_volatility(self, history: List[Tuple[datetime, float]], hours: int) -> float:
        """Calcule la volatilité (ATR %) sur N heures"""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        recent = [p for t, p in history if t > cutoff]
        
        if len(recent) < 2:
            return 0.0
        
        # True Range
        tr_values = []
        for i in range(1, len(recent)):
            high = max(recent[i], recent[i-1])
            low = min(recent[i], recent[i-1])
            tr = high - low
            tr_pct = tr / recent[i-1] * 100
            tr_values.append(tr_pct)
        
        if not tr_values:
            return 0.0
        
        # ATR moyen
        atr = statistics.mean(tr_values)
        return atr
    
    def _calc_trend(self, history: List[Tuple[datetime, float]]) -> Tuple[str, float]:
        """Calcule la direction et force de tendance"""
        if len(history) < 50:
            return "sideways", 0.0
        
        prices = [p for _, p in history]
        
        # Moyennes mobiles
        ma_short = statistics.mean(prices[-20:])
        ma_long = statistics.mean(prices[-50:])
        
        # Direction
        if ma_short > ma_long * 1.02:
            direction = "up"
        elif ma_short < ma_long * 0.98:
            direction = "down"
        else:
            direction = "sideways"
        
        # Force (0-1)
        diff = abs(ma_short - ma_long) / ma_long
        strength = min(1.0, diff * 10)  # Normaliser
        
        return direction, strength
    
    def _estimate_volume(self, history: List[Tuple[datetime, float]]) -> float:
        """Estime le volume (proxy: nombre de ticks)"""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        recent_ticks = len([t for t, _ in history if t > cutoff])
        return float(recent_ticks)
    
    def _estimate_spread(self, symbol: str, prices: List[float]) -> float:
        """Estime le spread moyen (%)"""
        if len(prices) < 10:
            return 0.1  # Valeur par défaut
        
        # Spread estimé par la variance microstructure
        returns = []
        for i in range(1, min(len(prices), 100)):
            ret = abs(prices[i] - prices[i-1]) / prices[i-1] * 100
            returns.append(ret)
        
        if not returns:
            return 0.1
        
        # Spread ~ moitié du retour minimum moyen
        avg_min_return = statistics.median(sorted(returns)[:10])
        return avg_min_return / 2
    
    def _assess_quality(self, vol_24h: float, vol_7d: float, 
                       trend_str: float, spread: float,
                       config: Optional[MarketConfig]) -> MarketQualityScore:
        """Évalue la qualité globale du marché"""
        score = 0
        
        # Volatilité idéale: 1-3% pour crypto, 0.3-1% pour forex
        if config and config.market_type == MarketType.FOREX:
            if 0.3 <= vol_24h <= 1.0:
                score += 2
            elif vol_24h < 0.1 or vol_24h > 2.0:
                score -= 2
        else:
            if 1.0 <= vol_24h <= 3.0:
                score += 2
            elif vol_24h < 0.5 or vol_24h > 10.0:
                score -= 2
        
        # Trend fort = mieux pour grid
        if trend_str > 0.5:
            score += 1
        
        # Spread faible = meilleur
        if spread < 0.05:
            score += 1
        elif spread > 0.5:
            score -= 1
        
        # Mapping score -> qualité
        if score >= 3:
            return MarketQualityScore.EXCELLENT
        elif score >= 1:
            return MarketQualityScore.GOOD
        elif score >= 0:
            return MarketQualityScore.ACCEPTABLE
        elif score >= -1:
            return MarketQualityScore.POOR
        else:
            return MarketQualityScore.BAD
    
    def _calc_composite_score(self, vol: float, trend: float, 
                              volume: float, spread: float,
                              config: Optional[MarketConfig]) -> float:
        """Calcule un score composite 0-100"""
        score = 50.0  # Base
        
        # Volatilité (30% du score)
        vol_score = 100 - abs(vol - 2.0) * 20  # Optimal = 2%
        score += vol_score * 0.3
        
        # Tendance (20% du score)
        trend_score = trend * 100
        score += trend_score * 0.2
        
        # Volume/Liquidité (30% du score)
        vol_proxy = min(100, volume / 10)  # Normalize
        score += vol_proxy * 0.3
        
        # Spread (20% du score)
        spread_score = max(0, 100 - spread * 100)
        score += spread_score * 0.2
        
        return max(0, min(100, score))
    
    def _recommend_strategy(self, quality: MarketQualityScore, 
                           vol: float, trend: float,
                           config: Optional[MarketConfig]) -> Tuple[str, float]:
        """Recommande une stratégie et allocation capital"""
        
        if quality in (MarketQualityScore.EXCELLENT, MarketQualityScore.GOOD):
            if trend > 0.6:
                return "trend", 0.25  # 25% capital
            else:
                return "grid", 0.20   # 20% capital
        elif quality == MarketQualityScore.ACCEPTABLE:
            return "grid", 0.10       # 10% capital, prudent
        else:
            return "none", 0.0        # Ne pas trader


# Singleton
_analyzer_instance: Optional[MarketAnalyzer] = None
_analyzer_lock = threading.Lock()


def get_market_analyzer() -> MarketAnalyzer:
    """Retourne l'analyseur de marchés (singleton)"""
    global _analyzer_instance
    
    with _analyzer_lock:
        if _analyzer_instance is None:
            _analyzer_instance = MarketAnalyzer()
        return _analyzer_instance
