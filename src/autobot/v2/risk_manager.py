"""
Risk Manager - Gestion dynamique des risques (SL/TP, levier, exposition)
"""

import logging
import threading
from typing import Dict, Optional, Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RiskConfig:
    """Configuration des risques selon capital"""
    capital_min: float
    capital_max: float
    stop_loss_pct: float  # Ex: -0.20 pour -20%
    take_profit_pct: float  # Ex: 0.30 pour +30%
    max_positions: int
    max_leverage: int
    description: str


class RiskManager:
    """
    Gère les paramètres de risque dynamiques selon le capital.
    
    Plus le capital est élevé, plus on protège (SL plus serré, TP plus conservateur).
    """
    
    # Configuration par niveau de capital
    DEFAULT_CONFIGS = [
        RiskConfig(
            capital_min=100,
            capital_max=499,
            stop_loss_pct=-0.25,
            take_profit_pct=0.40,
            max_positions=5,
            max_leverage=1,
            description="Capital faible - Protection maximale"
        ),
        RiskConfig(
            capital_min=500,
            capital_max=999,
            stop_loss_pct=-0.20,
            take_profit_pct=0.30,
            max_positions=8,
            max_leverage=1,
            description="Capital moyen - Équilibre risque/rendement"
        ),
        RiskConfig(
            capital_min=1000,
            capital_max=1999,
            stop_loss_pct=-0.15,
            take_profit_pct=0.25,
            max_positions=10,
            max_leverage=2,
            description="Capital élevé - Levier x2 possible"
        ),
        RiskConfig(
            capital_min=2000,
            capital_max=4999,
            stop_loss_pct=-0.12,
            take_profit_pct=0.22,
            max_positions=12,
            max_leverage=2,
            description="Capital très élevé - Protection renforcée"
        ),
        RiskConfig(
            capital_min=5000,
            capital_max=float('inf'),
            stop_loss_pct=-0.10,
            take_profit_pct=0.20,
            max_positions=15,
            max_leverage=3,
            description="Capital institutionnel - Gestion conservative"
        )
    ]
    
    def __init__(self, configs: Optional[list] = None):
        self.configs = configs or self.DEFAULT_CONFIGS
        self._on_sl_triggered: Optional[Callable] = None
        self._on_tp_triggered: Optional[Callable] = None
        
        logger.info("🛡️ RiskManager initialisé")
    
    def get_config_for_capital(self, capital: float) -> RiskConfig:
        """Retourne la configuration adaptée au capital"""
        for config in self.configs:
            if config.capital_min <= capital < config.capital_max:
                return config
        
        # Fallback sur dernière config
        return self.configs[-1]
    
    def calculate_sl_price(self, entry_price: float, capital: float, side: str = 'long') -> float:
        """
        Calcule prix du Stop Loss.
        
        Args:
            entry_price: Prix d'entrée
            capital: Capital de l'instance
            side: 'long' ou 'short'
        """
        config = self.get_config_for_capital(capital)
        
        if side == 'long':
            sl_price = entry_price * (1 + config.stop_loss_pct)
        else:
            sl_price = entry_price * (1 - config.stop_loss_pct)
        
        return sl_price
    
    def calculate_tp_price(self, entry_price: float, capital: float, side: str = 'long') -> float:
        """Calcule prix du Take Profit"""
        config = self.get_config_for_capital(capital)
        
        if side == 'long':
            tp_price = entry_price * (1 + config.take_profit_pct)
        else:
            tp_price = entry_price * (1 - config.take_profit_pct)
        
        return tp_price
    
    def check_position_limits(self, open_positions: int, capital: float) -> bool:
        """Vérifie si peut ouvrir nouvelle position"""
        config = self.get_config_for_capital(capital)
        return open_positions < config.max_positions
    
    def check_leverage_allowed(self, capital: float, requested_leverage: int) -> bool:
        """Vérifie si levier autorisé"""
        config = self.get_config_for_capital(capital)
        return requested_leverage <= config.max_leverage
    
    def calculate_position_size(self, capital: float, price: float, 
                                risk_per_trade: float = 0.02) -> float:
        """
        Calcule taille de position selon risque.
        
        Args:
            capital: Capital total
            price: Prix actuel
            risk_per_trade: Risque max par trade (défaut 2%)
        """
        config = self.get_config_for_capital(capital)
        
        # Risque en €
        risk_amount = capital * risk_per_trade
        
        # Distance au SL
        sl_distance = abs(config.stop_loss_pct)
        
        # Volume = risque / (prix * distance_SL)
        if sl_distance > 0 and price > 0:
            volume = risk_amount / (price * sl_distance)
            return volume
        
        return 0.0
    
    def should_emergency_stop(self, drawdown: float, capital: float) -> bool:
        """
        Détermine si arrêt d'urgence nécessaire.
        
        Args:
            drawdown: Drawdown courant (0.30 = -30%)
            capital: Capital restant
        """
        # Arrêt si drawdown > 30%
        if drawdown > 0.30:
            logger.error(f"🚨 STOP: Drawdown critique {drawdown:.2%}")
            return True
        
        # Arrêt si capital < 50% initial
        # (géré ailleurs mais double sécurité)
        
        return False
    
    def get_recommended_leverage(self, capital: float, win_streak: int = 0,
                                  drawdown: float = 0.0) -> int:
        """
        Recommande levier optimal selon situation.
        
        Args:
            capital: Capital disponible
            win_streak: Série de victoires
            drawdown: Drawdown courant
        """
        config = self.get_config_for_capital(capital)
        
        # Base: levier max selon capital
        recommended = 1
        
        if capital >= 1000 and win_streak >= 5 and drawdown < 0.05:
            recommended = 2
        
        if capital >= 5000 and win_streak >= 10 and drawdown < 0.03:
            recommended = 3
        
        # Ne dépasse jamais max
        return min(recommended, config.max_leverage)
    
    def get_summary(self, capital: float) -> Dict:
        """Retourne résumé des paramètres de risque"""
        config = self.get_config_for_capital(capital)
        
        return {
            'capital': capital,
            'stop_loss': f"{config.stop_loss_pct:.1%}",
            'take_profit': f"{config.take_profit_pct:.1%}",
            'max_positions': config.max_positions,
            'max_leverage': config.max_leverage,
            'description': config.description
        }


# Singleton pour usage global - CORRECTION Phase 4: Thread-safe
_risk_manager_instance = None
_risk_manager_lock = threading.Lock()


def get_risk_manager() -> RiskManager:
    """
    Retourne instance globale RiskManager (thread-safe).

    CORRECTION Phase 4: Utilise un lock pour éviter race condition
    si deux threads appellent get_risk_manager() simultanément.
    """
    global _risk_manager_instance

    with _risk_manager_lock:
        if _risk_manager_instance is None:
            _risk_manager_instance = RiskManager()
        return _risk_manager_instance
