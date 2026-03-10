"""
Tests d'intégration pour AUTOBOT Grid Trading - Kraken Edition

Ces tests vérifient que le bot Grid Trading fonctionne avec Kraken.
Mode simulation par défaut (sandbox=True).
"""

import os
import sys
import pytest
import logging

# Ajoute src au path
sys.path.insert(0, '/home/node/.openclaw/workspace/src')

from autobot.grid_calculator import GridCalculator, GridConfig
from autobot.order_manager import OrderManager, OrderSide, Order
from autobot.position_manager import PositionManager, PositionStatus
from autobot.error_handler import ErrorHandler, CircuitBreakerOpenError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def grid_calc():
    """Fixture pour le calculateur de grille"""
    config = GridConfig(
        num_levels=15,
        range_percent=14.0,  # +/- 7%
        capital=500.0,
        symbol="XXBTZEUR"
    )
    return GridCalculator(config)


@pytest.fixture
def order_manager():
    """Fixture pour le gestionnaire d'ordres (mode sandbox)"""
    return OrderManager(api_key=None, api_secret=None, sandbox=True)


@pytest.fixture
def position_manager(grid_calc, order_manager):
    """Fixture pour le gestionnaire de positions"""
    return PositionManager(order_manager, grid_calc)


@pytest.fixture
def error_handler():
    """Fixture pour le gestionnaire d'erreurs"""
    return ErrorHandler(max_retries=3, retry_delay=0.1)


# ============================================================================
# TESTS: GridCalculator
# ============================================================================

class TestGridCalculator:
    """Tests du calculateur de grille"""
    
    def test_calculate_15_levels(self, grid_calc):
        """Vérifie le calcul des 15 niveaux de grid"""
        center_price = 75000.0
        levels = grid_calc.calculate_grid(center_price)
        
        assert len(levels) == 15, f"Devrait avoir 15 niveaux, a {len(levels)}"
    
    def test_levels_around_center_price(self, grid_calc):
        """Vérifie que les niveaux entourent le prix central"""
        center_price = 75000.0
        levels = grid_calc.calculate_grid(center_price)
        
        assert levels[0] < center_price, "Premier niveau devrait être < prix centre"
        assert levels[-1] > center_price, "Dernier niveau devrait être > prix centre"
        assert abs(levels[7] - center_price) / center_price < 0.01, "Milieu proche du prix centre"
    
    def test_range_plus_minus_7_percent(self, grid_calc):
        """Vérifie la range de +/- 7%"""
        center_price = 75000.0
        levels = grid_calc.calculate_grid(center_price)
        
        expected_lower = center_price * 0.93
        expected_upper = center_price * 1.07
        
        assert abs(levels[0] - expected_lower) / expected_lower < 0.001
        assert abs(levels[-1] - expected_upper) / expected_upper < 0.001
    
    def test_buy_levels_below_center(self, grid_calc):
        """Vérifie les niveaux d'achat sous le prix central"""
        center_price = 75000.0
        grid_calc.calculate_grid(center_price)
        
        buy_levels = grid_calc.get_buy_levels()
        
        assert len(buy_levels) == 7
        for level in buy_levels:
            assert level < center_price
    
    def test_sell_levels_above_center(self, grid_calc):
        """Vérifie les niveaux de vente au-dessus du prix central"""
        center_price = 75000.0
        grid_calc.calculate_grid(center_price)
        
        sell_levels = grid_calc.get_sell_levels()
        
        assert len(sell_levels) == 7
        for level in sell_levels:
            assert level > center_price
    
    def test_grid_info_structure(self, grid_calc):
        """Vérifie la structure des infos de grille"""
        center_price = 75000.0
        grid_calc.calculate_grid(center_price)
        
        info = grid_calc.get_grid_info()
        
        assert info['num_levels'] == 15
        assert info['symbol'] == 'XXBTZEUR'
        assert info['capital_total'] == 500.0
        assert info['capital_per_level'] == 500.0 / 15


# ============================================================================
# TESTS: ErrorHandler
# ============================================================================

class TestErrorHandler:
    """Tests de la gestion d'erreurs"""
    
    def test_retry_succeeds_eventually(self, error_handler):
        """Vérifie que le retry finit par réussir"""
        attempt_count = 0
        
        def failing_then_success():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise Exception("Test error")
            return "success"
        
        result = error_handler.execute_with_retry(failing_then_success)
        
        assert result == "success"
        assert attempt_count == 3
    
    def test_circuit_opens_after_threshold(self):
        """Vérifie que le circuit s'ouvre après le seuil"""
        handler = ErrorHandler(
            max_retries=1,
            retry_delay=0.1,
            circuit_failure_threshold=2,
            circuit_recovery_timeout=0.5
        )
        
        def always_fail():
            raise Exception("Always fails")
        
        # Deux échecs
        for _ in range(2):
            try:
                handler.execute_with_retry(always_fail)
            except:
                pass
        
        assert handler.circuit_state.name == "OPEN"
    
    def test_circuit_blocks_calls_when_open(self):
        """Vérifie que le circuit bloque les appels quand ouvert"""
        handler = ErrorHandler(
            max_retries=1,
            retry_delay=0.1,
            circuit_failure_threshold=1,
            circuit_recovery_timeout=60.0
        )
        
        def always_fail():
            raise Exception("Always fails")
        
        try:
            handler.execute_with_retry(always_fail)
        except:
            pass
        
        with pytest.raises(CircuitBreakerOpenError):
            handler.execute_with_retry(always_fail)


