#!/usr/bin/env python
"""
Script pour lancer la séquence de backtests RL et trading.
"""
import sys
import time
from datetime import datetime
import os
import json

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from src.autobot.rl.train import start_training
from src.autobot.backtest.core import run_backtest

def main():
    config_dir = 'config'
    config_file = os.path.join(config_dir, 'api_keys.json')
    
    if not os.path.exists(config_file):
        print("❌ Les clés API ne sont pas configurées. Veuillez exécuter 'python installer.py --config-only' d'abord.")
        return
    
    from installer import run_backtests
    results = run_backtests()
    
    results_dir = 'results'
    os.makedirs(results_dir, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    results_file = os.path.join(results_dir, f'backtest_results_{timestamp}.json')
    
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n✅ Résultats sauvegardés dans {results_file}")
    print("\n🚀 Prêt pour le passage en réel optimal.")

if __name__ == "__main__":
    main()
