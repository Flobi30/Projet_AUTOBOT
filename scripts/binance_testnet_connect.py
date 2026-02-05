#!/usr/bin/env python3
"""
AUTOBOT Phase 1 - Tâche 1/7: Connexion API Binance Testnet
Script minimal pour vérifier la connexion à Binance Testnet.
"""

import os
import sys
from datetime import datetime

try:
    import ccxt
except ImportError:
    print("[ERROR] ccxt non installé. Exécutez: pip install ccxt")
    sys.exit(1)

def main():
    api_key = os.getenv("BINANCE_TESTNET_API_KEY", "")
    api_secret = os.getenv("BINANCE_TESTNET_API_SECRET", "")

    if not api_key or not api_secret:
        print("[ERROR] Variables BINANCE_TESTNET_API_KEY et BINANCE_TESTNET_API_SECRET requises")
        print("Créez vos clés sur: https://testnet.binance.vision/")
        sys.exit(1)

    try:
        exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': api_secret,
            'sandbox': True,
            'enableRateLimit': True,
        })
        exchange.set_sandbox_mode(True)

        print(f"[{datetime.now().isoformat()}] Connexion à Binance Testnet...")
        balance = exchange.fetch_balance()

        usdt = balance['total'].get('USDT', 0)
        btc = balance['total'].get('BTC', 0)

        print(f"[CONNECT] Binance Testnet OK")
        print(f"[BALANCE] USDT: {usdt:.2f}, BTC: {btc:.8f}")
        print(f"[STATUS] Connexion opérationnelle")

    except ccxt.AuthenticationError as e:
        print(f"[ERROR] Authentification échouée: {e}")
        print("Vérifiez vos clés API Testnet sur https://testnet.binance.vision/")
        sys.exit(1)
    except ccxt.NetworkError as e:
        print(f"[ERROR] Erreur réseau: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Erreur inattendue: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
