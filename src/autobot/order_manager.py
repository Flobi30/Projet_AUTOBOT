"""
Order Manager - Gestion des ordres sur Kraken
"""

import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum

try:
    import krakenex
    from krakenex import API
except ImportError:
    krakenex = None

from .error_handler import ErrorHandler

logger = logging.getLogger(__name__)


class OrderSide(Enum):
    """Côté de l'ordre (achat ou vente)"""
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    """Type d'ordre"""
    LIMIT = "limit"
    MARKET = "market"


@dataclass
class Order:
    """Représentation d'un ordre"""
    id: Optional[str] = None
    symbol: str = ""
    side: OrderSide = OrderSide.BUY
    order_type: OrderType = OrderType.LIMIT
    price: float = 0.0
    volume: float = 0.0
    status: str = "pending"  # pending, open, closed, canceled
    created_at: Optional[str] = None
    filled_volume: float = 0.0
    
    def is_filled(self) -> bool:
        """Vérifie si l'ordre est complètement exécuté"""
        return self.status == "closed" and self.filled_volume >= self.volume
    
    def is_buy(self) -> bool:
        """Vérifie si c'est un ordre d'achat"""
        return self.side == OrderSide.BUY
    
    def is_sell(self) -> bool:
        """Vérifie si c'est un ordre de vente"""
        return self.side == OrderSide.SELL
    
    def is_filled(self) -> bool:
        """Vérifie si l'ordre est complètement exécuté"""
        return self.status == "closed" and self.filled_volume >= self.volume


