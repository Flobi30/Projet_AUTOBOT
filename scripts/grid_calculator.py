#!/usr/bin/env python3
"""
AUTOBOT Phase 1 - Tâche 3/7: Calcul Grid Trading 15 niveaux
Calcule les niveaux de grid trading pour BTC/EUR sur Kraken.

Grid statique avec 15 niveaux équidistants, range +/- 7% autour du prix actuel.
Capital 500€ réparti équitablement sur chaque niveau.
"""

import sys
from dataclasses import dataclass
from datetime import datetime
from typing import List

from get_price import get_price


@dataclass
class GridConfig:
    """Configuration du grid trading."""

    symbol: str = "BTC/EUR"
    kraken_symbol: str = "XXBTZEUR"
    capital_total: float = 500.0
    num_levels: int = 15
    range_percent: float = 14.0
    profit_per_level: float = 0.8

    @property
    def capital_per_level(self) -> float:
        return self.capital_total / self.num_levels

    @property
    def half_range_percent(self) -> float:
        return self.range_percent / 2.0


@dataclass
class GridLevel:
    """Représente un niveau de la grille."""

    level: int
    price: float
    level_type: str
    capital_allocated: float
    btc_quantity: float

    def __str__(self) -> str:
        if self.level_type == "CENTER":
            return f"Level {self.level:2d} (CENTER): {self.price:.2f} EUR"
        return (
            f"Level {self.level:2d} ({self.level_type:4s}): "
            f"{self.price:.2f} EUR - {self.capital_allocated:.2f}€ "
            f"({self.btc_quantity:.8f} BTC)"
        )


def calculate_grid_levels(
    current_price: float, config: GridConfig
) -> List[GridLevel]:
    """Calcule les 15 niveaux de grid trading.

    Args:
        current_price: Prix actuel BTC/EUR
        config: Configuration du grid

    Returns:
        Liste de 15 GridLevel ordonnés du plus bas au plus haut
    """
    lower_price = current_price * (1 - config.half_range_percent / 100)
    upper_price = current_price * (1 + config.half_range_percent / 100)

    price_step = (upper_price - lower_price) / (config.num_levels - 1)

    levels: List[GridLevel] = []

    for i in range(config.num_levels):
        price = lower_price + i * price_step

        if i < 7:
            level_type = "BUY"
        elif i == 7:
            level_type = "CENTER"
        else:
            level_type = "SELL"

        if level_type == "CENTER":
            capital_allocated = 0.0
            btc_quantity = 0.0
        else:
            capital_allocated = config.capital_per_level
            btc_quantity = capital_allocated / price

        levels.append(
            GridLevel(
                level=i,
                price=price,
                level_type=level_type,
                capital_allocated=capital_allocated,
                btc_quantity=btc_quantity,
            )
        )

    return levels


def display_grid(
    levels: List[GridLevel], current_price: float, config: GridConfig
) -> None:
    """Affiche la grille de trading formatée.

    Args:
        levels: Liste des niveaux calculés
        current_price: Prix actuel
        config: Configuration utilisée
    """
    lower_price = levels[0].price
    upper_price = levels[-1].price

    print("=" * 65)
    print(f"  Grid {config.symbol} - Capital: {config.capital_total:.0f}€"
          f" - {config.num_levels} niveaux")
    print("=" * 65)
    print(f"  Current Price: {current_price:.2f} EUR")
    print(f"  Range: {lower_price:.2f} - {upper_price:.2f} EUR"
          f" (+/- {config.half_range_percent:.0f}%)")
    print(f"  Capital/niveau: {config.capital_per_level:.2f}€")
    print(f"  Profit objectif/niveau: {config.profit_per_level}%")
    print("-" * 65)

    for level in levels:
        print(f"  {level}")

    print("-" * 65)

    total_buy = sum(
        lv.capital_allocated for lv in levels if lv.level_type == "BUY"
    )
    total_sell = sum(
        lv.capital_allocated for lv in levels if lv.level_type == "SELL"
    )
    total_btc = sum(lv.btc_quantity for lv in levels)
    buy_count = sum(1 for lv in levels if lv.level_type == "BUY")
    sell_count = sum(1 for lv in levels if lv.level_type == "SELL")

    print(f"  BUY  levels: {buy_count} | Capital: {total_buy:.2f}€")
    print(f"  SELL levels: {sell_count} | Capital: {total_sell:.2f}€")
    print(f"  Total BTC:  {total_btc:.8f}")
    print(f"  Total EUR:  {total_buy + total_sell:.2f}€")
    print("=" * 65)


def main() -> None:
    """Point d'entrée principal: récupère le prix et calcule la grille."""
    config = GridConfig()

    print(f"[{datetime.now().isoformat()}] Récupération prix"
          f" {config.symbol} sur Kraken...")

    try:
        current_price = get_price(config.symbol)
        print(f"[PRICE] {config.symbol}: {current_price:.2f} EUR\n")
    except RuntimeError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    levels = calculate_grid_levels(current_price, config)

    display_grid(levels, current_price, config)

    print(f"\n[STATUS] Grid calculé avec succès - {len(levels)} niveaux")


if __name__ == "__main__":
    main()
