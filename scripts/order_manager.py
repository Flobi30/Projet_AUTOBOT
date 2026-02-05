#!/usr/bin/env python3
"""
AUTOBOT Phase 1 - Tâche 4/7: Placement ordre achat sur Kraken

Place un ordre d'achat LIMIT sur BTC/EUR via l'API Kraken authentifiée.
Utilise le Grid Calculator (Tâche 3) pour déterminer le prix Level 0
et le volume correspondant.

Flux:
1. Connexion Kraken (ccxt authentifié)
2. Récupération prix BTC/EUR actuel
3. Calcul grid → prix Level 0 (le plus bas)
4. Vérification fonds EUR disponibles
5. Placement ordre LIMIT buy
6. Récupération ID ordre
7. Vérification dans Open Orders

Symboles Kraken:
- XXBTZEUR = BTC/EUR
- Pair ccxt: BTC/EUR
"""

import os
import sys
import time
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any

try:
    import ccxt
except ImportError:
    print("[ERROR] ccxt non installé. Exécutez: pip install ccxt")
    sys.exit(1)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
GRID_ENGINE_DIR = os.path.join(SCRIPT_DIR, '..', 'src', 'grid_engine')
sys.path.insert(0, GRID_ENGINE_DIR)

from grid_calculator import GridCalculator, GridConfig, GridLevel  # noqa: E402

logger = logging.getLogger(__name__)

KRAKEN_PAIR_CCXT = "BTC/EUR"
KRAKEN_PAIR_API = "XXBTZEUR"
GRID_TOTAL_CAPITAL = 500.0
GRID_NUM_LEVELS = 15
GRID_RANGE_PERCENT = 14.0
KRAKEN_FEE_PERCENT = 0.26
KRAKEN_MIN_ORDER_BTC = 0.0001


@dataclass
class KrakenOrder:
    """
    Représente un ordre placé sur Kraken.

    Attributes:
        order_id: ID interne
        exchange_order_id: ID Kraken (txid)
        pair: Paire de trading
        side: buy ou sell
        order_type: limit ou market
        price: Prix de l'ordre
        volume_btc: Volume en BTC
        volume_eur: Volume en EUR
        level_id: ID du niveau grid associé
        status: Statut de l'ordre
        created_at: Date de création
        description: Description Kraken de l'ordre
    """
    order_id: str
    exchange_order_id: str
    pair: str
    side: str
    order_type: str
    price: float
    volume_btc: float
    volume_eur: float
    level_id: int
    status: str = "open"
    created_at: datetime = field(default_factory=datetime.utcnow)
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "order_id": self.order_id,
            "exchange_order_id": self.exchange_order_id,
            "pair": self.pair,
            "side": self.side,
            "order_type": self.order_type,
            "price": self.price,
            "volume_btc": self.volume_btc,
            "volume_eur": self.volume_eur,
            "level_id": self.level_id,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "description": self.description,
        }


def create_kraken_client() -> ccxt.kraken:
    """
    Crée un client Kraken authentifié via ccxt.

    Returns:
        Instance ccxt.kraken configurée

    Raises:
        SystemExit: Si les clés API ne sont pas configurées
    """
    api_key = os.getenv("KRAKEN_API_KEY", "")
    api_secret = os.getenv("KRAKEN_API_SECRET", "")

    if not api_key or not api_secret:
        print("[ERROR] Variables KRAKEN_API_KEY et KRAKEN_API_SECRET requises")
        print("Configurez vos clés dans .env:")
        print("  KRAKEN_API_KEY=votre_cle_api")
        print("  KRAKEN_API_SECRET=votre_cle_privee")
        sys.exit(1)

    exchange = ccxt.kraken({
        'apiKey': api_key,
        'secret': api_secret,
        'enableRateLimit': True,
    })

    return exchange


def get_btc_eur_price(exchange: ccxt.kraken) -> Dict[str, float]:
    """
    Récupère le prix BTC/EUR actuel sur Kraken.

    Args:
        exchange: Client Kraken ccxt

    Returns:
        Dict avec price, bid, ask
    """
    ticker = exchange.fetch_ticker(KRAKEN_PAIR_CCXT)
    return {
        "price": ticker['last'],
        "bid": ticker['bid'],
        "ask": ticker['ask'],
    }


def calculate_grid_level_0(center_price: float) -> GridLevel:
    """
    Calcule le niveau 0 (le plus bas) du grid.

    Args:
        center_price: Prix central (prix actuel BTC/EUR)

    Returns:
        GridLevel pour le Level 0
    """
    config = GridConfig(
        symbol=KRAKEN_PAIR_CCXT,
        total_capital=GRID_TOTAL_CAPITAL,
        num_levels=GRID_NUM_LEVELS,
        range_percent=GRID_RANGE_PERCENT,
        min_order_size=KRAKEN_MIN_ORDER_BTC,
        fee_percent=KRAKEN_FEE_PERCENT,
    )
    calculator = GridCalculator(config)
    levels = calculator.calculate_grid(center_price)
    return levels[0]


