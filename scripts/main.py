#!/usr/bin/env python3
"""
AUTOBOT - Bot de Trading Grid
Orchestrateur principal qui enchaine tous les modules.
"""

import os
import sys
import time
import json
import logging
from datetime import datetime
from typing import List, Dict, Optional

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
SRC_DIR = os.path.join(SCRIPT_DIR, "..", "src")
sys.path.insert(0, SRC_DIR)

from kraken_connect import main as kraken_connect_test  # noqa: E402
from get_price import get_current_price  # noqa: E402
from grid_calculator import GridConfig, calculate_grid_levels, display_grid  # noqa: E402
from order_manager import (  # noqa: E402
    create_kraken_client,
    place_buy_order,
    check_eur_balance,
)
from position_manager import monitor_and_manage, build_grid  # noqa: E402
from persistence import save_state, load_state  # noqa: E402
from autobot.error_handler import ErrorHandler, get_error_handler  # noqa: E402

GRID_CAPITAL = 500.0
GRID_LEVELS = 15
GRID_RANGE = 14.0
POLL_INTERVAL = 10
STATE_FILE = "bot_state.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


class GridTradingBot:
    """Bot de trading grid principal."""

    def __init__(self):
        self.exchange = None
        self.config = GridConfig(
            symbol="BTC/EUR",
            kraken_symbol="XXBTZEUR",
            capital_total=GRID_CAPITAL,
            num_levels=GRID_LEVELS,
            range_percent=GRID_RANGE,
        )
        self.state = self._load_state()
        self.error_handler = get_error_handler()

    def _load_state(self) -> Dict:
        """Charge l'etat depuis le fichier JSON."""
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        return {"orders": [], "positions": [], "initialized": False}

    def _save_state(self):
        """Sauvegarde l'etat dans le fichier JSON."""
        with open(STATE_FILE, "w") as f:
            json.dump(self.state, f, indent=2)

    def connect(self):
        """Connexion a Kraken."""
        self.exchange = create_kraken_client()
        logger.info("Connecte a Kraken")

    def initialize_grid(self):
        """Initialise le grid au demarrage."""
        if self.state.get("initialized"):
            logger.info("Grid deja initialise, reprise...")
            return

        price_data = get_current_price(self.config.kraken_symbol)
        current_price = price_data["price"]
        logger.info(f"Prix BTC/EUR: {current_price:.2f}")

        levels = calculate_grid_levels(current_price, self.config)
        display_grid(levels, current_price, self.config)

        buy_levels = [lv for lv in levels if lv.level_type == "BUY"]
        logger.info(f"Placement de {len(buy_levels)} ordres d'achat...")

        for level in buy_levels:
            try:
                order = place_buy_order(
                    exchange=self.exchange,
                    price=level.price,
                    volume_btc=level.btc_quantity,
                    level_id=level.level,
                )
                self.state["orders"].append(order.to_dict())
                logger.info(
                    f"Ordre BUY Level {level.level} place: "
                    f"{order.exchange_order_id}"
                )
            except Exception as e:
                logger.error(f"Erreur placement Level {level.level}: {e}")

        self.state["initialized"] = True
        self._save_state()
        logger.info("Grid initialise")

    def run(self):
        """Boucle principale du bot."""
        logger.info("Demarrage AUTOBOT Grid Trading")

        try:
            self.connect()
            self.initialize_grid()

            logger.info(f"Boucle principale (intervalle: {POLL_INTERVAL}s)")

            while True:
                try:
                    if self.error_handler.is_emergency_stopped:
                        logger.warning("Circuit breaker ouvert, pause...")
                        time.sleep(60)
                        continue

                    price_data = get_current_price(self.config.kraken_symbol)
                    current_price = price_data["price"]
                    levels = build_grid(current_price)

                    tracked_orders = {}
                    for o in self.state["orders"]:
                        if o.get("status") == "open" and o.get("side") == "buy":
                            tracked_orders[o["exchange_order_id"]] = o["level_id"]

                    if tracked_orders:
                        positions = monitor_and_manage(
                            exchange=self.exchange,
                            tracked_orders=tracked_orders,
                            levels=levels,
                            poll_interval=POLL_INTERVAL,
                            max_cycles=1,
                        )

                        if positions:
                            for pos in positions:
                                self.state["positions"].append(pos.to_dict())
                            self._save_state()

                    time.sleep(POLL_INTERVAL)

                except Exception as e:
                    logger.error(f"Erreur dans la boucle: {e}")
                    time.sleep(POLL_INTERVAL)

        except KeyboardInterrupt:
            logger.info("Arret demande par l'utilisateur")
            self._save_state()
        except Exception as e:
            logger.error(f"Erreur fatale: {e}")
            self._save_state()
            raise


def main():
    import argparse

    parser = argparse.ArgumentParser(description="AUTOBOT Grid Trading Bot")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Verifie les imports et la configuration sans trader",
    )
    args = parser.parse_args()

    if args.dry_run:
        logger.info("Mode dry-run: verification des imports et configuration")
        bot = GridTradingBot()
        logger.info(f"Config: {bot.config}")
        logger.info(f"State: {bot.state}")
        logger.info("Tous les imports sont OK")
        return

    bot = GridTradingBot()
    bot.run()


if __name__ == "__main__":
    main()
