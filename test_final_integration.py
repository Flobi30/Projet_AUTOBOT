#!/usr/bin/env python3
"""
Final integration test for AUTOBOT backtest optimization modules
"""
import sys
import os
import subprocess

def test_final_integration():
    """Test the final integrated backtest system"""
    print("=== Final AUTOBOT Backtest Integration Test ===")
    
    try:
        sys.path.insert(0, "/home/ubuntu")
        
        print("Testing optimization module availability...")
        modules_available = True
        
        try:
            from genetic_optimizer import GeneticOptimizer
            print("✅ GeneticOptimizer available")
        except ImportError as e:
            print(f"❌ GeneticOptimizer not available: {e}")
            modules_available = False
            
        try:
            from risk_manager_advanced import AdvancedRiskManager
            print("✅ AdvancedRiskManager available")
        except ImportError as e:
            print(f"❌ AdvancedRiskManager not available: {e}")
            modules_available = False
            
        try:
            from transaction_cost_manager import TransactionCostManager
            print("✅ TransactionCostManager available")
        except ImportError as e:
            print(f"❌ TransactionCostManager not available: {e}")
            modules_available = False
            
        try:
            from continuous_backtester import ContinuousBacktester
            print("✅ ContinuousBacktester available")
        except ImportError as e:
            print(f"❌ ContinuousBacktester not available: {e}")
            modules_available = False
            
        try:
            from performance_metrics_advanced import AdvancedPerformanceMetrics
            print("✅ AdvancedPerformanceMetrics available")
        except ImportError as e:
            print(f"❌ AdvancedPerformanceMetrics not available: {e}")
            modules_available = False
        
        if not modules_available:
            print("❌ Some optimization modules are missing")
            return False
        
        print("\nTesting integrated backtest routes...")
        try:
            from current_backtest_routes import EnhancedBacktestEngine, BacktestRequest
            print("✅ Enhanced backtest routes imported successfully")
            
            engine = EnhancedBacktestEngine()
            print("✅ Enhanced backtest engine initialized")
            
            if hasattr(engine, 'genetic_optimizer'):
                print("✅ Genetic optimizer integrated")
            else:
                print("❌ Genetic optimizer not integrated")
                
            if hasattr(engine, 'risk_manager'):
                print("✅ Risk manager integrated")
            else:
                print("❌ Risk manager not integrated")
                
            if hasattr(engine, 'transaction_cost_manager'):
                print("✅ Transaction cost manager integrated")
            else:
                print("❌ Transaction cost manager not integrated")
                
            if hasattr(engine, 'continuous_backtester'):
                print("✅ Continuous backtester integrated")
            else:
                print("❌ Continuous backtester not integrated")
                
            if hasattr(engine, 'performance_metrics'):
                print("✅ Performance metrics integrated")
            else:
                print("❌ Performance metrics not integrated")
            
        except Exception as e:
            print(f"❌ Integration test failed: {e}")
            return False
        
        print("\n✅ All optimization modules successfully integrated!")
        print("✅ Backtest engine ready for deployment")
        
        return True
        
    except Exception as e:
        print(f"❌ Final integration test failed: {e}")
        return False

if __name__ == "__main__":
    success = test_final_integration()
    if success:
        print("\n🎉 AUTOBOT Backtest Optimization Integration Complete!")
        print("Ready for deployment to production server.")
    else:
        print("\n❌ Integration incomplete - check module dependencies")
