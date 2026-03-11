"""
Grid Strategy - Trading sur grille de prix
Achat aux supports, vente aux résistances
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from collections import deque

from . import Strategy, TradingSignal, SignalType, calculate_grid_levels, PositionSizing

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
        self.range_percent = self.config.get('range_percent', 7.0)
        self.num_levels = self.config.get('num_levels', 15)
        # CORRECTION Point #5: capital_per_level devient un MAX, pas une valeur fixe
        self.max_capital_per_level = self.config.get('max_capital_per_level', 50.0)
        self.max_positions = self.config.get('max_positions', 10)
        
        # Niveaux de la grille
        self.grid_levels: List[float] = []
        self._init_grid()
        
        # Suivi des positions ouvertes par niveau (protégé par self._lock)
        self.open_levels: Dict[int, Dict] = {}  # level_index -> position_info
        
        # CORRECTION: Seuil de vente dynamique basé sur le step de la grille
        grid_step = self.range_percent / (self.num_levels - 1) if self.num_levels > 1 else 0.5
        self._sell_threshold_pct = max(0.5, grid_step * 0.8)  # 80% du step, min 0.5%
        
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
        """Initialise les niveaux de la grille"""
        self.grid_levels = calculate_grid_levels(
            center_price=self.center_price,
            range_percent=self.range_percent,
            num_levels=self.num_levels
        )
        
        # CORRECTION Point #5: Validation capital minimum au démarrage
        available = self.instance.get_current_capital()
        min_required = self.num_levels * 5.0  # Minimum 5€ par niveau
        
        if available < min_required:
            logger.error(f"❌ Capital insuffisant: {available:.2f}€ < {min_required:.2f}€ minimum "
                        f"({self.num_levels} niveaux × 5€)")
            raise ValueError(f"Capital insuffisant pour Grid Strategy: {available:.2f}€")
        
        # Log du capital dynamique calculé
        dynamic = self._calculate_dynamic_capital_per_level()
        logger.info(f"💰 Capital dynamique: {dynamic:.2f}€/niveau "
                   f"(max: {self.max_capital_per_level}€, disponible: {available:.2f}€)")
        
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
    
    def _calculate_dynamic_capital_per_level(self) -> float:
        """
        CORRECTION Point #5: Calcul dynamique du capital par niveau selon capital disponible.
        
        Au lieu d'utiliser capital_per_level fixe (33€), on calcule dynamiquement:
        - Capital disponible / nombre de niveaux × facteur d'utilisation
        - Garantit qu'on ne dépasse jamais le budget total
        
        Returns:
            Capital alloué par niveau en €
        """
        available = self.instance.get_current_capital()
        
        # Nombre de niveaux d'achat (moitié inférieure de la grille)
        buy_levels_count = self.num_levels // 2
        if buy_levels_count < 1:
            buy_levels_count = 1
        
        # Utiliser max 90% du capital disponible (marge de sécurité 10%)
        usable_capital = available * 0.90
        
        # Capital par niveau = capital utilisable / nombre de niveaux d'achat
        dynamic_capital = usable_capital / buy_levels_count
        
        # Plafonner par max_capital_per_level pour ne pas sur-allouer
        max_per_level = self.max_capital_per_level
        
        # Minimum de 5€ par niveau (sinon pas assez pour un ordre significatif)
        min_per_level = 5.0
        
        result = max(min_per_level, min(dynamic_capital, max_per_level))
        
        logger.debug(f"💰 Capital dynamique: {result:.2f}€ (disponible: {available:.2f}€, "
                    f"niveaux achat: {buy_levels_count})")
        
        return result
    
    def _can_open_position(self) -> bool:
        """Vérifie si on peut ouvrir une nouvelle position"""
        # CORRECTION: Accès sous lock pour thread safety
        with self._lock:
            open_count = len(self.open_levels)
        
        # Limite de positions
        if open_count >= self.max_positions:
            return False
        
        # CORRECTION Point #5: Utiliser capital par niveau calculé dynamiquement
        capital_per_level = self._calculate_dynamic_capital_per_level()
        available = self.instance.get_current_capital()
        if available < capital_per_level:
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
    
    def on_price(self, price: float):
        """
        Analyse le prix et émet des signaux si nécessaire.
        """
        if not self._initialized:
            return
        
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
                with self._lock:
                    all_levels = list(self.open_levels.keys())
                
                for i, level_idx in enumerate(all_levels):
                    position = self.open_levels[level_idx]
                    signal = TradingSignal(
                        type=SignalType.SELL,
                        symbol=symbol,
                        price=price,
                        volume=position['volume'],
                        reason=f"EMERGENCY: Grid invalidated - level {level_idx}",
                        timestamp=datetime.now(),
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
                position = self.open_levels[emergency_level]
                logger.warning(f"🛑 STOP-LOSS: Level {emergency_level} atteint drawdown max "
                              f"({self._max_drawdown_pct}%). Vente forcée.")
                
                signal = TradingSignal(
                    type=SignalType.SELL,
                    symbol=symbol,
                    price=price,
                    volume=position['volume'],
                    reason=f"STOP-LOSS: Drawdown {self._max_drawdown_pct}% atteint",
                    timestamp=datetime.now(),
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
            # CORRECTION: Batch sells - bypass cooldown pour tous sauf le premier
            for i, level_idx in enumerate(sell_levels):
                position = self.open_levels[level_idx]
                level_price = self.grid_levels[level_idx]
                
                profit_pct = (price - level_price) / level_price * 100
                
                signal = TradingSignal(
                    type=SignalType.SELL,
                    symbol=symbol,
                    price=price,
                    volume=position['volume'],
                    reason=f"Grid level {level_idx} profit: +{profit_pct:.2f}%",
                    timestamp=datetime.now(),
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
            if self._can_open_position():
                buy_levels = self._get_buy_levels(price)
                
                # On prend le niveau le plus proche (meilleur prix)
                if buy_levels:
                    best_level = max(buy_levels)  # Plus proche du prix actuel
                    level_price = self.grid_levels[best_level]
                    
                    # CORRECTION Point #5: Calcul dynamique du capital puis du volume
                    capital_per_level = self._calculate_dynamic_capital_per_level()
                    volume = capital_per_level / price
                    
                    signal = TradingSignal(
                        type=SignalType.BUY,
                        symbol=symbol,
                        price=price,
                        volume=volume,
                        reason=f"Grid buy level {best_level} @ {level_price:.0f}",
                        timestamp=datetime.now(),
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
                        'opened_at': datetime.now()
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
        
        # CORRECTION Point #5: Inclure le capital dynamique dans le statut
        dynamic_capital = self._calculate_dynamic_capital_per_level()
        
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
                # CORRECTION Point #5: Exposer le capital dynamique
                'capital_per_level': {
                    'dynamic': dynamic_capital,
                    'max': self.max_capital_per_level,
                    'available_capital': self.instance.get_current_capital()
                },
                'protection': {
                    'max_drawdown_pct': self._max_drawdown_pct,
                    'emergency_price': self._emergency_close_price,
                    'emergency_mode': self._emergency_mode,
                    'sell_threshold_pct': self._sell_threshold_pct
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
