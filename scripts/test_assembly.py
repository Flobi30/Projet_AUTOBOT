#!/usr/bin/env python3
"""Test rapide de l'assemblage (sans appeler Kraken)."""

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
SRC_DIR = os.path.join(SCRIPT_DIR, "..", "src")
sys.path.insert(0, SRC_DIR)


def test_imports():
    """Verifie que tous les imports fonctionnent."""
    try:
        from kraken_connect import main as kraken_main
        from get_price import get_current_price
        from grid_calculator import GridConfig, calculate_grid_levels, display_grid
        from order_manager import place_buy_order, check_eur_balance, create_kraken_client
        from position_manager import monitor_and_manage, build_grid
        from persistence import save_state, load_state
        from autobot.error_handler import ErrorHandler, get_error_handler, with_retry
        print("Tous les imports fonctionnent")
        return True
    except Exception as e:
        print(f"Erreur d'import: {e}")
        return False


def test_grid_calculation():
    """Test le calcul de grid."""
    try:
        from grid_calculator import GridConfig, calculate_grid_levels

        config = GridConfig(
            symbol="BTC/EUR",
            kraken_symbol="XXBTZEUR",
            capital_total=500.0,
            num_levels=15,
            range_percent=14.0,
        )
        levels = calculate_grid_levels(55000.0, config)
        assert len(levels) == 15, f"Attendu 15 niveaux, obtenu {len(levels)}"
        assert levels[0].level_type == "BUY", f"Level 0 devrait etre BUY, got {levels[0].level_type}"
        assert levels[7].level_type == "CENTER", f"Level 7 devrait etre CENTER, got {levels[7].level_type}"
        assert levels[14].level_type == "SELL", f"Level 14 devrait etre SELL, got {levels[14].level_type}"
        print("Calcul de grid OK")
        return True
    except Exception as e:
        print(f"Erreur grid: {e}")
        return False


def test_persistence():
    """Test la persistance JSON."""
    try:
        from persistence import save_state, load_state

        test_orders = [{"id": "test-1", "price": 50000.0}]
        test_positions = [{"id": "pos-1", "profit": 10.0}]
        test_metrics = {"total_profit": 10.0}

        save_state(test_orders, test_positions, test_metrics)
        state = load_state()

        assert state["orders"] == test_orders
        assert state["positions"] == test_positions
        assert state["metrics"] == test_metrics

        os.remove("bot_state.json")
        print("Persistance OK")
        return True
    except Exception as e:
        print(f"Erreur persistance: {e}")
        return False


def test_error_handler():
    """Test l'error handler."""
    try:
        from autobot.error_handler import ErrorHandler, get_error_handler

        handler = get_error_handler()
        assert handler is not None
        assert not handler.is_emergency_stopped
        print("Error handler OK")
        return True
    except Exception as e:
        print(f"Erreur error_handler: {e}")
        return False


def test_main_dry_run():
    """Test l'instanciation du bot (sans connexion Kraken)."""
    try:
        from main import GridTradingBot

        bot = GridTradingBot()
        assert bot.config.symbol == "BTC/EUR"
        assert bot.config.capital_total == 500.0
        assert bot.config.num_levels == 15
        assert bot.state is not None
        print("Main dry-run OK")
        return True
    except Exception as e:
        print(f"Erreur main: {e}")
        return False


if __name__ == "__main__":
    print("Test d'assemblage AUTOBOT")
    print("=" * 40)

    success = True
    success &= test_imports()
    success &= test_grid_calculation()
    success &= test_persistence()
    success &= test_error_handler()
    success &= test_main_dry_run()

    print("=" * 40)
    if success:
        print("Tous les tests passent")
        sys.exit(0)
    else:
        print("Des erreurs ont ete detectees")
        sys.exit(1)
