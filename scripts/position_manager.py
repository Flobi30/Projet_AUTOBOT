#!/usr/bin/env python3
"""
AUTOBOT Phase 1 - Tache 5/7: Detection fill achat + placement vente

Detecte quand un ordre d'achat est filled sur Kraken et place
automatiquement un ordre de vente LIMIT au niveau superieur du grid.

Cycle complet:
1. Query open orders sur Kraken
2. Detecter les ordres d'achat closed/filled
3. Calculer le prix de vente (niveau superieur du grid)
4. Placer un ordre de vente LIMIT au niveau superieur
5. Logger le cycle complet BUY filled -> SELL placed

Logique Grid:
- Si Level 0 (BUY) filled a 51588 EUR -> Placer SELL Level 8 a 56025 EUR
- Si Level 1 (BUY) filled a 52142 EUR -> Placer SELL Level 9 a 56580 EUR
- Profit par niveau: ~0.8%

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
from typing import Optional, Dict, List, Any

try:
    import ccxt
except ImportError:
    print("[ERROR] ccxt non installe. Executez: pip install ccxt")
    sys.exit(1)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from grid_calculator import GridConfig, GridLevel, calculate_grid_levels  # noqa: E402
from order_manager import (  # noqa: E402
    create_kraken_client,
    get_btc_eur_price,
    KrakenOrder,
    KRAKEN_PAIR_CCXT,
    GRID_TOTAL_CAPITAL,
    GRID_NUM_LEVELS,
    GRID_RANGE_PERCENT,
    KRAKEN_FEE_PERCENT,
    KRAKEN_MIN_ORDER_BTC,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

SELL_LEVEL_OFFSET = 8
PROFIT_TARGET_PERCENT = 0.8
POLL_INTERVAL_SECONDS = 5


@dataclass
class GridPosition:
    """
    Represente une position dans le grid trading.

    Suit le cycle complet: BUY filled -> SELL placed -> SELL filled.

    Attributes:
        position_id: Identifiant unique de la position
        level_id: Niveau du grid (0-14)
        buy_order_id: ID Kraken de l'ordre d'achat
        sell_order_id: ID Kraken de l'ordre de vente (si place)
        buy_price: Prix d'achat
        sell_price: Prix de vente cible
        volume_btc: Volume en BTC
        status: Statut de la position (open, sell_placed, closed)
        buy_filled_at: Timestamp du fill achat
        sell_filled_at: Timestamp du fill vente
        profit_eur: Profit realise en EUR
        profit_percent: Profit en pourcentage
    """
    position_id: str
    level_id: int
    buy_order_id: str
    buy_price: float
    volume_btc: float
    sell_order_id: Optional[str] = None
    sell_price: Optional[float] = None
    status: str = "open"
    buy_filled_at: Optional[datetime] = None
    sell_filled_at: Optional[datetime] = None
    profit_eur: float = 0.0
    profit_percent: float = 0.0
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "position_id": self.position_id,
            "level_id": self.level_id,
            "buy_order_id": self.buy_order_id,
            "sell_order_id": self.sell_order_id,
            "buy_price": self.buy_price,
            "sell_price": self.sell_price,
            "volume_btc": self.volume_btc,
            "status": self.status,
            "buy_filled_at": self.buy_filled_at.isoformat() if self.buy_filled_at else None,
            "sell_filled_at": self.sell_filled_at.isoformat() if self.sell_filled_at else None,
            "profit_eur": round(self.profit_eur, 4),
            "profit_percent": round(self.profit_percent, 4),
            "created_at": self.created_at.isoformat(),
        }


def build_grid(center_price: float) -> List[GridLevel]:
    """
    Construit le grid complet de 15 niveaux autour du prix central.

    Args:
        center_price: Prix central BTC/EUR

    Returns:
        Liste de 15 GridLevel ordonnes du plus bas au plus haut
    """
    config = GridConfig(
        symbol=KRAKEN_PAIR_CCXT,
        capital_total=GRID_TOTAL_CAPITAL,
        num_levels=GRID_NUM_LEVELS,
        range_percent=GRID_RANGE_PERCENT,
    )
    levels = calculate_grid_levels(center_price, config)
    return levels


def get_sell_level_for_buy(buy_level_id: int, levels: List[GridLevel]) -> Optional[GridLevel]:
    """
    Determine le niveau de vente correspondant a un niveau d'achat.

    Logique: BUY Level N -> SELL Level (N + SELL_LEVEL_OFFSET)
    - Level 0 (BUY) -> Level 8 (SELL)
    - Level 1 (BUY) -> Level 9 (SELL)
    - Level 6 (BUY) -> Level 14 (SELL)

    Args:
        buy_level_id: ID du niveau d'achat (0-6)
        levels: Liste complete des niveaux du grid

    Returns:
        GridLevel de vente ou None si hors limites
    """
    sell_level_id = buy_level_id + SELL_LEVEL_OFFSET

    if sell_level_id >= len(levels):
        logger.warning(
            f"Sell level {sell_level_id} hors limites "
            f"(max: {len(levels) - 1}) pour buy level {buy_level_id}"
        )
        return None

    sell_level = levels[sell_level_id]

    if sell_level.level_type != "SELL":
        logger.warning(
            f"Level {sell_level_id} n'est pas un SELL level "
            f"(type: {sell_level.level_type})"
        )
        return None

    return sell_level


def calculate_sell_price(buy_price: float, sell_level: GridLevel) -> float:
    """
    Calcule le prix de vente optimal.

    Utilise le prix du niveau de vente du grid comme reference,
    avec un minimum de profit_target_percent au-dessus du prix d'achat.

    Args:
        buy_price: Prix d'achat effectif
        sell_level: Niveau de vente du grid

    Returns:
        Prix de vente en EUR
    """
    grid_sell_price = sell_level.price

    min_sell_price = buy_price * (1 + PROFIT_TARGET_PERCENT / 100)

    final_price = max(grid_sell_price, min_sell_price)

    return round(final_price, 1)


def fetch_open_orders(exchange: ccxt.kraken) -> List[Dict[str, Any]]:
    """
    Recupere tous les ordres ouverts BTC/EUR sur Kraken.

    Args:
        exchange: Client Kraken ccxt

    Returns:
        Liste des ordres ouverts
    """
    open_orders = exchange.fetch_open_orders(KRAKEN_PAIR_CCXT)

    result = []
    for order in open_orders:
        result.append({
            "id": order.get("id"),
            "status": order.get("status"),
            "type": order.get("type"),
            "side": order.get("side"),
            "price": order.get("price"),
            "amount": order.get("amount"),
            "filled": order.get("filled"),
            "remaining": order.get("remaining"),
            "timestamp": order.get("datetime"),
        })

    return result


def check_order_status(exchange: ccxt.kraken, order_id: str) -> Dict[str, Any]:
    """
    Verifie le statut d'un ordre specifique sur Kraken.

    Args:
        exchange: Client Kraken ccxt
        order_id: ID Kraken de l'ordre

    Returns:
        Dict avec statut et details de l'ordre
    """
    try:
        order = exchange.fetch_order(order_id, KRAKEN_PAIR_CCXT)
        return {
            "id": order.get("id"),
            "status": order.get("status"),
            "side": order.get("side"),
            "type": order.get("type"),
            "price": order.get("price"),
            "amount": order.get("amount"),
            "filled": order.get("filled"),
            "remaining": order.get("remaining"),
            "cost": order.get("cost"),
            "fee": order.get("fee"),
            "average": order.get("average"),
            "timestamp": order.get("datetime"),
        }
    except ccxt.OrderNotFound:
        logger.error(f"Ordre {order_id} non trouve sur Kraken")
        return {"id": order_id, "status": "not_found"}
    except ccxt.ExchangeError as e:
        logger.error(f"Erreur Kraken pour ordre {order_id}: {e}")
        return {"id": order_id, "status": "error", "error": str(e)}


def is_order_filled(order_info: Dict[str, Any]) -> bool:
    """
    Determine si un ordre est completement filled.

    Args:
        order_info: Informations de l'ordre depuis Kraken

    Returns:
        True si l'ordre est filled/closed
    """
    status = order_info.get("status", "")
    return status in ("closed", "filled")


def place_sell_order(
    exchange: ccxt.kraken,
    price: float,
    volume_btc: float,
    level_id: int,
) -> KrakenOrder:
    """
    Place un ordre de vente LIMIT sur Kraken.

    Args:
        exchange: Client Kraken ccxt authentifie
        price: Prix LIMIT en EUR
        volume_btc: Volume en BTC
        level_id: ID du niveau grid

    Returns:
        KrakenOrder avec les details de l'ordre cree

    Raises:
        ccxt.InsufficientFunds: Fonds BTC insuffisants
        ccxt.InvalidOrder: Parametres d'ordre invalides
        ccxt.ExchangeError: Erreur exchange generale
    """
    volume_btc = round(volume_btc, 8)
    price = round(price, 1)
    volume_eur = round(volume_btc * price, 2)

    logger.info(
        f"[SELL ORDER] Placement LIMIT SELL | "
        f"Prix: {price:.1f} EUR | Volume: {volume_btc:.8f} BTC (~{volume_eur:.2f} EUR)"
    )

    result = exchange.create_order(
        symbol=KRAKEN_PAIR_CCXT,
        type="limit",
        side="sell",
        amount=volume_btc,
        price=price,
    )

    exchange_order_id = result.get("id", "")
    description = result.get("info", {}).get("descr", {}).get("order", "")
    status = result.get("status", "open")

    order = KrakenOrder(
        order_id=f"GRID-SELL-L{level_id}-{int(datetime.utcnow().timestamp())}",
        exchange_order_id=exchange_order_id,
        pair=KRAKEN_PAIR_CCXT,
        side="sell",
        order_type="limit",
        price=price,
        volume_btc=volume_btc,
        volume_eur=volume_eur,
        level_id=level_id,
        status=status,
        description=description,
    )

    logger.info(
        f"[SELL ORDER OK] Kraken ID: {exchange_order_id} | "
        f"Statut: {status} | Level: {level_id}"
    )

    return order


def handle_fill_and_sell(
    exchange: ccxt.kraken,
    buy_order_id: str,
    buy_level_id: int,
    levels: List[GridLevel],
) -> Optional[GridPosition]:
    """
    Gere le cycle complet: detection fill achat -> placement vente.

    1. Verifie le statut de l'ordre d'achat
    2. Si filled, determine le niveau de vente
    3. Calcule le prix de vente
    4. Place l'ordre de vente LIMIT
    5. Cree et retourne la GridPosition

    Args:
        exchange: Client Kraken ccxt authentifie
        buy_order_id: ID Kraken de l'ordre d'achat
        buy_level_id: Niveau du grid de l'achat (0-6)
        levels: Liste complete des niveaux du grid

    Returns:
        GridPosition si un cycle a ete complete, None sinon
    """
    logger.info(f"[CHECK] Verification ordre achat {buy_order_id} (Level {buy_level_id})...")

    order_info = check_order_status(exchange, buy_order_id)

    if not is_order_filled(order_info):
        current_status = order_info.get("status", "unknown")
        filled_amount = order_info.get("filled", 0)
        total_amount = order_info.get("amount", 0)
        logger.info(
            f"[WAIT] Ordre {buy_order_id} non filled | "
            f"Statut: {current_status} | Filled: {filled_amount}/{total_amount}"
        )
        return None

    buy_price = order_info.get("average") or order_info.get("price", 0)
    volume_btc = order_info.get("filled", 0)
    buy_cost = order_info.get("cost", buy_price * volume_btc)
    buy_fee = order_info.get("fee", {})
    fee_cost = buy_fee.get("cost", 0) if isinstance(buy_fee, dict) else 0

    logger.info(
        f"[FILLED] Achat FILLED! | Level {buy_level_id} | "
        f"Prix: {buy_price:.2f} EUR | Volume: {volume_btc:.8f} BTC | "
        f"Cout: {buy_cost:.2f} EUR | Fee: {fee_cost:.4f}"
    )

    sell_level = get_sell_level_for_buy(buy_level_id, levels)
    if sell_level is None:
        logger.error(
            f"[ERROR] Impossible de trouver le niveau de vente "
            f"pour buy level {buy_level_id}"
        )
        return None

    sell_price = calculate_sell_price(buy_price, sell_level)

    expected_profit_eur = (sell_price - buy_price) * volume_btc
    expected_profit_pct = ((sell_price - buy_price) / buy_price) * 100

    logger.info(
        f"[SELL TARGET] Level {sell_level.level} | "
        f"Prix vente: {sell_price:.1f} EUR | "
        f"Profit attendu: {expected_profit_eur:.2f} EUR ({expected_profit_pct:.2f}%)"
    )

    try:
        sell_order = place_sell_order(
            exchange=exchange,
            price=sell_price,
            volume_btc=volume_btc,
            level_id=sell_level.level,
        )
    except ccxt.InsufficientFunds as e:
        logger.error(f"[ERROR] Fonds BTC insuffisants pour vente: {e}")
        return None
    except ccxt.InvalidOrder as e:
        logger.error(f"[ERROR] Ordre de vente invalide: {e}")
        return None
    except ccxt.ExchangeError as e:
        logger.error(f"[ERROR] Erreur exchange pour vente: {e}")
        return None

    position = GridPosition(
        position_id=f"POS-L{buy_level_id}-{int(datetime.utcnow().timestamp())}",
        level_id=buy_level_id,
        buy_order_id=buy_order_id,
        buy_price=buy_price,
        volume_btc=volume_btc,
        sell_order_id=sell_order.exchange_order_id,
        sell_price=sell_price,
        status="sell_placed",
        buy_filled_at=datetime.utcnow(),
        profit_eur=expected_profit_eur,
        profit_percent=expected_profit_pct,
    )

    logger.info(
        f"[CYCLE OK] Position {position.position_id} | "
        f"BUY L{buy_level_id} @ {buy_price:.2f} -> SELL L{sell_level.level} @ {sell_price:.1f} | "
        f"Profit cible: {expected_profit_eur:.2f} EUR ({expected_profit_pct:.2f}%)"
    )

    return position


def monitor_and_manage(
    exchange: ccxt.kraken,
    tracked_orders: Dict[str, int],
    levels: List[GridLevel],
    poll_interval: int = POLL_INTERVAL_SECONDS,
    max_cycles: int = 0,
) -> List[GridPosition]:
    """
    Boucle principale de monitoring: surveille les ordres et gere les fills.

    Args:
        exchange: Client Kraken ccxt authentifie
        tracked_orders: Dict {exchange_order_id: buy_level_id} des ordres a surveiller
        levels: Liste complete des niveaux du grid
        poll_interval: Intervalle de polling en secondes (defaut: 5s)
        max_cycles: Nombre max de cycles (0 = infini)

    Returns:
        Liste des GridPosition completees
    """
    positions: List[GridPosition] = []
    pending_orders = dict(tracked_orders)
    cycle_count = 0

    logger.info(
        f"[MONITOR] Demarrage monitoring | "
        f"Ordres surveilles: {len(pending_orders)} | "
        f"Intervalle: {poll_interval}s"
    )

    while pending_orders:
        cycle_count += 1

        if max_cycles > 0 and cycle_count > max_cycles:
            logger.info(f"[MONITOR] Max cycles ({max_cycles}) atteint, arret")
            break

        logger.info(
            f"[CYCLE {cycle_count}] Verification de {len(pending_orders)} ordres..."
        )

        filled_this_cycle: List[str] = []

        for order_id, level_id in list(pending_orders.items()):
            position = handle_fill_and_sell(
                exchange=exchange,
                buy_order_id=order_id,
                buy_level_id=level_id,
                levels=levels,
            )

            if position is not None:
                positions.append(position)
                filled_this_cycle.append(order_id)

        for order_id in filled_this_cycle:
            del pending_orders[order_id]

        if filled_this_cycle:
            logger.info(
                f"[CYCLE {cycle_count}] {len(filled_this_cycle)} ordres filled | "
                f"Restant: {len(pending_orders)}"
            )

        if pending_orders:
            logger.info(f"[SLEEP] Attente {poll_interval}s avant prochain check...")
            time.sleep(poll_interval)

    logger.info(
        f"[MONITOR FIN] {len(positions)} positions completees "
        f"en {cycle_count} cycles"
    )

    return positions


def display_positions(positions: List[GridPosition]) -> None:
    """Affiche un resume des positions completees."""
    if not positions:
        print("\n[INFO] Aucune position completee")
        return

    print("\n" + "=" * 70)
    print("  POSITIONS COMPLETEES - Cycle BUY -> SELL")
    print("=" * 70)

    total_profit = 0.0

    for pos in positions:
        print(f"\n  Position: {pos.position_id}")
        print(f"    Buy  Level {pos.level_id:2d} @ {pos.buy_price:.2f} EUR")
        sell_level_id = pos.level_id + SELL_LEVEL_OFFSET
        sell_price_str = f"{pos.sell_price:.1f}" if pos.sell_price else "N/A"
        print(f"    Sell Level {sell_level_id:2d} @ {sell_price_str} EUR")
        print(f"    Volume: {pos.volume_btc:.8f} BTC")
        print(f"    Profit attendu: {pos.profit_eur:.2f} EUR ({pos.profit_percent:.2f}%)")
        print(f"    Statut: {pos.status}")
        print(f"    Sell Order ID: {pos.sell_order_id}")
        total_profit += pos.profit_eur

    print("\n" + "-" * 70)
    print(f"  Total positions: {len(positions)}")
    print(f"  Profit total attendu: {total_profit:.2f} EUR")
    print("=" * 70)


def display_grid_mapping(levels: List[GridLevel]) -> None:
    """Affiche le mapping BUY -> SELL du grid."""
    print("\n" + "=" * 70)
    print("  GRID MAPPING: BUY Level -> SELL Level")
    print("=" * 70)

    for level in levels:
        if level.level_type == "BUY":
            sell_level = get_sell_level_for_buy(level.level, levels)
            if sell_level:
                spread = sell_level.price - level.price
                spread_pct = (spread / level.price) * 100
                print(
                    f"  Level {level.level:2d} (BUY) @ {level.price:.2f} EUR "
                    f"-> Level {sell_level.level:2d} (SELL) @ {sell_level.price:.2f} EUR "
                    f"| Spread: {spread:.2f} EUR ({spread_pct:.2f}%)"
                )

    print("=" * 70)


def main():
    """Point d'entree principal - Monitoring et gestion des fills."""
    print("=" * 70)
    print("  AUTOBOT Phase 1 - Tache 5/7: Detection fill + placement vente")
    print("=" * 70)

    print("\n[1/5] Connexion a Kraken (authentifiee)...")
    exchange = create_kraken_client()
    balance = exchange.fetch_balance()
    eur_total = balance.get("total", {}).get("EUR", 0.0)
    btc_total = balance.get("total", {}).get("BTC", 0.0)
    print(f"  [OK] Connecte | EUR: {eur_total:.2f} | BTC: {btc_total:.8f}")

    print("\n[2/5] Recuperation prix BTC/EUR...")
    price_data = get_btc_eur_price(exchange)
    current_price = price_data["price"]
    print(f"  Prix actuel: {current_price:.2f} EUR")

    print("\n[3/5] Calcul grid complet (15 niveaux)...")
    levels = build_grid(current_price)

    buy_levels = [lv for lv in levels if lv.level_type == "BUY"]
    sell_levels = [lv for lv in levels if lv.level_type == "SELL"]
    print(f"  Niveaux BUY: {len(buy_levels)} (Levels 0-6)")
    print(f"  Niveaux SELL: {len(sell_levels)} (Levels 8-14)")
    print(f"  Range: {levels[0].price:.2f} - {levels[-1].price:.2f} EUR")

    display_grid_mapping(levels)

    print("\n[4/5] Recuperation ordres ouverts...")
    open_orders = fetch_open_orders(exchange)
    print(f"  Ordres ouverts BTC/EUR: {len(open_orders)}")

    buy_open_orders: Dict[str, int] = {}

    for order in open_orders:
        if order["side"] == "buy" and order["price"] is not None:
            closest_level = None
            min_distance = float("inf")
            for level in buy_levels:
                distance = abs(level.price - order["price"])
                if distance < min_distance:
                    min_distance = distance
                    closest_level = level

            if closest_level is not None:
                buy_open_orders[order["id"]] = closest_level.level
                print(
                    f"  -> Ordre {order['id']} | BUY @ {order['price']:.2f} EUR "
                    f"| Level {closest_level.level}"
                )

    if not buy_open_orders:
        print("\n[INFO] Aucun ordre d'achat ouvert a surveiller")
        print("[INFO] Placez d'abord des ordres avec order_manager.py (Tache 4)")

        print("\n[DEMO] Demonstration du cycle avec verification des ordres recents...")
        try:
            closed_orders = exchange.fetch_closed_orders(KRAKEN_PAIR_CCXT, limit=5)
            for order in closed_orders:
                if order.get("side") == "buy" and order.get("status") == "closed":
                    order_id = order.get("id")
                    order_price = order.get("average") or order.get("price", 0)
                    order_amount = order.get("filled", 0)
                    print(
                        f"\n  [FOUND] Ordre achat recemment filled: {order_id}"
                    )
                    print(f"    Prix: {order_price:.2f} EUR | Volume: {order_amount:.8f} BTC")

                    closest_level = None
                    min_distance = float("inf")
                    for level in buy_levels:
                        distance = abs(level.price - order_price)
                        if distance < min_distance:
                            min_distance = distance
                            closest_level = level

                    if closest_level is not None:
                        sell_level = get_sell_level_for_buy(closest_level.level, levels)
                        if sell_level:
                            sell_price = calculate_sell_price(order_price, sell_level)
                            profit = (sell_price - order_price) * order_amount
                            profit_pct = ((sell_price - order_price) / order_price) * 100
                            print(
                                f"    -> SELL cible: Level {sell_level.level} "
                                f"@ {sell_price:.1f} EUR"
                            )
                            print(
                                f"    -> Profit: {profit:.4f} EUR ({profit_pct:.2f}%)"
                            )
                    break
        except Exception as e:
            print(f"  [WARN] Impossible de recuperer les ordres fermes: {e}")

        print("\n[STATUS] Grid pret - En attente de fills pour lancer le cycle")
        return

    print(f"\n[5/5] Demarrage monitoring ({len(buy_open_orders)} ordres)...")
    print(f"  Intervalle: {POLL_INTERVAL_SECONDS}s")
    print("  Ctrl+C pour arreter\n")

    try:
        positions = monitor_and_manage(
            exchange=exchange,
            tracked_orders=buy_open_orders,
            levels=levels,
            poll_interval=POLL_INTERVAL_SECONDS,
        )
    except KeyboardInterrupt:
        print("\n\n[STOP] Monitoring arrete par l'utilisateur")
        positions = []

    display_positions(positions)

    print("\n[STATUS] Cycle complet termine")
    print(f"  Positions creees: {len(positions)}")

    return positions


if __name__ == "__main__":
    main()
