"""
Configuration - Gestion des variables d'environnement et settings
"""

import os
import logging
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class BotConfig:
    """Configuration complète du bot"""
    
    # API Kraken
    api_key: str = ""
    api_secret: str = ""
    
    # Mode
    sandbox: bool = True
    symbol: str = "XXBTZEUR"
    
    # Grid
    num_levels: int = 14  # Nombre pair pour équilibre
    range_percent: float = 14.0
    capital: float = 500.0
    
    # Sécurité
    max_order_value: float = 100.0
    max_volume: float = 0.01
    max_positions: int = 10
    max_drawdown_percent: float = 20.0
    
    # Trading
    poll_interval: int = 30  # secondes entre chaque scan
    
    # Persistence
    state_file: str = "data/autobot_state.json"


def load_config() -> BotConfig:
    """
    Charge la configuration depuis les variables d'environnement.
    
    CORRECTION: Double confirmation pour mode production.
    
    Returns:
        Configuration chargée
        
    Raises:
        RuntimeError: Si configuration invalide
    """
    config = BotConfig()
    
    # Chargement depuis .env
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        logger.warning("⚠️ python-dotenv non installé, utilisation des variables système uniquement")
    
    # API Keys (ne pas logger !)
    config.api_key = os.getenv("KRAKEN_API_KEY", "")
    config.api_secret = os.getenv("KRAKEN_API_SECRET", "")
    
    # Mode sandbox/production
    sandbox_str = os.getenv("AUTOBOT_SANDBOX", "true").lower()
    config.sandbox = sandbox_str in ("true", "1", "yes")
    
    # CORRECTION: Double confirmation pour production
    if not config.sandbox:
        production_confirmed = os.getenv("AUTOBOT_PRODUCTION_CONFIRMED", "") == "YES_I_KNOW_WHAT_IM_DOING"
        if not production_confirmed:
            raise RuntimeError(
                "⛔ MODE PRODUCTION REFUSÉ !\n"
                "Pour passer en production, définissez:\n"
                "AUTOBOT_PRODUCTION_CONFIRMED=YES_I_KNOW_WHAT_IM_DOING\n"
                "ET AUTOBOT_SANDBOX=false"
            )
        logger.warning("🚨 MODE PRODUCTION ACTIVÉ - ORDRES RÉELS !")
    
    # Trading settings
    config.symbol = os.getenv("AUTOBOT_SYMBOL", config.symbol)
    config.num_levels = int(os.getenv("AUTOBOT_NUM_LEVELS", str(config.num_levels)))
    config.range_percent = float(os.getenv("AUTOBOT_RANGE_PERCENT", str(config.range_percent)))
    config.capital = float(os.getenv("AUTOBOT_CAPITAL", str(config.capital)))
    
    # Sécurité
    config.max_order_value = float(os.getenv("AUTOBOT_MAX_ORDER_VALUE", str(config.max_order_value)))
    config.max_volume = float(os.getenv("AUTOBOT_MAX_VOLUME", str(config.max_volume)))
    config.max_positions = int(os.getenv("AUTOBOT_MAX_POSITIONS", str(config.max_positions)))
    config.max_drawdown_percent = float(os.getenv("AUTOBOT_MAX_DRAWDOWN", str(config.max_drawdown_percent)))
    
    # Polling
    config.poll_interval = int(os.getenv("AUTOBOT_POLL_INTERVAL", str(config.poll_interval)))
    
    # Validation
    if not config.sandbox:
        if not config.api_key or not config.api_secret:
            raise RuntimeError("KRAKEN_API_KEY et KRAKEN_API_SECRET requis en mode production")
    
    # Force nombre pair de niveaux
    if config.num_levels % 2 != 0:
        config.num_levels += 1
        logger.warning(f"⚠️ Nombre de niveaux ajusté à {config.num_levels} (pair requis)")
    
    logger.info(f"⚙️ Configuration chargée:")
    logger.info(f"   Mode: {'SANDBOX' if config.sandbox else 'PRODUCTION'}")
    logger.info(f"   Symbole: {config.symbol}")
    logger.info(f"   Niveaux: {config.num_levels}")
    logger.info(f"   Capital: €{config.capital:.2f}")
    
    return config
