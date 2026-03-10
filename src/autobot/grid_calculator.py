"""
Grid Calculator - Calcule les niveaux de grille pour le trading
"""

import logging
from typing import List, Tuple, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class GridConfig:
    """Configuration pour le calcul de la grille"""
    num_levels: int = 15
    range_percent: float = 14.0  # +/- 7% = 14% total
    capital: float = 500.0
    symbol: str = "XXBTZEUR"


class GridCalculator:
    """
    Calcule les niveaux de grille pour le trading grid.
    
    Par défaut: 15 niveaux sur une range de +/- 7% autour du prix central.
    """
    
    def __init__(self, config: GridConfig = None):
        """
        Initialise le calculateur de grille.
        
        Args:
            config: Configuration de la grille (utilise défaut si None)
        """
        self.config = config or GridConfig()
        self.levels: List[float] = []
        self.center_price: float = 0.0
        
    def calculate_grid(self, center_price: float) -> List[float]:
        """
        Calcule les niveaux de grille autour d'un prix central.
        
        Args:
            center_price: Prix central actuel du marché
            
        Returns:
            Liste des 15 niveaux de prix
            
        Raises:
            ValueError: Si le prix central est invalide
        """
        if center_price <= 0:
            raise ValueError(f"Prix central invalide: {center_price}")
        
        self.center_price = center_price
        
        # Calcul de la range (ex: +/- 7% = 14% total)
        half_range = self.config.range_percent / 2 / 100
        lower = center_price * (1 - half_range)
        upper = center_price * (1 + half_range)
        
        # Calcul du step entre chaque niveau
        step = (upper - lower) / (self.config.num_levels - 1)
        
        # Génération des niveaux
        self.levels = [lower + i * step for i in range(self.config.num_levels)]
        
        logger.info(f"📊 Grid calculé ({self.config.num_levels} niveaux):")
        logger.info(f"   Prix centre: €{center_price:,.2f}")
        logger.info(f"   Range: €{lower:,.2f} - €{upper:,.2f}")
        logger.info(f"   Capital/niveau: €{self.config.capital / self.config.num_levels:.2f}")
        
        return self.levels
    
    def get_buy_levels(self) -> List[float]:
        """
        Retourne les niveaux d'achat (inférieurs au prix central).
        
        Returns:
            Liste des niveaux d'achat
        """
        if not self.levels:
            raise ValueError("Grid non calculé. Appelez calculate_grid() d'abord.")
        return [level for level in self.levels if level < self.center_price]
    
    def get_sell_levels(self) -> List[float]:
        """
        Retourne les niveaux de vente (supérieurs au prix central).
        
        Returns:
            Liste des niveaux de vente
        """
        if not self.levels:
            raise ValueError("Grid non calculé. Appelez calculate_grid() d'abord.")
        return [level for level in self.levels if level > self.center_price]
    
    def get_nearest_level(self, price: float) -> float:
        """
        Trouve le niveau de grille le plus proche d'un prix donné.
        
        Args:
            price: Prix à analyser
            
        Returns:
            Niveau de grille le plus proche
        """
        if not self.levels:
            raise ValueError("Grid non calculé. Appelez calculate_grid() d'abord.")
        return min(self.levels, key=lambda x: abs(x - price))
    
    def get_grid_info(self) -> Dict[str, Any]:
        """
        Retourne les informations complètes de la grille.
        
        Returns:
            Dictionnaire avec toutes les infos de la grille
        """
        if not self.levels:
            raise ValueError("Grid non calculé. Appelez calculate_grid() d'abord.")
        
        capital_per_level = self.config.capital / self.config.num_levels
        
        return {
            'num_levels': self.config.num_levels,
            'center_price': self.center_price,
            'lower_price': self.levels[0],
            'upper_price': self.levels[-1],
            'range_percent': self.config.range_percent,
            'capital_total': self.config.capital,
            'capital_per_level': capital_per_level,
            'levels': self.levels,
            'buy_levels': self.get_buy_levels(),
            'sell_levels': self.get_sell_levels(),
            'symbol': self.config.symbol
        }
