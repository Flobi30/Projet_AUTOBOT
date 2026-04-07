"""
Grid Strategy - Trading sur grille de prix
Achat aux supports, vente aux résistances
"""

import logging
import math
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timezone
from collections import deque

from . import Strategy, TradingSignal, SignalType, calculate_grid_levels, PositionSizing
from autobot.v2.modules.regime_detector import RegimeDetector, MarketRegime
from autobot.v2.modules.funding_rates import FundingRatesMonitor
from autobot.v2.modules.open_interest import OpenInterestMonitor
from autobot.v2.modules.kelly_criterion import KellyCriterion

logger = logging.getLogger(__name__)


class GridStrategy(Strategy):
    """
    Stratégie de trading sur grille (Grid Trading).
    
    Principe:
    - Définit N niveaux de prix autour d'un prix central
    - Achète aux niveaux inférieurs (supports)
    - Vend aux niveaux supérieurs (résistances)
    - Profite des oscillations latérales
    
    Configuration:
    - center_price: Prix central de la grille
    - range_percent: Range total +/- (ex: 7 pour +/- 7%)
    - num_levels: Nombre de niveaux (défaut: 15)
    - max_capital_per_level: Capital MAXIMUM par niveau en € (dynamique selon capital)
    - max_positions: Nombre max de positions ouvertes
    
    CORRECTION Point #5: Le capital par niveau est calculé dynamiquement:
    - Si capital faible: réduction automatique (min 5€/niveau)
    - Si capital élevé: utilisation du max configuré
    - Garantit qu'on ne dépasse jamais le budget total disponible
    """
    
    def __init__(self, instance: Any, config: Optional[Dict] = None):
        super().__init__(instance, config)
        
        # Configuration
        self.center_price = self.config.get('center_price', 50000.0)
        self.range_percent = self.config.get('range_percent', 2.0)
        self.num_levels = self.config.get('num_levels', 15)
        # CORRECTION Point #5: capital_per_level devient un MAX, pas une valeur fixe
        self.max_capital_per_level = self.config.get('max_capital_per_level', 50.0)
        self.max_positions = self.config.get('max_positions', 10)
        
        # Niveaux de la grille
        self.grid_levels: List[float] = []
        
        # CORRECTION Point #5: Capital par niveau calculé UNE SEULE FOIS à l'init
        # Évite l'effet "Shrinking Orders" et les appels API redondants
        self._runtime_capital_per_level: float = 0.0
        
        self._init_grid()
        
        # Phase 1 modules
        self._regime_detector = RegimeDetector()
        self._funding_monitor = FundingRatesMonitor()
        self._oi_monitor = OpenInterestMonitor()
        self._kelly = KellyCriterion()
        
        # Suivi des positions ouvertes par niveau (protégé par self._lock)
        self.open_levels: Dict[int, Dict] = {}  # level_index -> position_info
        
        # CORRECTION: Seuil de vente dynamique basé sur le step de la grille
        # CRITIQUE: Doit couvrir les frais Kraken (~0.52% taker + 0.52% taker = ~1.04%)
        # + marge minimum 0.5% → minimum 1.5% pour être rentable
        grid_step = self.range_percent / (self.num_levels - 1) if self.num_levels > 1 else 0.5
        self._sell_threshold_pct = max(1.5, grid_step * 0.8)  # CORRECTION: min 1.5% pas 0.5%
        
        # CORRECTION: Protection drawdown / stop-loss
        self._max_drawdown_pct = self.config.get('max_drawdown_pct', 10.0)  # Stop si -10%
        self._grid_invalidation_factor = self.config.get('grid_invalidation_factor', 2.0)  # 2× range
        self._emergency_close_price = self.center_price * (1 - self.range_percent * self._grid_invalidation_factor / 100)
        
        # Historique des prix
        self._price_history: deque = deque(maxlen=100)
        
        # État
        self._initialized = True
        self._emergency_mode = False  # Mode urgence activé si crash
        
        logger.info(f"📊 Grid Strategy: {self.num_levels} niveaux, "
                   f"±{self.range_percent}% sur {self.center_price:.0f}€")
    
    def _init_grid(self):
        """Initialise les niveaux de la grille et calcule le capital par niveau"""
        self.grid_levels = calculate_grid_levels(
            center_price=self.center_price,
            range_percent=self.range_percent,
            num_levels=self.num_levels
        )
        
        # CORRECTION Point #5: Calculer le capital UNE SEULE FOIS à l'initialisation
        # CORRECTION: Utiliser get_available_capital() (non alloué) pas get_current_capital() (total)
        available = self.instance.get_available_capital()
        
        # CORRECTION: Guard contre capital négatif ou nul
        if available <= 0:
            logger.error(f"❌ Capital négatif ou nul: {available:.2f}€")
            raise ValueError(f"Capital invalide pour Grid Strategy: {available:.2f}€")
        
        # CORRECTION Point #5: Utiliser max_positions pour le calcul (pas num_levels // 2)
        # C'est le nombre max réel de positions qu'on peut ouvrir
        max_possible_buys = max(1, self.max_positions)
        
        # Utiliser max 90% du capital disponible (marge de sécurité 10%)
        usable_capital = available * 0.90
        
        # Capital par niveau = capital utilisable / nombre max de positions
        dynamic_capital = usable_capital / max_possible_buys
        
        # Borner entre 5€ et max_capital_per_level
        self._runtime_capital_per_level = max(5.0, min(dynamic_capital, self.max_capital_per_level))
        
        # Validation cohérente avec le runtime
        min_required = max_possible_buys * 5.0 / 0.90  # Aligné avec le calcul
        
        if available < min_required:
            logger.error(f"❌ Capital insuffisant: {available:.2f}€ < {min_required:.2f}€ minimum "
                        f"({max_possible_buys} positions max × 5€ / 0.90)")
            raise ValueError(f"Capital insuffisant pour Grid Strategy: {available:.2f}€")
        
        logger.info(f"💰 Capital par niveau: {self._runtime_capital_per_level:.2f}€ "
                   f"(max: {self.max_capital_per_level}€, disponible: {available:.2f}€, "
                   f"positions max: {max_possible_buys})")
        
        logger.debug(f"📊 Niveaux grille ({len(self.grid_levels)}): "
                    f"{self.grid_levels[0]:.0f} → {self.grid_levels[-1]:.0f}")
    
    def _find_nearest_level(self, price: float) -> int:
        """Trouve l'index du niveau le plus proche du prix"""
        if not self.grid_levels:
            return -1
        
        nearest_idx = 0
        min_distance = abs(price - self.grid_levels[0])
        
        for i, level in enumerate(self.grid_levels):
            distance = abs(price - level)
            if distance < min_distance:
                min_distance = distance
                nearest_idx = i
        
        return nearest_idx
    
    def _get_buy_levels(self, current_price: float) -> List[int]:
        """
        Retourne les niveaux d'achat potentiels (sous le prix actuel).
        On achète aux niveaux inférieurs pour revendre plus haut.
        """
        nearest = self._find_nearest_level(current_price)
        if nearest < 0:
            return []
        
        # CORRECTION: Copier sous lock pour thread safety
        with self._lock:
            open_levels_copy = dict(self.open_levels)
        
        # On achète aux niveaux inférieurs (0 à nearest-1)
        buy_levels = []
        for i in range(nearest):
            if i not in open_levels_copy:  # Pas déjà de position
                buy_levels.append(i)
        
        return buy_levels
    
    def _get_sell_levels(self, current_price: float) -> List[int]:
        """
        Retourne les niveaux de vente potentiels (au-dessus du prix actuel).
        On vend les positions ouvertes qui sont en profit.
        """
        sell_levels = []
        
        # CORRECTION: Copier sous lock pour thread safety
        with self._lock:
            open_levels_copy = dict(self.open_levels)
        
        for level_idx, position in open_levels_copy.items():
            level_price = self.grid_levels[level_idx]
            
            # CORRECTION: Seuil de vente dynamique (pas hardcodé à 0.5%)
            if current_price > level_price * (1 + self._sell_threshold_pct / 100):
                sell_levels.append(level_idx)
        
        return sell_levels
    
    def _calculate_dynamic_capital_per_level(self, available_capital: Optional[float] = None) -> float:
        """
        CORRECTION Point #5: Retourne le capital par niveau calculé à l'initialisation.
        
        Le capital est calculé UNE SEULE FOIS dans _init_grid() pour éviter:
        - L'effet "Shrinking Orders" (volumes qui diminuent après chaque achat)
        - Les appels API redondants à chaque tick de prix
        
        Args:
            available_capital: Capital disponible (pour validation, optionnel)
            
        Returns:
            Capital alloué par niveau en €
        """
        # CORRECTION: Guard contre capital négatif ou nul
        if available_capital is not None and available_capital <= 0:
            logger.warning(f"⚠️ Capital négatif ou nul: {available_capital}")
            return 0.0  # Pas de trading
        
        # Retourne la valeur calculée à l'initialisation
        return self._runtime_capital_per_level
    
    def _can_open_position(self, available_capital: float) -> bool:
        """
        Vérifie si on peut ouvrir une nouvelle position.
        
        Args:
            available_capital: Capital disponible (snapshot unique du cycle)
            
        Returns:
            True si on peut ouvrir une position
        """
        # CORRECTION: Accès sous lock pour thread safety
        with self._lock:
            open_count = len(self.open_levels)
        
        # Limite de positions
        if open_count >= self.max_positions:
            return False
        
        # CORRECTION Point #5: Utiliser capital par niveau calculé à l'init + snapshot capital
        capital_per_level = self._calculate_dynamic_capital_per_level(available_capital)
        if capital_per_level <= 0:
            return False
            
        if available_capital < capital_per_level:
            return False
        
        return True
    
    def _check_drawdown(self, current_price: float) -> Optional[int]:
        """
        Vérifie si le drawdown max est atteint sur une position.
        Retourne le level_idx à vendre en urgence, ou None.
        """
        with self._lock:
            open_levels_copy = dict(self.open_levels)
        
        for level_idx, position in open_levels_copy.items():
            entry_price = position['entry_price']
            current_drawdown = (entry_price - current_price) / entry_price * 100
            
            if current_drawdown >= self._max_drawdown_pct:
                return level_idx
        
        return None
    
    def _is_grid_invalidated(self, current_price: float) -> bool:
        """
        Vérifie si le prix est sorti de la grille (crash sous les niveaux).
        """
        return current_price < self._emergency_close_price

    def _check_grid_drift(self, price: float) -> bool:
        """
        Recentre la grille si le prix a dérivé de plus de 5% du centre actuel.

        Met à jour center_price, recalcule les niveaux et recalcule
        _emergency_close_price. Retourne True si recentrage effectué.

        N'est appelé que hors mode urgence et hors positions ouvertes,
        pour éviter de perturber des ordres actifs.
        """
        if self._emergency_mode:
            return False
        drift = abs(price - self.center_price) / self.center_price
        if drift <= 0.05:
            return False
        # Recentrage uniquement si aucune position ouverte (sécurité)
        with self._lock:
            has_open = bool(self.open_levels)
        if has_open:
            return False
        self.center_price = price
        self._init_grid()
        self._emergency_close_price = (
            self.center_price
            * (1 - self.range_percent * self._grid_invalidation_factor / 100)
        )
        logger.info(
            f"🔄 Grille recentrée sur {price:.0f} "
            f"(seuil urgence: {self._emergency_close_price:.0f})"
        )
        return True
    
    def on_price(self, price: float):
        """
        Analyse le prix et émet des signaux si nécessaire.
        """
        if not self._initialized:
            return

        # CORRECTION P0: Guard contre prix invalide (NaN, Inf, division par zéro)
        if not math.isfinite(price) or price <= 0:
            logger.error(f"❌ Prix invalide: {price}. Ignoré.")
            return

        # CORRECTION: Vérifie que les données WebSocket sont fraîches
        # Évite de trader sur des prix obsolètes si déconnexion/reconnexion
        if hasattr(self.instance, 'orchestrator') and self.instance.orchestrator:
            ws_client = self.instance.orchestrator.ws_client
            if hasattr(ws_client, 'is_data_fresh') and not ws_client.is_data_fresh():
                logger.warning(f"⏸️ {self.instance.id}: Données WebSocket stale, signal ignoré")
                return

        # S3: Recentre la grille si dérive > 5% (met à jour _emergency_close_price)
        self._check_grid_drift(price)

        # CORRECTION P1: Snapshot unique du capital pour tout le cycle
        # Évite les appels API redondants et les incohérences
        # CORRECTION F4: Utiliser get_available_capital() (capital libre) pas get_current_capital() (total)
        available_capital = self.instance.get_available_capital()
        
        with self._lock:
            self._price_history.append(price)
            symbol = self.instance.config.symbol
            
            # CORRECTION: 0. Check drawdown et grid invalidation (protection urgence)
            if not self._emergency_mode:
                # Check si prix sous le niveau d'invalidation
                if self._is_grid_invalidated(price):
                    self._emergency_mode = True
                    logger.error(f"🚨 GRID INVALIDATED: prix {price:.0f} < {self._emergency_close_price:.0f}. "
                                f"Mode urgence activé - fermeture toutes positions!")
            
            # Si mode urgence, vendre TOUTES les positions
            if self._emergency_mode:
                # Déjà sous self._lock (outer) — pas de lock imbriqué nécessaire
                all_positions = list(self.open_levels.items())  # (level_idx, position_info)
                
                for i, (level_idx, position) in enumerate(all_positions):
                    signal = TradingSignal(
                        type=SignalType.SELL,
                        symbol=symbol,
                        price=price,
                        volume=position['volume'],
                        reason=f"EMERGENCY: Grid invalidated - level {level_idx}",
                        timestamp=datetime.now(timezone.utc),
                        metadata={
                            'level_index': level_idx,
                            'emergency': True,
                            'grid_low': self.grid_levels[0],
                            'current_price': price,
                            'strategy': 'grid'
                        }
                    )
                    self.emit_signal(signal, bypass_cooldown=(i > 0))
                return  # Sortir, pas d'achat en mode urgence
            
            # Check drawdown individuel sur chaque position
            emergency_level = self._check_drawdown(price)
            if emergency_level is not None:
                # Déjà sous self._lock (outer) — accès direct
                position = self.open_levels.get(emergency_level)
                    
                if position is None:
                    logger.warning(f"⚠️ Position d'urgence {emergency_level} déjà fermée")
                else:
                    logger.warning(f"🛑 STOP-LOSS: Level {emergency_level} atteint drawdown max "
                                  f"({self._max_drawdown_pct}%). Vente forcée.")
                    
                    signal = TradingSignal(
                        type=SignalType.SELL,
                        symbol=symbol,
                        price=price,
                        volume=position['volume'],
                        reason=f"STOP-LOSS: Drawdown {self._max_drawdown_pct}% atteint",
                        timestamp=datetime.now(timezone.utc),
                        metadata={
                            'level_index': emergency_level,
                            'stop_loss': True,
                            'drawdown_pct': self._max_drawdown_pct,
                            'strategy': 'grid'
                        }
                    )
                    self.emit_signal(signal)
            
            # 1. Check ventes normales (positions à fermer en profit)
            sell_levels = self._get_sell_levels(price)
            # Déjà sous self._lock (outer) — copie directe sans lock imbriqué
            sell_positions = []
            for level_idx in sell_levels:
                position = self.open_levels.get(level_idx)
                if position:
                    level_price = self.grid_levels[level_idx]
                    sell_positions.append((level_idx, position, level_price))
            
            # CORRECTION: Batch sells - bypass cooldown pour tous sauf le premier
            for i, (level_idx, position, level_price) in enumerate(sell_positions):
                profit_pct = (price - level_price) / level_price * 100
                
                signal = TradingSignal(
                    type=SignalType.SELL,
                    symbol=symbol,
                    price=price,
                    volume=position['volume'],
                    reason=f"Grid level {level_idx} profit: +{profit_pct:.2f}%",
                    timestamp=datetime.now(timezone.utc),
                    metadata={
                        'level_index': level_idx,
                        'level_price': level_price,
                        'entry_price': position['entry_price'],
                        'profit_pct': profit_pct,
                        'strategy': 'grid'
                    }
                )
                
                # CORRECTION: Bypass cooldown pour batch sells (tous sauf premier)
                self.emit_signal(signal, bypass_cooldown=(i > 0))
            
            # CORRECTION: 2. Check achats (nouveaux niveaux) - DANS le lock
            # Phase 1: Vérifications modules avant ouverture de position
            # Funding rates extrême → pas d'achat
            funding_rate = None
            if hasattr(self.instance, 'get_funding_rate'):
                funding_rate = self.instance.get_funding_rate()
            if funding_rate is not None and not self._funding_monitor.update(funding_rate):
                logger.info(f"⏸️ Grid: Funding rate extrême ({funding_rate}), pas d'achat")
                return
            
            # Squeeze risk (OI) → pas d'achat
            if self._oi_monitor.is_squeeze_risk():
                logger.info(f"⏸️ Grid: Squeeze risk détecté (OI), pas d'achat")
                return
            
            # Régime de marché → Grid trade uniquement en range
            if not self._regime_detector.should_trade_grid():
                logger.info(f"⏸️ Grid: Marché hors range, pas d'achat")
                return
            
            # Passe le snapshot du capital pour éviter appels multiples
            if self._can_open_position(available_capital):
                buy_levels = self._get_buy_levels(price)
                
                # On prend le niveau le plus proche (meilleur prix)
                if buy_levels:
                    best_level = max(buy_levels)  # Plus proche du prix actuel
                    level_price = self.grid_levels[best_level]
                    
                    # CORRECTION Point #5: Utiliser capital calculé à l'init (pas recalculé)
                    capital_per_level = self._calculate_dynamic_capital_per_level(available_capital)
                    if capital_per_level > 0:
                        volume = capital_per_level / price
                        
                        signal = TradingSignal(
                            type=SignalType.BUY,
                            symbol=symbol,
                            price=price,
                            volume=volume,
                            reason=f"Grid buy level {best_level} @ {level_price:.0f}",
                            timestamp=datetime.now(timezone.utc),
                            metadata={
                                'level_index': best_level,
                                'level_price': level_price,
                                'grid_center': self.center_price,
                                'strategy': 'grid'
                            }
                        )
                        
                        self.emit_signal(signal)
    
    def on_position_opened(self, position: Any):
        """Appelé quand une position est ouverte"""
        try:
            # CORRECTION: Vérification hasattr pour robustesse
            if not hasattr(position, 'buy_price') or not hasattr(position, 'volume'):
                logger.error("❌ Position object manque buy_price ou volume")
                return
            
            # Trouve quel niveau correspond à cette position
            entry_price = position.buy_price
            nearest_level = self._find_nearest_level(entry_price)
            
            if nearest_level >= 0:
                # CORRECTION: Lock pour thread safety
                with self._lock:
                    self.open_levels[nearest_level] = {
                        'entry_price': entry_price,
                        'volume': position.volume,
                        'opened_at': datetime.now(timezone.utc)
                    }
                
                logger.info(f"📊 Position ouverte niveau {nearest_level}: "
                           f"{entry_price:.0f}€ x {position.volume:.6f}")
        except Exception as e:
            logger.exception(f"❌ Erreur on_position_opened: {e}")
    
    def on_position_closed(self, position: Any, profit: float):
        """Appelé quand une position est fermée"""
        try:
            # CORRECTION: Vérification hasattr pour robustesse
            if not hasattr(position, 'buy_price'):
                logger.error("❌ Position object manque buy_price")
                return
            
            # Trouve et retire le niveau correspondant
            entry_price = position.buy_price
            nearest_level = self._find_nearest_level(entry_price)
            
            # CORRECTION: Lock pour thread safety
            with self._lock:
                if nearest_level in self.open_levels:
                    del self.open_levels[nearest_level]
            
            logger.info(f"📊 Position fermée niveau {nearest_level}: "
                       f"P&L = {profit:+.2f}€")
        except Exception as e:
            logger.exception(f"❌ Erreur on_position_closed: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """Statut de la stratégie Grid"""
        base_status = super().get_status()
        
        # CORRECTION: Copier sous lock pour thread safety
        with self._lock:
            open_levels_keys = list(self.open_levels.keys())
            open_count = len(self.open_levels)
        
        # CORRECTION Point #5: Utiliser le capital calculé à l'init (pas d'appel API)
        # Note: get_current_capital() est appelé une seule fois ici pour le statut
        available_capital = self.instance.get_current_capital()
        
        return {
            **base_status,
            'grid': {
                'center_price': self.center_price,
                'range_percent': self.range_percent,
                'num_levels': self.num_levels,
                'levels': self.grid_levels,
                'open_positions': open_count,
                'max_positions': self.max_positions,
                'open_levels': open_levels_keys,
                # CORRECTION Point #5: Exposer le capital configuré (calculé à l'init)
                'capital_per_level': {
                    'fixed': self._runtime_capital_per_level,
                    'max_configured': self.max_capital_per_level,
                    'available_capital': available_capital
                },
                'protection': {
                    'max_drawdown_pct': self._max_drawdown_pct,
                    'emergency_price': self._emergency_close_price,
                    'emergency_mode': self._emergency_mode,
                    'sell_threshold_pct': self._sell_threshold_pct
                },
                'phase1_modules': {
                    'regime': self._regime_detector.current_regime.value if hasattr(self._regime_detector, 'current_regime') and self._regime_detector.current_regime else 'unknown',
                    'should_trade_grid': self._regime_detector.should_trade_grid(),
                    'squeeze_risk': self._oi_monitor.is_squeeze_risk(),
                }
            }
        }
    
    def reset(self):
        """Réinitialise la grille"""
        with self._lock:
            self.open_levels.clear()
            self._price_history.clear()
            self._emergency_mode = False
        super().reset()
        logger.info("📊 Grid Strategy réinitialisée")
