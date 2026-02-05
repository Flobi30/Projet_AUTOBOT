#!/usr/bin/env python3
"""
AUTOBOT Phase 1 - Tâche 2/7: Récupération prix temps réel sur Kraken

Ce script récupère le prix BTC/EUR en temps réel via l'API publique Kraken.
Le Grid Trading a besoin du prix en temps réel pour calculer les niveaux.

API utilisée: https://api.kraken.com/0/public/Ticker?pair=XXBTZEUR

Fonctionnalités:
- Récupération du prix BTC/EUR via API publique (pas besoin de clés API)
- Rafraîchissement configurable (5-10 secondes par défaut)
- Gestion des erreurs de connexion avec retry automatique
- Affichage de l'évolution du prix pour debug
"""

import sys
import time
from datetime import datetime
from typing import Optional, Dict, Any

try:
    import requests
except ImportError:
    print("[ERROR] requests non installé. Exécutez: pip install requests")
    sys.exit(1)


# Configuration par défaut
DEFAULT_REFRESH_INTERVAL = 5  # secondes
DEFAULT_PAIR = "XXBTZEUR"  # BTC/EUR sur Kraken
KRAKEN_TICKER_URL = "https://api.kraken.com/0/public/Ticker"
MAX_RETRIES = 3
RETRY_DELAY = 2  # secondes entre les retries


class KrakenPriceError(Exception):
    """Exception personnalisée pour les erreurs de récupération de prix."""
    pass


def get_current_price(
    pair: str = DEFAULT_PAIR,
    timeout: int = 10
) -> Dict[str, Any]:
    """
    Récupère le prix actuel d'une paire sur Kraken.
    
    Args:
        pair: Paire de trading (ex: XXBTZEUR pour BTC/EUR)
        timeout: Timeout de la requête en secondes
        
    Returns:
        Dict contenant:
            - price: Prix actuel (last trade)
            - bid: Meilleur prix d'achat
            - ask: Meilleur prix de vente
            - volume_24h: Volume sur 24h
            - timestamp: Timestamp de la récupération
            - pair: Paire demandée
            
    Raises:
        KrakenPriceError: En cas d'erreur de récupération
    """
    retries = 0
    last_error = None
    
    while retries < MAX_RETRIES:
        try:
            response = requests.get(
                KRAKEN_TICKER_URL,
                params={"pair": pair},
                timeout=timeout
            )
            response.raise_for_status()
            
            data = response.json()
            
            # Vérifier les erreurs Kraken
            if data.get("error") and len(data["error"]) > 0:
                raise KrakenPriceError(f"Erreur Kraken: {data['error']}")
            
            # Extraire les données du ticker
            result = data.get("result", {})
            if not result:
                raise KrakenPriceError("Aucune donnée reçue de Kraken")
            
            # Kraken peut retourner la paire avec un nom légèrement différent
            ticker_data = None
            for key in result:
                ticker_data = result[key]
                break
            
            if not ticker_data:
                raise KrakenPriceError(f"Paire {pair} non trouvée")
            
            # Extraire les informations de prix
            # Format Kraken: a=ask, b=bid, c=last trade, v=volume
            return {
                "price": float(ticker_data["c"][0]),  # Last trade price
                "bid": float(ticker_data["b"][0]),    # Best bid
                "ask": float(ticker_data["a"][0]),    # Best ask
                "volume_24h": float(ticker_data["v"][1]),  # Volume 24h
                "high_24h": float(ticker_data["h"][1]),    # High 24h
                "low_24h": float(ticker_data["l"][1]),     # Low 24h
                "timestamp": datetime.now().isoformat(),
                "pair": pair
            }
            
        except requests.exceptions.Timeout:
            last_error = "Timeout de connexion à Kraken"
            retries += 1
            print(f"[RETRY {retries}/{MAX_RETRIES}] {last_error}")
            
        except requests.exceptions.ConnectionError:
            last_error = "Erreur de connexion réseau"
            retries += 1
            print(f"[RETRY {retries}/{MAX_RETRIES}] {last_error}")
            
        except requests.exceptions.RequestException as e:
            last_error = f"Erreur HTTP: {e}"
            retries += 1
            print(f"[RETRY {retries}/{MAX_RETRIES}] {last_error}")
            
        except (KeyError, IndexError, ValueError) as e:
            raise KrakenPriceError(f"Erreur de parsing des données: {e}")
        
        if retries < MAX_RETRIES:
            time.sleep(RETRY_DELAY)
    
    raise KrakenPriceError(f"Échec après {MAX_RETRIES} tentatives: {last_error}")


