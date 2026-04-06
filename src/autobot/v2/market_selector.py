"""
Market Selector - Sélection automatique du meilleur marché
Décide quel marché utiliser pour une nouvelle instance
"""

import logging
import random
import threading
from typing import List, Optional, Dict, TYPE_CHECKING
from dataclasses import dataclass
from datetime import datetime, timezone

from .market_analyzer import MarketAnalyzer, get_market_analyzer, MarketQualityScore
from .markets import MarketType, MarketConfig, get_market_config, is_market_open

if TYPE_CHECKING:
    from .orchestrator import Orchestrator

logger = logging.getLogger(__name__)

# Singleton
_selector_instance: Optional['MarketSelector'] = None
_selector_lock = threading.Lock()


def get_market_selector(orchestrator: 'Orchestrator') -> 'MarketSelector':
    """Retourne le sélecteur de marché (singleton)"""
    global _selector_instance
    
    with _selector_lock:
        if _selector_instance is None:
            _selector_instance = MarketSelector(orchestrator)
        return _selector_instance


@dataclass
class MarketSelection:
    """Résultat d'une sélection de marché"""
    symbol: str
    market_type: MarketType
    strategy: str
    capital_allocation: float  # % du capital total
    reason: str  # Explication de la sélection


class MarketSelector:
    """
    Sélecteur intelligent de marché.
    
    Logique:
    1. Analyse tous les marchés disponibles
    2. Filtre ceux ouverts et de bonne qualité
    3. Évite la concentration sur un seul marché
    4. Considère les marchés déjà utilisés
    5. Sélectionne le meilleur ou diversifie
    """
    
    def __init__(self, orchestrator: 'Orchestrator'):
        self.orchestrator = orchestrator
        self.analyzer = get_market_analyzer()
        
        # Configuration
        self.min_quality_score = MarketQualityScore.ACCEPTABLE
        self.max_same_market_instances = 2  # Max 2 instances par symbole
        self.min_diversification = 3  # Min 3 marchés différents si possible
        
    def select_market_for_spinoff(self, parent_instance_id: str) -> Optional[MarketSelection]:
        """
        Sélectionne le meilleur marché pour un spin-off.
        
        Args:
            parent_instance_id: ID de l'instance parente
            
        Returns:
            MarketSelection ou None si pas de marché approprié
        """
        logger.info("🎯 Sélection automatique du marché pour spin-off...")
        
        # 1. Récupère les marchés actuellement utilisés
        current_markets = self._get_current_markets()
        logger.debug(f"   Marchés actuels: {current_markets}")
        
        # 2. Analyse tous les marchés
        available_markets = self._get_all_available_markets()
        logger.debug(f"   Marchés analysés: {len(available_markets)}")
        
        # 3. Filtre les marchés appropriés
        candidates = self._filter_candidates(available_markets, current_markets)
        
        if not candidates:
            logger.warning("⚠️ Aucun marché approprié trouvé pour spin-off")
            return None
        
        # 4. Stratégie de sélection
        selection = self._select_from_candidates(candidates, current_markets)
        
        if selection:
            logger.info(f"✅ Marché sélectionné: {selection.symbol} ({selection.market_type.value})")
            logger.info(f"   Raison: {selection.reason}")
            logger.info(f"   Stratégie: {selection.strategy}")
            logger.info(f"   Allocation: {selection.capital_allocation*100:.0f}%")
        
        return selection
    
    def _get_current_markets(self) -> Dict[str, int]:
        """Retourne les marchés actuellement utilisés avec leur nombre d'instances"""
        markets = {}
        
        for instance in self.orchestrator._instances.values():
            symbol = instance.config.symbol
            markets[symbol] = markets.get(symbol, 0) + 1
        
        return markets
    
    def _get_all_available_markets(self) -> List:
        """Retourne tous les marchés disponibles avec leurs métriques"""
        # Symboles supportés
        symbols = [
            # Crypto
            "BTC/EUR", "ETH/EUR", "SOL/EUR", "ADA/EUR",
            # Forex
            "EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF",
            # Commodités (via tokens)
            "GOLD/EUR", "SILVER/EUR"
        ]
        
        markets = []
        for symbol in symbols:
            metrics = self.analyzer.analyze_market(symbol)
            if metrics:
                markets.append(metrics)
        
        return markets
    
    def _filter_candidates(self, markets: List, current_markets: Dict[str, int]) -> List:
        """Filtre les marchés candidats selon critères"""
        candidates = []
        
        for market in markets:
            # Vérifier si marché ouvert
            if not is_market_open(market.symbol):
                continue
            
            # Vérifier qualité minimum
            if market.market_quality.value < self.min_quality_score.value:
                continue
            
            # Vérifier pas déjà trop d'instances sur ce marché
            current_count = current_markets.get(market.symbol, 0)
            if current_count >= self.max_same_market_instances:
                continue
            
            # Vérifier score composite minimum
            if market.composite_score < 40:
                continue
            
            candidates.append(market)
        
        # Trier par score composite
        candidates.sort(key=lambda m: m.composite_score, reverse=True)
        
        return candidates
    
    def _select_from_candidates(self, candidates: List, current_markets: Dict) -> Optional[MarketSelection]:
        """
        Sélectionne parmi les candidats avec logique de diversification.
        """
        if not candidates:
            return None
        
        # Stratégie 1: Si moins de 3 marchés différents, privilégier diversification
        unique_markets = len(current_markets)
        
        if unique_markets < self.min_diversification and len(candidates) > 1:
            # Chercher un marché pas encore utilisé
            new_markets = [c for c in candidates if c.symbol not in current_markets]
            
            if new_markets:
                # Prendre le meilleur nouveau marché
                selected = new_markets[0]
                return MarketSelection(
                    symbol=selected.symbol,
                    market_type=selected.market_type,
                    strategy=selected.recommended_strategy,
                    capital_allocation=selected.recommended_allocation,
                    reason=f"Diversification: nouveau marché {selected.market_type.value} (score: {selected.composite_score:.0f})"
                )
        
        # Stratégie 2: Prendre le meilleur marché disponible
        best = candidates[0]
        
        # Si déjà utilisé, vérifier qu'on ne dépasse pas la limite
        if best.symbol in current_markets:
            count = current_markets[best.symbol]
            if count >= self.max_same_market_instances:
                # Prendre le 2ème meilleur
                if len(candidates) > 1:
                    best = candidates[1]
        
        # Stratégie 3: Si forex et crypto disponibles, diversifier
        has_crypto = any(c.market_type == MarketType.CRYPTO for c in candidates)
        has_forex = any(c.market_type == MarketType.FOREX for c in candidates)
        
        if has_crypto and has_forex:
            # Compter types actuels
            crypto_count = sum(1 for s in current_markets if get_market_config(s) and 
                             get_market_config(s).market_type == MarketType.CRYPTO)
            forex_count = sum(1 for s in current_markets if get_market_config(s) and 
                            get_market_config(s).market_type == MarketType.FOREX)
            
            # Privilégier le type sous-représenté
            if forex_count < crypto_count:
                forex_candidates = [c for c in candidates if c.market_type == MarketType.FOREX]
                if forex_candidates:
                    best = forex_candidates[0]
                    return MarketSelection(
                        symbol=best.symbol,
                        market_type=best.market_type,
                        strategy=best.recommended_strategy,
                        capital_allocation=best.recommended_allocation,
                        reason=f"Équilibrage: privilégie forex (crypto:{crypto_count}, forex:{forex_count})"
                    )
        
        # Sélection par défaut: meilleur marché
        return MarketSelection(
            symbol=best.symbol,
            market_type=best.market_type,
            strategy=best.recommended_strategy,
            capital_allocation=best.recommended_allocation,
            reason=f"Meilleur score composite ({best.composite_score:.0f}/100) - Qualité: {best.market_quality.name}"
        )
    
    def get_market_recommendations(self, top_n: int = 5) -> List[MarketSelection]:
        """
        Retourne les N meilleures recommandations de marchés.
        Utile pour l'UI dashboard.
        """
        markets = self._get_all_available_markets()
        candidates = self._filter_candidates(markets, self._get_current_markets())
        
        recommendations = []
        for market in candidates[:top_n]:
            recommendations.append(MarketSelection(
                symbol=market.symbol,
                market_type=market.market_type,
                strategy=market.recommended_strategy,
                capital_allocation=market.recommended_allocation,
                reason=f"Score: {market.composite_score:.0f}, Vol: {market.volatility_24h:.2f}%, Trend: {market.trend_strength:.2f}"
            ))
        
        return recommendations
    
    def emergency_market_switch(self, instance_id: str, reason: str) -> Optional[MarketSelection]:
        """
        Propose un changement de marché d'urgence.
        Utile si un marché devient trop volatil ou illiquide.
        """
        logger.warning(f"🚨 Analyse changement marché d'urgence pour {instance_id}: {reason}")
        
        # Force une nouvelle analyse
        markets = self._get_all_available_markets()
        
        # Filtre strict: uniquement EXCELLENT ou GOOD
        excellent = [m for m in markets if m.market_quality in 
                    (MarketQualityScore.EXCELLENT, MarketQualityScore.GOOD)]
        
        if excellent:
            best = max(excellent, key=lambda m: m.composite_score)
            return MarketSelection(
                symbol=best.symbol,
                market_type=best.market_type,
                strategy=best.recommended_strategy,
                capital_allocation=best.recommended_allocation,
                reason=f"Urgence: {reason}. Alternative: {best.symbol} (score: {best.composite_score:.0f})"
            )
        
        return None