class OrderManager:
    """
    Gère les ordres sur Kraken.
    
    Features:
    - Placement d'ordres LIMIT (buy/sell)
    - Annulation d'ordres
    - Récupération du statut des ordres
    - Gestion des erreurs avec retry
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        sandbox: bool = True
    ):
        """
        Initialise le gestionnaire d'ordres.
        
        Args:
            api_key: Clé API Kraken
            api_secret: Secret API Kraken
            sandbox: Mode sandbox (pas d'ordres réels)
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.sandbox = sandbox
        self.error_handler = ErrorHandler()
        
        # Initialisation du client Kraken
        self._client = None
        if krakenex and api_key and api_secret:
            self._client = krakenex.API(key=api_key, secret=api_secret)
        
        # Cache des ordres actifs
        self._active_orders: Dict[str, Order] = {}
        
        logger.info(f"📊 OrderManager initialisé (sandbox={sandbox})")
    
    def _get_client(self):
        """Retourne le client API Kraken"""
        if self._client is None:
            raise RuntimeError("Client Kraken non initialisé - vérifiez les clés API")
        return self._client
    
    def place_buy_order(
        self,
        symbol: str,
        price: float,
        volume: float
    ) -> Order:
        """
        Place un ordre d'achat LIMIT.
        
        Args:
            symbol: Paire de trading (ex: XXBTZEUR)
            price: Prix limite
            volume: Volume à acheter
            
        Returns:
            Ordre créé
        """
        return self._place_order(
            symbol=symbol,
            side=OrderSide.BUY,
            price=price,
            volume=volume
        )
    
    def place_sell_order(
        self,
        symbol: str,
        price: float,
        volume: float
    ) -> Order:
        """
        Place un ordre de vente LIMIT.
        
        Args:
            symbol: Paire de trading (ex: XXBTZEUR)
            price: Prix limite
            volume: Volume à vendre
            
        Returns:
            Ordre créé
        """
        return self._place_order(
            symbol=symbol,
            side=OrderSide.SELL,
            price=price,
            volume=volume
        )
    
    def _place_order(
        self,
        symbol: str,
        side: OrderSide,
        price: float,
        volume: float
    ) -> Order:
        """
        Place un ordre (interne).
        
        Args:
            symbol: Paire de trading
            side: BUY ou SELL
            price: Prix limite
            volume: Volume
            
        Returns:
            Ordre créé
        """
        if price <= 0:
            raise ValueError(f"Prix invalide: {price}")
        if volume <= 0:
            raise ValueError(f"Volume invalide: {volume}")
        
        order = Order(
            symbol=symbol,
            side=side,
            order_type=OrderType.LIMIT,
            price=price,
            volume=volume,
            status="pending"
        )
        
        if self.sandbox:
            # Mode simulation - pas d'appel API réel
            order.id = f"sandbox_{side.value}_{hash(str(price)) % 1000000}"
            order.status = "open"
            logger.info(f"🧪 [SANDBOX] Ordre {side.value} créé: {volume} @ €{price:,.2f}")
        else:
            # Mode production - appel API Kraken
            def _create_order():
                client = self._get_client()
                result = client.query_private(
                    'AddOrder',
                    {
                        'pair': symbol,
                        'type': side.value,
                        'ordertype': 'limit',
                        'price': str(price),
                        'volume': str(volume)
                    }
                )
                
                if result.get('error'):
                    raise RuntimeError(f"Erreur Kraken: {result['error']}")
                
                txid = result['result']['txid'][0]
                return txid
            
            try:
                txid = self.error_handler.execute_with_retry(_create_order)
                order.id = txid
                order.status = "open"
                logger.info(f"✅ Ordre {side.value} placé: {volume} @ €{price:,.2f} (ID: {txid})")
            except Exception as e:
                logger.error(f"❌ Échec placement ordre: {e}")
                order.status = "error"
                raise
        
        self._active_orders[order.id] = order
        return order
    
    def cancel_order(self, order_id: str) -> bool:
        """
        Annule un ordre actif.
        
        Args:
            order_id: ID de l'ordre à annuler
            
        Returns:
            True si annulé avec succès
        """
        if order_id not in self._active_orders:
            logger.warning(f"⚠️ Ordre {order_id} non trouvé")
            return False
        
        if self.sandbox:
            logger.info(f"🧪 [SANDBOX] Ordre {order_id} annulé")
            self._active_orders[order_id].status = "canceled"
            return True
        
        def _do_cancel():
            client = self._get_client()
            result = client.query_private('CancelOrder', {'txid': order_id})
            
            if result.get('error'):
                raise RuntimeError(f"Erreur Kraken: {result['error']}")
            
            return result.get('result', {}).get('count', 0) > 0
        
        try:
            success = self.error_handler.execute_with_retry(_do_cancel)
            if success:
                self._active_orders[order_id].status = "canceled"
                logger.info(f"✅ Ordre {order_id} annulé")
            return success
        except Exception as e:
            logger.error(f"❌ Échec annulation ordre {order_id}: {e}")
            return False
    
    def get_order_status(self, order_id: str) -> Optional[Order]:
        """
        Récupère le statut d'un ordre.
        
        Args:
            order_id: ID de l'ordre
            
        Returns:
            Ordre avec statut à jour, ou None si non trouvé
        """
        if order_id in self._active_orders:
            return self._active_orders[order_id]
        
        if self.sandbox:
            return None
        
        def _query_order():
            client = self._get_client()
            result = client.query_private('QueryOrders', {'txid': order_id})
            
            if result.get('error'):
                raise RuntimeError(f"Erreur Kraken: {result['error']}")
            
            order_info = result.get('result', {}).get(order_id)
            if not order_info:
                return None
            
            return order_info
        
        try:
            info = self.error_handler.execute_with_retry(_query_order)
            if info:
                # Met à jour ou crée l'ordre
                order = Order(
                    id=order_id,
                    status=info.get('status', 'unknown'),
                    filled_volume=float(info.get('vol_exec', 0))
                )
                self._active_orders[order_id] = order
                return order
        except Exception as e:
            logger.error(f"❌ Erreur récupération statut ordre {order_id}: {e}")
        
        return None
    
    def get_active_orders(self) -> List[Order]:
        """
        Retourne tous les ordres actifs.
        
        Returns:
            Liste des ordres actifs
        """
        return [
            order for order in self._active_orders.values()
            if order.status in ("pending", "open")
        ]
    
    def cancel_all_orders(self) -> int:
        """
        Annule tous les ordres actifs.
        
        Returns:
            Nombre d'ordres annulés
        """
        active = self.get_active_orders()
        count = 0
        
        for order in active:
            if self.cancel_order(order.id):
                count += 1
        
        logger.info(f"🗑️ {count}/{len(active)} ordres annulés")
        return count