def format_price_display(price_data: Dict[str, Any], previous_price: Optional[float] = None) -> str:
    """
    Formate l'affichage du prix avec indication de tendance.
    
    Args:
        price_data: Données de prix retournées par get_current_price()
        previous_price: Prix précédent pour calculer la variation
        
    Returns:
        String formatée pour l'affichage
    """
    price = price_data["price"]
    timestamp = price_data["timestamp"]
    
    # Indicateur de tendance
    if previous_price is not None:
        if price > previous_price:
            trend = "↑"
            change = f"+{price - previous_price:.2f}"
        elif price < previous_price:
            trend = "↓"
            change = f"{price - previous_price:.2f}"
        else:
            trend = "="
            change = "0.00"
        trend_info = f" {trend} ({change} EUR)"
    else:
        trend_info = ""
    
    return (
        f"[{timestamp}] BTC/EUR: {price:.2f} EUR{trend_info} | "
        f"Bid: {price_data['bid']:.2f} | Ask: {price_data['ask']:.2f} | "
        f"24h: {price_data['low_24h']:.2f}-{price_data['high_24h']:.2f}"
    )


def run_price_monitor(
    refresh_interval: int = DEFAULT_REFRESH_INTERVAL,
    pair: str = DEFAULT_PAIR,
    max_iterations: Optional[int] = None
) -> None:
    """
    Lance le monitoring continu du prix.
    
    Args:
        refresh_interval: Intervalle de rafraîchissement en secondes (5-10 recommandé)
        pair: Paire de trading à surveiller
        max_iterations: Nombre max d'itérations (None = infini)
    """
    print("=" * 70)
    print(f"AUTOBOT - Monitoring Prix Kraken")
    print(f"Paire: {pair} | Rafraîchissement: {refresh_interval}s")
    print("=" * 70)
    print("Appuyez sur Ctrl+C pour arrêter\n")
    
    previous_price = None
    iteration = 0
    
    try:
        while max_iterations is None or iteration < max_iterations:
            try:
                price_data = get_current_price(pair=pair)
                print(format_price_display(price_data, previous_price))
                previous_price = price_data["price"]
                
            except KrakenPriceError as e:
                print(f"[ERROR] {e}")
            
            iteration += 1
            
            if max_iterations is None or iteration < max_iterations:
                time.sleep(refresh_interval)
                
    except KeyboardInterrupt:
        print("\n\n[STOP] Monitoring arrêté par l'utilisateur")
        print(f"Dernière itération: {iteration}")
        if previous_price:
            print(f"Dernier prix: {previous_price:.2f} EUR")


def main():
    """Point d'entrée principal avec arguments CLI."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Récupération du prix BTC/EUR en temps réel via Kraken"
    )
    parser.add_argument(
        "-i", "--interval",
        type=int,
        default=DEFAULT_REFRESH_INTERVAL,
        help=f"Intervalle de rafraîchissement en secondes (défaut: {DEFAULT_REFRESH_INTERVAL})"
    )
    parser.add_argument(
        "-p", "--pair",
        type=str,
        default=DEFAULT_PAIR,
        help=f"Paire de trading (défaut: {DEFAULT_PAIR})"
    )
    parser.add_argument(
        "-n", "--iterations",
        type=int,
        default=None,
        help="Nombre d'itérations (défaut: infini)"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Récupérer le prix une seule fois et quitter"
    )
    
    args = parser.parse_args()
    
    if args.once:
        # Mode single shot
        try:
            price_data = get_current_price(pair=args.pair)
            print(f"Prix BTC/EUR: {price_data['price']:.2f} EUR")
            print(f"Bid: {price_data['bid']:.2f} | Ask: {price_data['ask']:.2f}")
            print(f"Volume 24h: {price_data['volume_24h']:.2f}")
            print(f"Range 24h: {price_data['low_24h']:.2f} - {price_data['high_24h']:.2f}")
        except KrakenPriceError as e:
            print(f"[ERROR] {e}")
            sys.exit(1)
    else:
        # Mode monitoring continu
        run_price_monitor(
            refresh_interval=args.interval,
            pair=args.pair,
            max_iterations=args.iterations
        )


if __name__ == "__main__":
    main()
