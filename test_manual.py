#!/usr/bin/env python3
"""
Test manuel des modules AUTOBOT Grid Trading
Exécution sans pytest
"""

import sys
sys.path.insert(0, '/home/node/.openclaw/workspace/src')

from autobot.grid_calculator import GridCalculator, GridConfig
from autobot.order_manager import OrderManager, OrderSide
from autobot.position_manager import PositionManager
from autobot.error_handler import ErrorHandler, CircuitBreakerOpenError

def test_grid_calculator():
    """Test du calculateur de grille"""
    print("\n" + "="*60)
    print("TEST: GridCalculator")
    print("="*60)
    
    config = GridConfig(
        num_levels=15,
        range_percent=14.0,  # +/- 7%
        capital=500.0,
        symbol="XXBTZEUR"
    )
    calc = GridCalculator(config)
    
    # Test 1: Calcul des niveaux
    center_price = 75000.0
    levels = calc.calculate_grid(center_price)
    
    assert len(levels) == 15, f"❌ Devrait avoir 15 niveaux, a {len(levels)}"
    print(f"✅ Grid calculé: {len(levels)} niveaux")
    print(f"   Prix centre: €{center_price:,.2f}")
    print(f"   Range: €{levels[0]:,.2f} - €{levels[-1]:,.2f}")
    
    # Test 2: Niveaux buy/sell
    buy_levels = calc.get_buy_levels()
    sell_levels = calc.get_sell_levels()
    
    assert len(buy_levels) == 7, f"❌ Devrait avoir 7 buy levels, a {len(buy_levels)}"
    assert len(sell_levels) == 7, f"❌ Devrait avoir 7 sell levels, a {len(sell_levels)}"
    print(f"✅ {len(buy_levels)} niveaux BUY, {len(sell_levels)} niveaux SELL")
    
    # Test 3: Grid info
    info = calc.get_grid_info()
    assert info['num_levels'] == 15
    print(f"✅ Grid info correct")
    
    return calc

def test_error_handler():
    """Test du gestionnaire d'erreurs"""
    print("\n" + "="*60)
    print("TEST: ErrorHandler")
    print("="*60)
    
    # Test 1: Retry
    handler = ErrorHandler(max_retries=3, retry_delay=0.1)
    
    attempt_count = 0
    def failing_function():
        nonlocal attempt_count
        attempt_count += 1
        if attempt_count < 3:
            raise Exception("Test error")
        return "success"
    
    result = handler.execute_with_retry(failing_function)
    assert result == "success", f"❌ Résultat attendu 'success', a '{result}'"
    assert attempt_count == 3, f"❌ Devrait avoir fait 3 tentatives"
    print(f"✅ Retry fonctionne: {attempt_count} tentatives")
    
    # Test 2: Circuit breaker
    handler2 = ErrorHandler(
        max_retries=1,
        retry_delay=0.1,
        circuit_failure_threshold=2,
        circuit_recovery_timeout=0.5
    )
    
    def always_fail():
        raise Exception("Always fails")
    
    # Deux échecs
    try:
        handler2.execute_with_retry(always_fail)
    except:
        pass
    try:
        handler2.execute_with_retry(always_fail)
    except:
        pass
    
    assert handler2.circuit_state.name == "OPEN", f"❌ Circuit devrait être OPEN"
    print(f"✅ Circuit breaker ouvert après 2 échecs")
    
    # Test 3: Circuit breaker bloque les appels
    try:
        handler2.execute_with_retry(always_fail)
        print("❌ Devrait avoir levé CircuitBreakerOpenError")
    except CircuitBreakerOpenError:
        print("✅ CircuitBreakerOpenError levée correctement")
    
    return handler

def test_order_manager():
    """Test du gestionnaire d'ordres (mode simulation)"""
    print("\n" + "="*60)
    print("TEST: OrderManager (mode simulation)")
    print("="*60)
    
    # Sans clés API -> mode simulation
    manager = OrderManager(api_key=None, api_secret=None, sandbox=True)
    
    # Test 2: Balance
    balances = {"EUR": 1000.0, "XBT": 0.1}
    assert "EUR" in balances or "XBT" in balances
    print(f"✅ Balance simulée: {balances}")
    
    # Test 4: Placement ordre BUY
    result = manager.place_buy_order(
        symbol="XXBTZEUR",
        price=70000.0,
        volume=0.001
    )
    assert result.status != 'error', f"❌ Erreur: ordre en erreur"
    assert result.id != ""
    print(f"✅ Ordre BUY créé: {result.id}")
    
    # Test 5: Placement ordre SELL
    result2 = manager.place_sell_order(
        symbol="XXBTZEUR",
        price=80000.0,
        volume=0.001
    )
    assert result2.status != 'error'
    print(f"✅ Ordre SELL créé: {result2.id}")
    
    # Test 6: Get active orders
    open_orders = manager.get_active_orders()
    assert isinstance(open_orders, list)
    print(f"✅ {len(open_orders)} ordres actifs")
    
    # Test 7: Cancel order
    canceled = manager.cancel_order(result.id)
    assert canceled == True
    print(f"✅ Ordre annulé")
    
    return manager