def check_eur_balance(exchange: ccxt.kraken, required_eur: float) -> Dict[str, Any]:
    """
    Vérifie que les fonds EUR sont suffisants.

    Args:
        exchange: Client Kraken ccxt
        required_eur: Montant EUR requis pour l'ordre

    Returns:
        Dict avec available, required, sufficient
    """
    balance = exchange.fetch_balance()
    eur_free = balance.get('free', {}).get('EUR', 0.0)
    eur_total = balance.get('total', {}).get('EUR', 0.0)

    return {
        "available": eur_free,
        "total": eur_total,
        "required": required_eur,
        "sufficient": eur_free >= required_eur,
    }


def place_buy_order(
    exchange: ccxt.kraken,
    price: float,
    volume_btc: float,
    level_id: int = 0,
) -> KrakenOrder:
    """
    Place un ordre d'achat LIMIT sur Kraken.

    Args:
        exchange: Client Kraken ccxt authentifié
        price: Prix LIMIT en EUR
        volume_btc: Volume en BTC
        level_id: ID du niveau grid

    Returns:
        KrakenOrder avec les détails de l'ordre créé

    Raises:
        ccxt.InsufficientFunds: Fonds EUR insuffisants
        ccxt.InvalidOrder: Paramètres d'ordre invalides
        ccxt.ExchangeError: Erreur exchange générale
    """
    volume_btc = round(volume_btc, 8)
    price = round(price, 1)
    volume_eur = round(volume_btc * price, 2)

    print("[ORDER] Placement ordre LIMIT BUY...")
    print(f"  Paire: {KRAKEN_PAIR_CCXT}")
    print(f"  Prix: {price:.1f} EUR")
    print(f"  Volume: {volume_btc:.8f} BTC (~{volume_eur:.2f} EUR)")

    result = exchange.create_order(
        symbol=KRAKEN_PAIR_CCXT,
        type='limit',
        side='buy',
        amount=volume_btc,
        price=price,
    )

    exchange_order_id = result.get('id', '')
    description = result.get('info', {}).get('descr', {}).get('order', '')
    status = result.get('status', 'open')

    order = KrakenOrder(
        order_id=f"GRID-L{level_id}-{int(datetime.utcnow().timestamp())}",
        exchange_order_id=exchange_order_id,
        pair=KRAKEN_PAIR_CCXT,
        side="buy",
        order_type="limit",
        price=price,
        volume_btc=volume_btc,
        volume_eur=volume_eur,
        level_id=level_id,
        status=status,
        description=description,
    )

    print("[OK] Ordre créé!")
    print(f"  Kraken Order ID: {exchange_order_id}")
    print(f"  Statut: {status}")
    if description:
        print(f"  Description: {description}")

    return order


def verify_open_order(exchange: ccxt.kraken, exchange_order_id: str) -> Dict[str, Any]:
    """
    Vérifie qu'un ordre apparaît dans les Open Orders Kraken.

    Args:
        exchange: Client Kraken ccxt
        exchange_order_id: ID Kraken de l'ordre

    Returns:
        Dict avec found, order_info, open_orders_count
    """
    print(f"\n[VERIFY] Vérification ordre {exchange_order_id} dans Open Orders...")

    time.sleep(2)

    open_orders = exchange.fetch_open_orders(KRAKEN_PAIR_CCXT)

    found = False
    order_info: Optional[Dict[str, Any]] = None

    for o in open_orders:
        if o.get('id') == exchange_order_id:
            found = True
            order_info = {
                "id": o.get('id'),
                "status": o.get('status'),
                "type": o.get('type'),
                "side": o.get('side'),
                "price": o.get('price'),
                "amount": o.get('amount'),
                "filled": o.get('filled'),
                "remaining": o.get('remaining'),
                "timestamp": o.get('datetime'),
            }
            break

    result = {
        "found": found,
        "order_info": order_info,
        "open_orders_count": len(open_orders),
    }

    if found:
        print("[OK] Ordre trouvé dans Open Orders!")
        print(f"  Statut: {order_info['status']}")
        print(f"  Prix: {order_info['price']} EUR")
        print(f"  Volume: {order_info['amount']} BTC")
        print(f"  Rempli: {order_info['filled']} BTC")
    else:
        print("[WARN] Ordre non trouvé dans Open Orders")
        print(f"  Total Open Orders BTC/EUR: {len(open_orders)}")

    return result


