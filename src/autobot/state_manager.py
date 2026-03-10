"""
State Manager - Persistence des positions et ordres
"""

import json
import logging
import os
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class StateManager:
    """
    Gère la persistence de l'état du bot.
    
    CORRECTION: Permet de récupérer l'état après un crash.
    Sauvegarde: positions, ordres actifs, capital initial, profits.
    """
    
    DEFAULT_STATE_FILE = "autobot_state.json"
    
    def __init__(self, state_file: str = None):
        """
        Initialise le gestionnaire d'état.
        
        Args:
            state_file: Chemin du fichier d'état (défaut: autobot_state.json)
        """
        self.state_file = state_file or self.DEFAULT_STATE_FILE
        self._ensure_directory()
        
        logger.info(f"💾 StateManager initialisé (fichier: {self.state_file})")
    
    def _ensure_directory(self):
        """Crée le répertoire si nécessaire."""
        dir_path = os.path.dirname(self.state_file)
        if dir_path and not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)
    
    def save_state(
        self,
        positions: Dict[str, Any],
        active_orders: Dict[str, Any],
        initial_capital: float,
        total_profit: float,
        symbol: str = "XXBTZEUR"
    ) -> bool:
        """
        Sauvegarde l'état complet du bot.
        
        Args:
            positions: Dictionnaire des positions
            active_orders: Dictionnaire des ordres actifs
            initial_capital: Capital initial
            total_profit: Profit total réalisé
            symbol: Paire de trading
            
        Returns:
            True si sauvegarde réussie
        """
        state = {
            'version': '1.0.0',
            'timestamp': datetime.now().isoformat(),
            'symbol': symbol,
            'initial_capital': initial_capital,
            'total_profit': total_profit,
            'positions': self._serialize_positions(positions),
            'active_orders': self._serialize_orders(active_orders)
        }
        
        try:
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
            logger.debug(f"💾 État sauvegardé ({len(positions)} positions, {len(active_orders)} ordres)")
            return True
        except Exception as e:
            logger.error(f"❌ Erreur sauvegarde état: {e}")
            return False
    
    def load_state(self) -> Optional[Dict[str, Any]]:
        """
        Charge l'état sauvegardé.
        
        Returns:
            État chargé ou None si pas de fichier
        """
        if not os.path.exists(self.state_file):
            logger.info("📂 Aucun état précédent trouvé (premier démarrage)")
            return None
        
        try:
            with open(self.state_file, 'r') as f:
                state = json.load(f)
            
            logger.info(f"📂 État chargé depuis {self.state_file}")
            logger.info(f"   Dernière sauvegarde: {state.get('timestamp', 'inconnue')}")
            logger.info(f"   Positions: {len(state.get('positions', {}))}")
            logger.info(f"   Ordres actifs: {len(state.get('active_orders', {}))}")
            
            return state
            
        except Exception as e:
            logger.error(f"❌ Erreur chargement état: {e}")
            return None
    
    def _serialize_positions(self, positions: Dict[str, Any]) -> Dict[str, Any]:
        """Sérialise les positions pour JSON."""
        serialized = {}
        for key, pos in positions.items():
            serialized[key] = {
                'buy_order_id': pos.buy_order_id,
                'buy_price': pos.buy_price,
                'volume': pos.volume,
                'sell_order_id': pos.sell_order_id,
                'sell_price': pos.sell_price,
                'status': pos.status.value if hasattr(pos.status, 'value') else pos.status,
                'profit': pos.profit
            }
        return serialized
    
    def _serialize_orders(self, orders: Dict[str, Any]) -> Dict[str, Any]:
        """Sérialise les ordres pour JSON."""
        serialized = {}
        for key, order in orders.items():
            serialized[key] = {
                'id': order.id,
                'symbol': order.symbol,
                'side': order.side.value if hasattr(order.side, 'value') else order.side,
                'order_type': order.order_type.value if hasattr(order.order_type, 'value') else order.order_type,
                'price': order.price,
                'volume': order.volume,
                'status': order.status,
                'filled_volume': order.filled_volume
            }
        return serialized
    
    def backup_state(self) -> bool:
        """
        Crée une sauvegarde de l'état actuel avec timestamp.
        
        Returns:
            True si backup créé
        """
        if not os.path.exists(self.state_file):
            return False
        
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = f"{self.state_file}.{timestamp}.backup"
            
            with open(self.state_file, 'r') as src:
                with open(backup_file, 'w') as dst:
                    dst.write(src.read())
            
            logger.info(f"💾 Backup créé: {backup_file}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Erreur backup: {e}")
            return False
