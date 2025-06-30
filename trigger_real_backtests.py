#!/usr/bin/env python3
"""
Trigger real backtests to start accumulating performance data.
"""
import requests
import time
import json

def trigger_real_backtests():
    """Trigger real backtests and verify data accumulation."""
    print("=== Triggering Real Backtests for Data Accumulation ===")
    
    base_url = "http://localhost:8000"
    
    print("🚀 Triggering backtest status API to run real backtests...")
    
    for i in range(3):  # Run 3 times to accumulate data
        print(f"\n--- Backtest Run {i+1}/3 ---")
        
        try:
            response = requests.get(f"{base_url}/api/backtest/status", timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Backtest API Response:")
                print(f"   Status: {data.get('status')}")
                print(f"   Strategy: {data.get('current_strategy')}")
                print(f"   Total Return: {data.get('total_return')}%")
                print(f"   Daily Return: {data.get('daily_return')}%")
                print(f"   Strategies Tested: {data.get('strategies_tested')}")
                print(f"   Data Source: {data.get('data_source')}")
                
                if 'backtest_details' in data:
                    details = data['backtest_details']
                    print(f"   Total Backtests Run: {details.get('total_backtests_run')}")
                    print(f"   Cumulative Capital: {details.get('cumulative_capital', 'N/A')}€")
                    print(f"   Real Data: {details.get('real_data')}")
            else:
                print(f"❌ Backtest API failed: {response.status_code}")
                print(f"   Response: {response.text}")
        
        except Exception as e:
            print(f"❌ Error calling backtest API: {e}")
        
        if i < 2:
            print("⏳ Waiting 5 seconds before next run...")
            time.sleep(5)
    
    print("\n🔍 Checking Capital API for accumulated data...")
    
    try:
        response = requests.get(f"{base_url}/api/metrics/capital", timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'success':
                capital_data = data['data']
                print(f"✅ Capital API Response:")
                print(f"   Current Capital: {capital_data.get('current_capital')}€")
                print(f"   Initial Capital: {capital_data.get('initial_capital')}€")
                print(f"   Total Profit: {capital_data.get('total_profit')}€")
                print(f"   ROI: {capital_data.get('roi')}%")
                print(f"   Data Source: {capital_data.get('data_source')}")
                
                if 'performance_summary' in capital_data:
                    summary = capital_data['performance_summary']
                    print(f"   Total Backtests: {summary.get('total_backtests')}")
                    print(f"   Cumulative Return: {summary.get('cumulative_return')}%")
            else:
                print(f"❌ Capital API error: {data}")
        else:
            print(f"❌ Capital API failed: {response.status_code}")
    
    except Exception as e:
        print(f"❌ Error calling capital API: {e}")
    
    print("\n=== Real Backtest Triggering Complete ===")
    print("🎯 Check the browser pages to see if data is accumulating!")

if __name__ == "__main__":
    trigger_real_backtests()
