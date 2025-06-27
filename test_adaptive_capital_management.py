#!/usr/bin/env python3
"""
Test adaptive capital management system
"""
import sys
import os
sys.path.insert(0, '/home/ubuntu/repos/Projet_AUTOBOT/src')

from autobot.adaptive.capital_manager import AdaptiveCapitalManager
import time

def test_adaptive_capital_management():
    print("=== Testing Adaptive Capital Management System ===")
    
    capital_amounts = [500, 1000, 2500, 5000, 10000]
    
    for capital in capital_amounts:
        print(f"\n--- Testing with {capital}€ capital ---")
        
        manager = AdaptiveCapitalManager(initial_capital=capital)
        
        strategy_name, strategy_params = manager.get_best_strategy_for_capital(capital)
        print(f"Best strategy: {strategy_name}")
        print(f"Adapted parameters: {strategy_params}")
        
        for i in range(3):
            returns = 2.5 + (i * 0.5)
            manager.update_performance(strategy_name, capital, returns, 
                                     sharpe=1.2 + (i * 0.1), 
                                     drawdown=5.0 - (i * 0.5))
            print(f"Updated performance: {returns}% return")
        
        summary = manager.get_capital_summary()
        print(f"Capital range: {summary['capital_range']}")
        print(f"Active strategies: {summary['active_strategies']}")
        print(f"Experience count: {summary['experience_count']}")
    
    print("\n=== Adaptive Capital Management Test Complete ===")

if __name__ == "__main__":
    test_adaptive_capital_management()
