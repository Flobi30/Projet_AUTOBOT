#!/usr/bin/env python3
"""
AUTOBOT Phase 1 - Connexion API Kraken
Script pour vérifier la connexion à Kraken et récupérer les balances.

Avantages Kraken vs Binance:
- Pas de géoblocage (accessible depuis tous les serveurs)
- API stable et bien documentée
- Idéal pour Grid Trading

Symboles Kraken:
- XXBTZEUR = BTC/EUR
- XETHZEUR = ETH/EUR
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
    """Connexion à Kraken et récupération des balances."""
    api_key = os.getenv("KRAKEN_API_KEY", "")
    api_secret = os.getenv("KRAKEN_API_SECRET", "")

    if not api_key or not api_secret:
        print("[ERROR] Variables KRAKEN_API_KEY et KRAKEN_API_SECRET requises")
        print("Créez vos clés sur: https://www.kraken.com/u/security/api")
        print("\nInstructions:")
        print("1. Connectez-vous à votre compte Kraken")
        print("2. Allez dans Security > API")
        print("3. Créez une nouvelle clé avec les permissions:")
        print("   - Query Funds (pour voir les balances)")
        print("   - Query Open Orders & Trades (optionnel)")
        print("4. Copiez la clé API et la clé privée")
        print("5. Ajoutez-les dans votre fichier .env:")
        print("   KRAKEN_API_KEY=votre_cle_api")
        print("   KRAKEN_API_SECRET=votre_cle_privee")
        sys.exit(1)

    try:
        exchange = ccxt.kraken({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
        })

        print(f"[{datetime.now().isoformat()}] Connexion à Kraken...")
        
        balance = exchange.fetch_balance()

        eur = balance['total'].get('EUR', 0)
        btc = balance['total'].get('BTC', 0)

        print("[CONNECT] Kraken OK")
        print(f"[BALANCE] EUR: {eur:.2f}, BTC: {btc:.8f}")
        print("[STATUS] Connexion opérationnelle")

        ticker = exchange.fetch_ticker('BTC/EUR')
        print(f"[MARKET] BTC/EUR: {ticker['last']:.2f} EUR")

    except ccxt.AuthenticationError as e:
        print(f"[ERROR] Authentification échouée: {e}")
        print("Vérifiez vos clés API sur https://www.kraken.com/u/security/api")
        sys.exit(1)
    except ccxt.NetworkError as e:
        print(f"[ERROR] Erreur réseau: {e}")
        sys.exit(1)
    except ccxt.ExchangeError as e:
        print(f"[ERROR] Erreur exchange: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Erreur inattendue: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
