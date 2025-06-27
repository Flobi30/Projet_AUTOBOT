#!/usr/bin/env python3
"""
Test adaptive capital management system
"""
import sys
import os
sys.path.insert(0, '/home/ubuntu/repos/Projet_AUTOBOT/src')

def test_adaptive_capital_management():
    print("=== Testing Adaptive Capital Management System ===")
    
    try:
        from autobot.adaptive.capital_manager import AdaptiveCapitalManager
        
        print("✅ AdaptiveCapitalManager imported successfully")
        
        capital_amounts = [500, 1000, 2500, 5000, 10000]
        
        for capital in capital_amounts:
            print(f"\n--- Testing with {capital}€ capital ---")
            
            manager = AdaptiveCapitalManager(initial_capital=capital)
            print(f"Initial capital: {manager.current_capital}€")
            print(f"Capital range: {manager.get_capital_range(manager.current_capital)}")
            
            strategy_name, strategy_params = manager.get_best_strategy_for_capital(capital)
            print(f"Best strategy: {strategy_name}")
            print(f"Adapted parameters: {strategy_params}")
            
            for i in range(3):
                returns = 2.5 + (i * 0.5)  # Simulate improving performance
                manager.update_performance(strategy_name, capital, returns, 
                                         sharpe=1.2 + (i * 0.1), 
                                         drawdown=5.0 - (i * 0.5))
                print(f"Updated performance: {returns}% return")
            
            summary = manager.get_capital_summary()
            print(f"Capital range: {summary['capital_range']}")
            print(f"Active strategies: {summary['active_strategies']}")
            print(f"Experience count: {summary['experience_count']}")
        
        print("\n=== Testing Capital Range Adaptation ===")
        manager = AdaptiveCapitalManager(initial_capital=500.0)
        
        base_params = {"position_size": 0.1, "stop_loss": 0.02, "lookback_period": 20}
        
        for capital in [500, 2000, 8000]:
            adapted = manager.adapt_strategy_parameters(base_params, capital)
            print(f"Capital {capital}€: {adapted}")
        
        print("\n✅ Adaptive Capital Management System working correctly!")
        return True
        
    except Exception as e:
        print(f"❌ Error testing adaptive capital management: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_adaptive_capital_management()
    if success:
        print("\n🎉 All tests passed!")
    else:
        print("\n💥 Tests failed!")
