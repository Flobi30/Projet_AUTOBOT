#!/usr/bin/env python3
"""
Verification script for AUTOBOT backtest optimization integration
"""
import os
import sys

def verify_integration():
    """Verify that all optimization modules are properly integrated"""
    print("=== AUTOBOT Backtest Optimization Integration Verification ===")
    
    required_files = [
        "genetic_optimizer.py",
        "risk_manager_advanced.py", 
        "transaction_cost_manager.py",
        "continuous_backtester.py",
        "performance_metrics_advanced.py",
        "current_backtest_routes.py"
    ]
    
    print("Checking required files...")
    for file in required_files:
        if os.path.exists(f"/home/ubuntu/{file}"):
            size = os.path.getsize(f"/home/ubuntu/{file}")
            print(f"  ✅ {file} ({size} bytes)")
        else:
            print(f"  ❌ {file} (missing)")
            return False
    
    print("\nChecking integration points...")
    
    with open("/home/ubuntu/current_backtest_routes.py", "r") as f:
        content = f.read()
        
    integration_checks = [
        ("from genetic_optimizer import GeneticOptimizer", "Genetic optimizer import"),
        ("from risk_manager_advanced import AdvancedRiskManager", "Risk manager import"),
        ("from transaction_cost_manager import TransactionCostManager", "Transaction cost manager import"),
        ("from continuous_backtester import ContinuousBacktester", "Continuous backtester import"),
        ("from performance_metrics_advanced import AdvancedPerformanceMetrics", "Performance metrics import"),
        ("self.genetic_optimizer = GeneticOptimizer", "Genetic optimizer initialization"),
        ("self.risk_manager = AdvancedRiskManager", "Risk manager initialization"),
        ("self.transaction_cost_manager = TransactionCostManager", "Transaction cost manager initialization"),
        ("self.continuous_backtester = ContinuousBacktester", "Continuous backtester initialization"),
        ("self.performance_metrics = AdvancedPerformanceMetrics", "Performance metrics initialization")
    ]
    
    for check, description in integration_checks:
        if check in content:
            print(f"  ✅ {description}")
        else:
            print(f"  ❌ {description}")
            return False
    
    print("\n✅ All integration points verified successfully!")
    print("✅ AUTOBOT backtest optimization integration complete!")
    
    return True

if __name__ == "__main__":
    success = verify_integration()
    if success:
        print("\n🎉 Integration verification passed!")
        print("Ready for deployment to production server.")
    else:
        print("\n❌ Integration verification failed!")
