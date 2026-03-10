#!/usr/bin/env python3
"""
AUTOBOT - Main Entry Point
Bot de trading Grid sur Kraken

Usage:
    python -m autobot.main
    
Environment:
    AUTOBOT_SANDBOX=true              # Mode simulation (défaut)
    AUTOBOT_PRODUCTION_CONFIRMED=YES_I_KNOW_WHAT_IM_DOING  # Pour production
    KRAKEN_API_KEY=xxx
    KRAKEN_API_SECRET=xxx
"""

import os
import sys
import time
import signal
import logging
from pathlib import Path

# Ajoute src au path
sys.path.insert(0, str(Path(__file__).parent.parent))

from autobot.config import load_config, BotConfig
from autobot.grid_calculator import GridCalculator, GridConfig
from autobot.order_manager import OrderManager, OrderSide
from autobot.position_manager import PositionManager
from autobot.market_data import MarketData
from autobot.state_manager import StateManager
from autobot.error_handler import ErrorHandler

# Configuration logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/autobot.log')
    ]
)
logger = logging.getLogger(__name__)


class TradingBot:
    """
    Bot de trading principal.
    
    Boucle principale:
    1. Récupère le prix actuel
    2. Calcule la grille
    3. Place les ordres BUY
    4. Scanne les positions
    5. Vérifie le stop-loss
    6. Sauvegarde l'état
    """
    
    def __init__(self, config: BotConfig):
        """Initialise le bot."""
        self.config = config
        self.running = False
        
        # State manager (persistence)
        self.state_manager = StateManager(config.state_file)
        
        # Order manager
        self.order_manager = OrderManager(
            api_key=config.api_key if not config.sandbox else None,
            api_secret=config.api_secret if not config.sandbox else None,
            sandbox=config.sandbox,
            max_order_value=config.max_order_value,
            max_volume=config.max_volume
        )
        
        # Market data
        self.market_data = MarketData(self.order_manager._get_client())
        
        # Grid calculator
        grid_config = GridConfig(
            num_levels=config.num_levels,
            range_percent=config.range_percent,
            capital=config.capital,
            symbol=config.symbol
        )
        self.grid_calculator = GridCalculator(grid_config)
        
        # Position manager
        self.position_manager = PositionManager(
            order_manager=self.order_manager,
            grid_calculator=self.grid_calculator,
            max_positions=config.max_positions,
            max_drawdown_percent=config.max_drawdown_percent
        )
        
        # Callbacks
        self.position_manager.set_callbacks(
            on_position_filled=self._on_position_filled,
            on_profit_realized=self._on_profit_realized,
            on_stop_loss_triggered=self._on_stop_loss_triggered
        )
        
        # Charger l'état précédent si existe
        self._load_state()
        
        logger.info("🤖 TradingBot initialisé")
        logger.info(f"   Mode: {'SANDBOX' if config.sandbox else 'PRODUCTION'}")
        logger.info(f"   Symbole: {config.symbol}")
        logger.info(f"   Capital: €{config.capital:.2f}")
        logger.info(f"   Polling: {config.poll_interval}s")
    
    def _load_state(self):
        """Charge l'état précédent."""
        state = self.state_manager.load_state()
        if state:
            self.position_manager.set_initial_capital(state.get('initial_capital', self.config.capital))
            logger.info(f"📂 État chargé: {state.get('total_profit', 0):.2f}€ de profit précédent")
    
    def _save_state(self):
        """Sauvegarde l'état actuel."""
        self.state_manager.save_state(
            positions=self.position_manager._positions,
            active_orders=self.order_manager._active_orders,
            initial_capital=self.position_manager._initial_capital or self.config.capital,
            total_profit=self.position_manager.get_total_profit(),
            symbol=self.config.symbol
        )
    
    def _on_position_filled(self, position):
        """Callback: Position remplie (BUY -> SELL placé)."""
        logger.info(f"📈 Position remplie: SELL placé @ €{position.sell_price:,.2f}")
    
    def _on_profit_realized(self, position):
        """Callback: Profit réalisé."""
        logger.info(f"💰 PROFIT: €{position.profit:.2f}")
        self._save_state()
    
    def _on_stop_loss_triggered(self, drawdown):
        """Callback: Stop-loss déclenché."""
        logger.error(f"🚨 STOP-LOSS: Drawdown de {drawdown:.1f}%")
        self._save_state()
        self.stop()
    
    def initialize_grid(self):
        """Initialise la grille avec le prix actuel."""
        logger.info("🔧 Initialisation de la grille...")
        
        # Récupère le prix actuel
        current_price = self.market_data.get_current_price(self.config.symbol)
        if not current_price:
            logger.error("❌ Impossible de récupérer le prix actuel")
            return False
        
        logger.info(f"📊 Prix actuel: €{current_price:,.2f}")
        
        # Calcule la grille
        self.grid_calculator.calculate_grid(current_price)
        
        # Calcule le volume par niveau (dynamique)
        volume_per_level = self.grid_calculator.get_volume_per_level(current_price)
        
        # Place les ordres BUY
        buy_levels = self.grid_calculator.get_buy_levels()
        logger.info(f"📈 Placement de {len(buy_levels)} ordres BUY...")
        
        placed = 0
        for price in buy_levels:
            try:
                order = self.order_manager.place_buy_order(
                    symbol=self.config.symbol,
                    price=price,
                    volume=volume_per_level
                )
                self.position_manager.open_position(order)
                placed += 1
            except Exception as e:
                logger.error(f"❌ Erreur placement ordre @ €{price:,.2f}: {e}")
        
        logger.info(f"✅ {placed}/{len(buy_levels)} ordres BUY placés")
        self._save_state()
        return True
    
    def run_cycle(self):
        """Exécute un cycle de trading."""
        # Récupère le prix actuel
        current_price = self.market_data.get_current_price(self.config.symbol)
        if not current_price:
            logger.warning("⚠️ Prix non disponible, cycle ignoré")
            return
        
        # Scanne les positions
        self.position_manager.scan_all_positions()
        
        # Vérifie le stop-loss
        self.position_manager.check_stop_loss(current_price)
        
        # Nettoie les ordres fermés
        self.order_manager.cleanup_closed_orders()
        self.position_manager.cleanup_closed_positions()
        
        # Sauvegarde l'état
        self._save_state()
        
        # Log status
        open_pos = len(self.position_manager.get_open_positions())
        filled_pos = len(self.position_manager.get_filled_positions())
        total_profit = self.position_manager.get_total_profit()
        
        logger.info(
            f"📊 Status: {open_pos} ouvertes, {filled_pos} en attente SELL, "
            f"Profit: €{total_profit:.2f}"
        )
    
    def run(self):
        """Boucle principale du bot."""
        logger.info("🚀 Démarrage du bot...")
        self.running = True
        
        # Initialize la grille au démarrage
        if not self.initialize_grid():
            logger.error("❌ Échec initialisation grille")
            return
        
        logger.info(f"🔄 Boucle principale démarrée (intervalle: {self.config.poll_interval}s)")
        
        try:
            while self.running:
                self.run_cycle()
                time.sleep(self.config.poll_interval)
        except KeyboardInterrupt:
            logger.info("🛑 Interruption clavier reçue")
        except Exception as e:
            logger.error(f"❌ Erreur dans la boucle principale: {e}")
        finally:
            self.stop()
    
    def stop(self):
        """Arrête proprement le bot."""
        logger.info("🛑 Arrêt du bot...")
        self.running = False
        
        # Sauvegarde l'état final
        self._save_state()
        
        # Annule tous les ordres (optionnel - selon stratégie)
        # self.order_manager.cancel_all_orders()
        
        logger.info("👋 Bot arrêté")


def signal_handler(bot):
    """Gestionnaire de signaux pour arrêt propre."""
    def handler(signum, frame):
        logger.info(f"📡 Signal {signum} reçu")
        bot.stop()
        sys.exit(0)
    return handler


def main():
    """Point d'entrée principal."""
    try:
        # Charge la configuration
        config = load_config()
        
        # Crée et démarre le bot
        bot = TradingBot(config)
        
        # Gestion des signaux
        signal.signal(signal.SIGINT, signal_handler(bot))
        signal.signal(signal.SIGTERM, signal_handler(bot))
        
        # Démarre
        bot.run()
        
    except Exception as e:
        logger.error(f"❌ Erreur fatale: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
