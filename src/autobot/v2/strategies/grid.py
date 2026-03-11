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
    - capital_per_level: Capital alloué par niveau en €
    - max_positions: Nombre max de positions ouvertes
    """
    
    def __init__(self, instance: Any, config: Optional[Dict] = None):
        super().__init__(instance, config)
        
        # Configuration
        self.center_price = self.config.get('center_price', 50000.0)
        self.range_percent = self.config.get('range_percent', 7.0)
        self.num_levels = self.config.get('num_levels', 15)
        self.capital_per_level = self.config.get('capital_per_level', 33.0)
        self.max_positions = self.config.get('max_positions', 10)
        
        # Niveaux de la grille
        self.grid_levels: List[float] = []
        self._init_grid()
        
        # Suivi des positions ouvertes par niveau
        self.open_levels: Dict[int, Dict] = {}  # level_index -> position_info
        
        # Historique des prix
        self._price_history: deque = deque(maxlen=100)
        
        # État
        self._initialized = True
        
        logger.info(f"📊 Grid Strategy: {self.num_levels} niveaux, "
                   f"±{self.range_percent}% sur {self.center_price:.0f}€")
    
    def _init_grid(self):
        """Initialise les niveaux de la grille"""
        self.grid_levels = calculate_grid_levels(
            center_price=self.center_price,
            range_percent=self.range_percent,
            num_levels=self.num_levels
        )
        
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
        
        # On achète aux niveaux inférieurs (0 à nearest-1)
        buy_levels = []
        for i in range(nearest):
            if i not in self.open_levels:  # Pas déjà de position
                buy_levels.append(i)
        
        return buy_levels
    
    def _get_sell_levels(self, current_price: float) -> List[int]:
        """
        Retourne les niveaux de vente potentiels (au-dessus du prix actuel).
        On vend les positions ouvertes qui sont en profit.
        """
        sell_levels = []
        
        for level_idx, position in self.open_levels.items():
            level_price = self.grid_levels[level_idx]
            
            # On vend si le prix actuel est supérieur au niveau + marge
            if current_price > level_price * 1.005:  # +0.5% de marge
                sell_levels.append(level_idx)
        
        return sell_levels
    
    def _can_open_position(self) -> bool:
        """Vérifie si on peut ouvrir une nouvelle position"""
        # Limite de positions
        if len(self.open_levels) >= self.max_positions:
            return False
        
        # Capital disponible
        available = self.instance.get_available_capital()
        if available < self.capital_per_level:
            return False
        
        return True
    
    def on_price(self, price: float):
        """
        Analyse le prix et émet des signaux si nécessaire.
        """
        if not self._initialized:
            return
        
        self._price_history.append(price)
        
        symbol = self.instance.config.symbol
        
        # 1. Check ventes (positions à fermer en profit)
        sell_levels = self._get_sell_levels(price)
        for level_idx in sell_levels:
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
            
            self.emit_signal(signal)
        
        # 2. Check achats (nouveaux niveaux)
        if self._can_open_position():
            buy_levels = self._get_buy_levels(price)
            
            # On prend le niveau le plus proche (meilleur prix)
            if buy_levels:
                best_level = max(buy_levels)  # Plus proche du prix actuel
                level_price = self.grid_levels[best_level]
                
                # Calcul volume
                volume = self.capital_per_level / price
                
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
        # Trouve quel niveau correspond à cette position
        entry_price = position.buy_price
        nearest_level = self._find_nearest_level(entry_price)
        
        if nearest_level >= 0:
            self.open_levels[nearest_level] = {
                'entry_price': entry_price,
                'volume': position.volume,
                'opened_at': datetime.now()
            }
            
            logger.info(f"📊 Position ouverte niveau {nearest_level}: "
                       f"{entry_price:.0f}€ x {position.volume:.6f}")
    
    def on_position_closed(self, position: Any, profit: float):
        """Appelé quand une position est fermée"""
        # Trouve et retire le niveau correspondant
        entry_price = position.buy_price
        nearest_level = self._find_nearest_level(entry_price)
        
        if nearest_level in self.open_levels:
            del self.open_levels[nearest_level]
            
            logger.info(f"📊 Position fermée niveau {nearest_level}: "
                       f"P&L = {profit:+.2f}€")
    
    def get_status(self) -> Dict[str, Any]:
        """Statut de la stratégie Grid"""
        base_status = super().get_status()
        
        return {
            **base_status,
            'grid': {
                'center_price': self.center_price,
                'range_percent': self.range_percent,
                'num_levels': self.num_levels,
                'levels': self.grid_levels,
                'open_positions': len(self.open_levels),
                'max_positions': self.max_positions,
                'open_levels': list(self.open_levels.keys())
            }
        }
    
    def reset(self):
        """Réinitialise la grille"""
        self.open_levels.clear()
        self._price_history.clear()
        super().reset()
        logger.info("📊 Grid Strategy réinitialisée")
