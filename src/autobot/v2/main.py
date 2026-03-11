"""
main.py - Point d'entrée AUTOBOT V2
Démarre l'orchestrateur et le dashboard
"""

import logging
import os
import sys
import signal
import time
from pathlib import Path
from typing import Optional

# Ajoute src au path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# OPTIMISATION: Logging structuré avec rotation
from autobot.v2.utils import setup_structured_logging

# Setup logging avant tout import qui pourrait logger
setup_structured_logging(
    level=logging.INFO,
    log_file="autobot.log",
    max_bytes=10*1024*1024,  # 10MB
    backup_count=5,
    use_json=True
)

from autobot.v2.orchestrator import Orchestrator, InstanceConfig
from autobot.v2.api.dashboard import DashboardServer
from autobot.v2.persistence import get_persistence, start_maintenance

logger = logging.getLogger(__name__)

class AutoBotV2:
    """
    Application principale AUTOBOT V2
    Gère le cycle de vie complet du bot
    """
    
    def __init__(self, dashboard_host: str = "127.0.0.1", dashboard_port: int = 8080,
                 api_key: Optional[str] = None, api_secret: Optional[str] = None):
        self.orchestrator = None
        self.dashboard = None
        self.running = False
        self.dashboard_host = dashboard_host
        self.dashboard_port = dashboard_port
        self.api_key = api_key or os.getenv('KRAKEN_API_KEY')
        self.api_secret = api_secret or os.getenv('KRAKEN_API_SECRET')
        
    def setup_signal_handlers(self):
        """Configure les handlers pour arrêt propre"""
        def signal_handler(signum, frame):
            logger.info(f"📡 Signal {signum} reçu, arrêt en cours...")
            self.stop()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    def create_default_instance(self) -> InstanceConfig:
        """Crée une instance par défaut pour démarrer"""
        return InstanceConfig(
            name="Instance Principale",
            symbol="XXBTZEUR",  # BTC/EUR sur Kraken
            initial_capital=500.0,
            strategy="grid",
            leverage=1,
            grid_config={
                'range_percent': 7.0,
                'num_levels': 15
            }
        )
    
    def start(self):
        """Démarre le bot et le dashboard"""
        logger.info("="*60)
        logger.info("🚀 DÉMARRAGE AUTOBOT V2")
        logger.info("="*60)
        
        self.setup_signal_handlers()
        self.running = True
        
        try:
            # 1. Crée et démarre l'orchestrateur
            logger.info("🎛️ Initialisation Orchestrateur...")
            self.orchestrator = Orchestrator(api_key=self.api_key, api_secret=self.api_secret)
            
            # Crée l'instance par défaut
            default_config = self.create_default_instance()
            instance = self.orchestrator.create_instance(default_config)
            
            if not instance:
                logger.error("❌ Impossible de créer l'instance par défaut")
                sys.exit(1)
            
            # Démarre l'orchestrateur
            self.orchestrator.start()
            
            # OPTIMISATION: Démarre le maintenance scheduler (backup SQLite + cleanup)
            logger.info("🔧 Démarrage Maintenance Scheduler...")
            persistence = get_persistence()
            start_maintenance(persistence)
            
            # 2. Démarre le dashboard
            logger.info("🌐 Démarrage Dashboard...")
            self.dashboard = DashboardServer(host=self.dashboard_host, port=self.dashboard_port)
            self.dashboard.start(self.orchestrator)

            logger.info("")
            logger.info("="*60)
            logger.info("✅ AUTOBOT V2 DÉMARRÉ AVEC SUCCÈS!")
            logger.info("="*60)
            logger.info("")
            logger.info(f"📊 Dashboard: http://{self.dashboard_host}:{self.dashboard_port}")
            logger.info(f"📈 API: http://{self.dashboard_host}:{self.dashboard_port}/api/status")
            if os.getenv('DASHBOARD_API_TOKEN'):
                logger.info("🔒 Auth: Token configuré (sécurisé)")
            else:
                logger.info("⚠️  Auth: Mode développement (pas de token)")
            logger.info("🛑 Arrêt: Ctrl+C")
            logger.info("")
            
            # Boucle principale
            while self.running:
                time.sleep(1)
                
        except Exception as e:
            logger.exception("❌ Erreur fatale")
            self.stop()
            sys.exit(1)
    
    def stop(self):
        """Arrête proprement le bot"""
        if not self.running:
            return
        
        logger.info("🛑 Arrêt AUTOBOT V2...")
        self.running = False
        
        if self.orchestrator:
            self.orchestrator.stop()
        
        if self.dashboard:
            self.dashboard.stop()
        
        logger.info("✅ Arrêt terminé")


def main():
    """Point d'entrée"""
    # Vérifie les variables d'environnement Kraken
    if not os.getenv('KRAKEN_API_KEY') or not os.getenv('KRAKEN_API_SECRET'):
        logger.warning("⚠️  Clés API Kraken non définies!")
        logger.warning("   Le bot démarrera en mode simulation.")
        logger.warning("   Définissez KRAKEN_API_KEY et KRAKEN_API_SECRET pour le trading réel.")
        logger.info("")
    
    bot = AutoBotV2()
    bot.start()


if __name__ == "__main__":
    main()