# ============================================================================
# TESTS: OrderManager
# ============================================================================

class TestOrderManager:
    """Tests du gestionnaire d'ordres"""
    
    def test_place_buy_order(self, order_manager):
        """Test le placement d'un ordre d'achat"""
        result = order_manager.place_buy_order(
            symbol="XXBTZEUR",
            price=70000.0,
            volume=0.001
        )
        
        assert isinstance(result, Order)
        assert result.id != ""
        assert result.side == OrderSide.BUY
        assert result.price == 70000.0
    
    def test_place_sell_order(self, order_manager):
        """Test le placement d'un ordre de vente"""
        result = order_manager.place_sell_order(
            symbol="XXBTZEUR",
            price=80000.0,
            volume=0.001
        )
        
        assert isinstance(result, Order)
        assert result.id != ""
        assert result.side == OrderSide.SELL
    
    def test_cancel_order(self, order_manager):
        """Test l'annulation d'un ordre"""
        order = order_manager.place_buy_order(
            symbol="XXBTZEUR",
            price=70000.0,
            volume=0.001
        )
        
        result = order_manager.cancel_order(order.id)
        assert result == True
    
    def test_get_active_orders(self, order_manager):
        """Test la récupération des ordres actifs"""
        # Crée quelques ordres
        order_manager.place_buy_order("XXBTZEUR", 70000.0, 0.001)
        order_manager.place_sell_order("XXBTZEUR", 80000.0, 0.001)
        
        active = order_manager.get_active_orders()
        
        assert isinstance(active, list)
        assert len(active) >= 2


# ============================================================================
# TESTS: PositionManager
# ============================================================================

class TestPositionManager:
    """Tests du gestionnaire de positions"""
    
    def test_open_position(self, position_manager, order_manager):
        """Test l'ouverture d'une position"""
        buy_order = order_manager.place_buy_order("XXBTZEUR", 70000.0, 0.001)
        
        position = position_manager.open_position(buy_order)
        
        assert position.buy_order_id == buy_order.id
        assert position.status == PositionStatus.OPEN
        assert position.buy_price == 70000.0
    
    def test_get_open_positions(self, position_manager, order_manager):
        """Test la récupération des positions ouvertes"""
        buy_order = order_manager.place_buy_order("XXBTZEUR", 70000.0, 0.001)
        position_manager.open_position(buy_order)
        
        open_pos = position_manager.get_open_positions()
        
        assert len(open_pos) == 1
    
    def test_calculate_profit(self, position_manager, order_manager):
        """Test le calcul du profit"""
        buy_order = order_manager.place_buy_order("XXBTZEUR", 70000.0, 0.001)
        position = position_manager.open_position(buy_order)
        
        # Simule une position fermée
        position.sell_price = 71000.0
        
        profit = position.calculate_profit()
        
        # Profit brut = (71000 - 70000) * 0.001 = 10€
        # Moins frais ~0.2%
        assert profit > 0
        assert profit < 15  # Moins que le profit brut à cause des frais
    
    def test_sell_price_calculation(self, grid_calc):
        """Test le calcul du prix de vente"""
        grid_calc.calculate_grid(75000.0)
        
        # Crée un manager avec cette grille
        om = OrderManager(api_key=None, api_secret=None, sandbox=True)
        pm = PositionManager(om, grid_calc)
        
        buy_price = 70000.0
        sell_price = pm._calculate_sell_price(buy_price)
        
        assert sell_price > buy_price


# ============================================================================
# TESTS: Intégration
# ============================================================================

class TestIntegration:
    """Tests d'intégration complets"""
    
    def test_full_grid_workflow(self):
        """Test le workflow complet de la grille"""
        # 1. Configuration
        config = GridConfig(num_levels=15, range_percent=14.0, capital=500.0)
        calc = GridCalculator(config)
        
        # 2. Calcul de la grille
        center_price = 75000.0
        levels = calc.calculate_grid(center_price)
        buy_levels = calc.get_buy_levels()
        sell_levels = calc.get_sell_levels()
        
        assert len(levels) == 15
        assert len(buy_levels) == 7
        assert len(sell_levels) == 7
        
        # 3. Gestionnaire d'ordres
        om = OrderManager(api_key=None, api_secret=None, sandbox=True)
        
        # 4. Placement d'ordres sur plusieurs niveaux
        for level in buy_levels[:3]:
            om.place_buy_order("XXBTZEUR", round(level, 2), 0.001)
        
        for level in sell_levels[:3]:
            om.place_sell_order("XXBTZEUR", round(level, 2), 0.001)
        
        active = om.get_active_orders()
        assert len(active) == 6
        
        # 5. Gestionnaire de positions
        pm = PositionManager(om, calc)
        
        # 6. Ouverture d'une position
        buy_order = om.place_buy_order("XXBTZEUR", buy_levels[0], 0.001)
        position = pm.open_position(buy_order)
        
        assert position.status == PositionStatus.OPEN
        
        # 7. Nettoyage
        om.cancel_all_orders()
    
    def test_symbol_xxbtzeur(self):
        """Vérifie que le symbole XXBTZEUR est utilisé"""
        config = GridConfig(symbol="XXBTZEUR")
        calc = GridCalculator(config)
        
        info = calc.get_grid_info()
        
        assert info['symbol'] == "XXBTZEUR"


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
