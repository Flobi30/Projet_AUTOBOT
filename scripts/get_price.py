#!/usr/bin/env python3
"""
AUTOBOT Phase 1 - Tâche 2/7: Récupération prix Kraken
Récupère le prix actuel BTC/EUR via l'API publique Kraken (sans clé API).

Symboles Kraken:
- XXBTZEUR = BTC/EUR
- XETHZEUR = ETH/EUR
"""

import sys
from datetime import datetime

try:
    import ccxt
except ImportError:
    print("[ERROR] ccxt non installé. Exécutez: pip install ccxt")
    sys.exit(1)


def get_price(symbol: str = "BTC/EUR") -> float:
    """Récupère le prix actuel d'une paire sur Kraken (API publique).

    Args:
        symbol: Paire de trading (ex: BTC/EUR, ETH/EUR)

    Returns:
        Prix actuel en EUR

    Raises:
        RuntimeError: Si la récupération du prix échoue
    """
    try:
        exchange = ccxt.kraken({"enableRateLimit": True})
        ticker = exchange.fetch_ticker(symbol)
        price = ticker["last"]
        if price is None:
            raise RuntimeError(f"Prix indisponible pour {symbol}")
        return float(price)
    except ccxt.NetworkError as e:
        raise RuntimeError(f"Erreur réseau Kraken: {e}") from e
    except ccxt.ExchangeError as e:
        raise RuntimeError(f"Erreur exchange Kraken: {e}") from e
    except Exception as e:
        raise RuntimeError(f"Erreur récupération prix: {e}") from e


def main() -> None:
    """Affiche le prix BTC/EUR actuel depuis Kraken."""
    symbol = "BTC/EUR"
    print(f"[{datetime.now().isoformat()}] Récupération prix {symbol} sur Kraken...")

    try:
        price = get_price(symbol)
        print(f"[PRICE] {symbol}: {price:.2f} EUR")
        print("[STATUS] Prix récupéré avec succès")
    except RuntimeError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
