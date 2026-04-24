"""
Order Flow Imbalance (OFI) — Détecte la pression du carnet d'ordres.
Module Performance Ultra P1.
"""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class OrderFlowImbalance:
    """
    Calcule l'Order Flow Imbalance (OFI) en temps réel.
    L'OFI mesure le déséquilibre entre la pression acheteuse et vendeuse
    en analysant les changements de volume aux meilleurs prix bid/ask.
    """

    def __init__(self, depth: int = 10) -> None:
        self._depth = depth
        # État du carnet {symbol: {'bids': {price: vol}, 'asks': {price: vol}}}
        self._books: Dict[str, Dict[str, Dict[float, float]]] = {}
        # Valeur OFI lissée ou brute
        self._ofi_values: Dict[str, float] = {}
        # Historique pour calcul de tendance
        self._ofi_history: Dict[str, List[float]] = {}

    async def on_book_update(self, pair: str, data: dict) -> None:
        """Callback pour les mises à jour du carnet d'ordres Kraken."""
        if pair not in self._books:
            self._books[pair] = {'bids': {}, 'asks': {}}
            self._ofi_history[pair] = []

        # Kraken WS V1 : 'as' or 'bs' for snapshot, 'a' or 'b' for updates
        book = self._books[pair]
        
        # Snapshot
        if 'as' in data:
            book['asks'] = {float(row[0]): float(row[1]) for row in data['as']}
        if 'bs' in data:
            book['bids'] = {float(row[0]): float(row[1]) for row in data['bs']}
            return # OFI commence après le snapshot

        # Updates
        ofi_delta = 0.0
        
        if 'a' in data:
            old_best_ask = min(book['asks'].keys()) if book['asks'] else None
            old_best_ask_vol = book['asks'].get(old_best_ask, 0.0) if old_best_ask else 0.0
            
            # Apply updates
            for row in data['a']:
                p, v = float(row[0]), float(row[1])
                if v == 0:
                    book['asks'].pop(p, None)
                else:
                    book['asks'][p] = v
            
            new_best_ask = min(book['asks'].keys()) if book['asks'] else None
            new_best_ask_vol = book['asks'].get(new_best_ask, 0.0) if new_best_ask else 0.0
            
            # OFI logic for asks
            if new_best_ask and old_best_ask:
                if new_best_ask > old_best_ask:
                    ofi_delta -= 0 # Price moved up, ask pressure decreased? No, old best ask is gone.
                elif new_best_ask < old_best_ask:
                    ofi_delta += new_best_ask_vol # New lower ask, increased sell pressure
                else:
                    ofi_delta += (new_best_ask_vol - old_best_ask_vol) # Same price, volume change
        
        if 'b' in data:
            old_best_bid = max(book['bids'].keys()) if book['bids'] else None
            old_best_bid_vol = book['bids'].get(old_best_bid, 0.0) if old_best_bid else 0.0
            
            for row in data['b']:
                p, v = float(row[0]), float(row[1])
                if v == 0:
                    book['bids'].pop(p, None)
                else:
                    book['bids'][p] = v
            
            new_best_bid = max(book['bids'].keys()) if book['bids'] else None
            new_best_bid_vol = book['bids'].get(new_best_bid, 0.0) if new_best_bid else 0.0
            
            # OFI logic for bids
            if new_best_bid and old_best_bid:
                if new_best_bid > old_best_bid:
                    ofi_delta += new_best_bid_vol # New higher bid, increased buy pressure
                elif new_best_bid < old_best_bid:
                    ofi_delta -= 0 # Price moved down, old best bid is gone
                else:
                    ofi_delta += (new_best_bid_vol - old_best_bid_vol) # Same price, volume change

        # Update OFI for pair
        current_ofi = self._ofi_values.get(pair, 0.0) + ofi_delta
        self._ofi_values[pair] = current_ofi
        
        # Keep history
        self._ofi_history[pair].append(ofi_delta)
        if len(self._ofi_history[pair]) > 100:
            self._ofi_history[pair].pop(0)

    def get_ofi_score(self, pair: str) -> float:
        """
        Retourne un score d'imbalance entre -1 (forte pression vente) 
        et 1 (forte pression achat).
        """
        history = self._ofi_history.get(pair, [])
        if not history:
            return 0.0
        
        # Somme des deltas récents
        recent_sum = sum(history[-20:])
        # Normalisation simple (à affiner selon la volatilité du volume)
        return max(-1.0, min(1.0, recent_sum / 10.0))

    def is_unbalanced_against(self, pair: str, side: str) -> bool:
        """
        Vérifie si le carnet est fortement déséquilibré contre nous.
        side: 'buy' ou 'sell'
        """
        score = self.get_ofi_score(pair)
        if side == 'buy' and score < -0.6: # On veut acheter mais forte pression vendeuse
            return True
        if side == 'sell' and score > 0.6: # On veut vendre mais forte pression acheteuse
            return True
        return False
