#!/usr/bin/env python
"""
Simple backtest script that works without PyTorch dependencies.
"""
import sys
import os
import json
from datetime import datetime, timedelta

project_root = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'src'))

def main():
    """Run backtests using the real backtest service"""
    try:
        from src.autobot.services.backtest_service import get_backtest_service
        
        print("🚀 Starting AUTOBOT Backtest Analysis...")
        
        backtest_service = get_backtest_service()
        
        test_configs = [
            {
                "strategy": "moving_average_crossover",
                "symbol": "BTC/USD",
                "params": {"fast_period": 10, "slow_period": 50}
            },
            {
                "strategy": "rsi_strategy", 
                "symbol": "ETH/USD",
                "params": {"rsi_period": 14, "overbought": 70, "oversold": 30}
            },
            {
                "strategy": "bollinger_bands",
                "symbol": "SOL/USD", 
                "params": {"bb_period": 20, "bb_std": 2.0}
            }
        ]
        
        results = []
        
        for config in test_configs:
            print(f"\n📊 Testing {config['strategy']} on {config['symbol']}...")
            
            result = backtest_service.run_backtest(
                strategy_id=config["strategy"],
                symbol=config["symbol"],
                start_date="2023-01-01",
                end_date="2023-12-31", 
                initial_capital=10000,
                params=config["params"]
            )
            
            metrics = result["metrics"]
            print(f"   ✅ Total Return: {metrics['total_return']:.2f}%")
            print(f"   ✅ Sharpe Ratio: {metrics['sharpe']:.2f}")
            print(f"   ✅ Max Drawdown: {metrics['max_drawdown']:.2f}%")
            print(f"   ✅ Win Rate: {metrics['win_rate']:.1f}%")
            print(f"   ✅ Total Trades: {metrics['total_trades']}")
            
            results.append({
                "config": config,
                "metrics": metrics
            })
        
        results_dir = 'results'
        os.makedirs(results_dir, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        results_file = os.path.join(results_dir, f'backtest_results_{timestamp}.json')
        
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"\n✅ Results saved to {results_file}")
        print("\n🎯 AUTOBOT Backtest Analysis Complete!")
        
        return results
        
    except Exception as e:
        print(f"❌ Error running backtests: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    main()