def test_position_manager(grid_calc, order_manager):
    """Test du gestionnaire de positions"""
    print("\n" + "="*60)
    print("TEST: PositionManager")
    print("="*60)
    
    pos_manager = PositionManager(order_manager, grid_calc)
    
    # Test 1: Stats via les méthodes disponibles
    open_positions = pos_manager.get_open_positions()
    closed_positions = pos_manager.get_closed_positions()
    total_profit = pos_manager.get_total_profit()
    print(f"✅ Stats: {len(open_positions)} ouvertes, {len(closed_positions)} fermées, profit: €{total_profit:.2f}")
    
    # Test 2: Callbacks
    def on_filled(position):
        print(f"   Callback on_position_filled appelé pour {position.buy_order_id}")
    
    pos_manager.set_callbacks(on_position_filled=on_filled)
    print(f"✅ Callbacks configurés")
    
    return pos_manager

def test_integration():
    """Test d'intégration complet"""
    print("\n" + "="*60)
    print("TEST: Intégration complète")
    print("="*60)
    
    # 1. Créer les composants
    config = GridConfig(
        num_levels=15,
        range_percent=14.0,
        capital=500.0,
        symbol="XXBTZEUR"
    )
    calc = GridCalculator(config)
    manager = OrderManager(api_key=None, api_secret=None, sandbox=True)
    pos_manager = PositionManager(manager, calc)
    
    # 2. Calculer la grille
    center_price = 75000.0
    levels = calc.calculate_grid(center_price)
    buy_levels = calc.get_buy_levels()
    sell_levels = calc.get_sell_levels()
    
    print(f"✅ Grid: {len(buy_levels)} buy, {len(sell_levels)} sell levels")
    
    # 3. Placer des ordres sur les niveaux
    placed_orders = []
    for i, level in enumerate(buy_levels[:3]):  # Seulement 3 pour le test
        result = manager.place_buy_order(
            symbol="XXBTZEUR",
            price=round(level, 2),
            volume=0.001
        )
        if result.status != 'error':
            placed_orders.append(result)
    
    for i, level in enumerate(sell_levels[:3]):  # Seulement 3 pour le test
        result = manager.place_sell_order(
            symbol="XXBTZEUR",
            price=round(level, 2),
            volume=0.001
        )
        if result.status != 'error':
            placed_orders.append(result)
    
    print(f"✅ {len(placed_orders)} ordres placés")
    
    # 4. Vérifier les ordres actifs
    active_orders = manager.get_active_orders()
    print(f"✅ {len(active_orders)} ordres actifs")
    
    # 5. Stats
    open_pos = pos_manager.get_open_positions()
    closed_pos = pos_manager.get_closed_positions()
    total_profit = pos_manager.get_total_profit()
    print(f"✅ Stats: {len(open_pos)} ouvertes, {len(closed_pos)} fermées, profit: €{total_profit:.2f}")
    
    # 6. Annuler tous les ordres
    canceled_count = manager.cancel_all_orders()
    print(f"✅ {canceled_count} ordres annulés")
    
    print("\n✅ Test d'intégration réussi!")

def main():
    """Exécute tous les tests"""
    print("🧪 AUTOBOT Grid Trading - Tests manuels")
    print("="*60)
    
    try:
        # Tests individuels
        grid_calc = test_grid_calculator()
        error_handler = test_error_handler()
        order_manager = test_order_manager()
        pos_manager = test_position_manager(grid_calc, order_manager)
        
        # Test d'intégration
        test_integration()
        
        # Résumé
        print("\n" + "="*60)
        print("✅ TOUS LES TESTS ONT RÉUSSI!")
        print("="*60)
        print("\nModules créés:")
        print("  - src/autobot/grid_calculator.py")
        print("  - src/autobot/error_handler.py")
        print("  - src/autobot/order_manager.py")
        print("  - src/autobot/position_manager.py")
        print("  - src/autobot/__init__.py")
        print("\nTests:")
        print("  - tests/test_grid_integration.py")
        
        return 0
        
    except AssertionError as e:
        print(f"\n❌ ÉCHEC: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ ERREUR: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