def query_order(exchange: ccxt.kraken, exchange_order_id: str) -> Dict[str, Any]:
    """
    Interroge le statut d'un ordre spécifique via l'API Kraken.

    Args:
        exchange: Client Kraken ccxt
        exchange_order_id: ID Kraken de l'ordre

    Returns:
        Dict avec les détails de l'ordre
    """
    print(f"\n[QUERY] Interrogation ordre {exchange_order_id}...")

    order = exchange.fetch_order(exchange_order_id, KRAKEN_PAIR_CCXT)

    info = {
        "id": order.get('id'),
        "status": order.get('status'),
        "type": order.get('type'),
        "side": order.get('side'),
        "price": order.get('price'),
        "amount": order.get('amount'),
        "filled": order.get('filled'),
        "remaining": order.get('remaining'),
        "cost": order.get('cost'),
        "fee": order.get('fee'),
        "timestamp": order.get('datetime'),
    }

    print(f"  Statut: {info['status']}")
    print(f"  Prix: {info['price']} EUR")
    print(f"  Volume: {info['amount']} BTC")
    print(f"  Rempli: {info['filled']} / {info['amount']} BTC")

    return info


def main():
    """Point d'entrée principal - Place un ordre d'achat Grid Level 0."""
    print("=" * 60)
    print("AUTOBOT Phase 1 - Tâche 4/7: Placement ordre achat Kraken")
    print("=" * 60)

    print("\n[1/6] Connexion à Kraken (authentifiée)...")
    exchange = create_kraken_client()
    balance = exchange.fetch_balance()
    eur_total = balance.get('total', {}).get('EUR', 0.0)
    btc_total = balance.get('total', {}).get('BTC', 0.0)
    print(f"  [OK] Connecté | EUR: {eur_total:.2f} | BTC: {btc_total:.8f}")

    print("\n[2/6] Récupération prix BTC/EUR...")
    price_data = get_btc_eur_price(exchange)
    current_price = price_data['price']
    print(f"  Prix actuel: {current_price:.2f} EUR")
    print(f"  Bid: {price_data['bid']:.2f} | Ask: {price_data['ask']:.2f}")

    print("\n[3/6] Calcul Grid Level 0...")
    level_0 = calculate_grid_level_0(current_price)
    print(f"  Level 0 prix: {level_0.price:.2f} EUR")
    print(f"  Volume: {level_0.quantity:.8f} BTC")
    print(f"  Capital alloué: {level_0.allocated_capital:.2f} EUR")
    print(f"  Side: {level_0.side.value}")

    volume_eur = level_0.quantity * level_0.price
    print(f"  Valeur ordre: ~{volume_eur:.2f} EUR")

    print("\n[4/6] Vérification fonds EUR...")
    balance_check = check_eur_balance(exchange, volume_eur)
    print(f"  Disponible: {balance_check['available']:.2f} EUR")
    print(f"  Requis: {balance_check['required']:.2f} EUR")

    if not balance_check['sufficient']:
        print("  [ERROR] Fonds insuffisants!")
        print(f"  Manque: {balance_check['required'] - balance_check['available']:.2f} EUR")
        sys.exit(1)
    print("  [OK] Fonds suffisants")

    print("\n[5/6] Placement ordre LIMIT BUY...")
    try:
        order = place_buy_order(
            exchange=exchange,
            price=level_0.price,
            volume_btc=level_0.quantity,
            level_id=level_0.level_id,
        )
    except ccxt.InsufficientFunds as e:
        print(f"[ERROR] Fonds insuffisants: {e}")
        sys.exit(1)
    except ccxt.InvalidOrder as e:
        print(f"[ERROR] Ordre invalide: {e}")
        print("Vérifiez le prix et le volume minimum")
        sys.exit(1)
    except ccxt.ExchangeError as e:
        print(f"[ERROR] Erreur exchange: {e}")
        sys.exit(1)

    print("\n[6/6] Vérification ordre dans Open Orders...")
    verification = verify_open_order(exchange, order.exchange_order_id)

    order_details = query_order(exchange, order.exchange_order_id)

    print("\n" + "=" * 60)
    print("RÉSUMÉ")
    print("=" * 60)
    print(f"  Ordre ID (interne): {order.order_id}")
    print(f"  Kraken txid: {order.exchange_order_id}")
    print(f"  Paire: {order.pair}")
    print(f"  Type: {order.order_type.upper()} {order.side.upper()}")
    print(f"  Prix: {order.price:.1f} EUR")
    print(f"  Volume: {order.volume_btc:.8f} BTC (~{order.volume_eur:.2f} EUR)")
    print(f"  Grid Level: {order.level_id}")
    print(f"  Statut: {order_details.get('status', order.status)}")
    print(f"  Visible Open Orders: {'OUI' if verification['found'] else 'NON'}")
    print(f"  Créé: {order.created_at.isoformat()}")

    if verification['found']:
        print("\n[SUCCESS] Ordre créé et visible dans Open Orders Kraken!")
    else:
        print("\n[WARN] Ordre créé mais non visible (peut-être déjà exécuté)")

    return order


if __name__ == "__main__":
    main()
