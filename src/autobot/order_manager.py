"""
Order Manager - Gestion des ordres sur Kraken
"""

import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum

try:
    import krakenex
    from krakenex import API
except ImportError:
    krakenex = None

from .error_handler import ErrorHandler

logger = logging.getLogger(__name__)

# Constantes de sécurité
MAX_ORDER_VALUE_EUR = 100.0  # Limite max par ordre
MAX_VOLUME_BTC = 0.01  # Limite max en BTC
REQUEST_TIMEOUT = 30  # Timeout API en secondes


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


class OrderManager:
    """
    Gère les ordres sur Kraken.
    
    Features:
    - Placement d'ordres LIMIT (buy/sell)
    - Annulation d'ordres
    - Récupération du statut des ordres
    - Gestion des erreurs avec retry
    - Limites de sécurité (montant max, timeout)
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        sandbox: bool = True,
        max_order_value: float = MAX_ORDER_VALUE_EUR,
        max_volume: float = MAX_VOLUME_BTC
    ):
        """
        Initialise le gestionnaire d'ordres.
        
        Args:
            api_key: Clé API Kraken
            api_secret: Secret API Kraken
            sandbox: Mode sandbox (pas d'ordres réels)
            max_order_value: Valeur max par ordre en EUR
            max_volume: Volume max par ordre
        """
        self.api_key = api_key
        # Ne stocke pas le secret en clair, passe-le directement au client
        self.sandbox = sandbox
        self.max_order_value = max_order_value
        self.max_volume = max_volume
        self.error_handler = ErrorHandler()
        
        # Initialisation du client Kraken avec timeout
        self._client = None
        if krakenex and api_key and api_secret:
            self._client = krakenex.API(key=api_key, secret=api_secret)
            # Configure le timeout si l'API le supporte
            try:
                self._client.conn.timeout = REQUEST_TIMEOUT
            except AttributeError:
                pass  # Version ancienne de krakenex
        
        # Cache des ordres actifs
        self._active_orders: Dict[str, Order] = {}
        
        logger.info(f"📊 OrderManager initialisé (sandbox={sandbox}, max_value={max_order_value}€)")
    
    def _get_client(self):
        """Retourne le client API Kraken"""
        if self._client is None:
            raise RuntimeError("Client Kraken non initialisé - vérifiez les clés API")
        return self._client
    
    def _check_balance(self, side: OrderSide, price: float, volume: float, symbol: str) -> bool:
        """
        Vérifie que le solde est suffisant pour l'ordre.
        
        Args:
            side: BUY ou SELL
            price: Prix de l'ordre
            volume: Volume
            symbol: Paire de trading
            
        Returns:
            True si solde suffisant
            
        Raises:
            RuntimeError: Si solde insuffisant
        """
        if self.sandbox:
            return True  # Pas de vérification en sandbox
        
        def _query_balance():
            client = self._get_client()
            result = client.query_private('Balance')
            
            if result.get('error'):
                raise RuntimeError(f"Erreur Kraken Balance: {result['error']}")
            
            return result.get('result', {})
        
        try:
            balances = self.error_handler.execute_with_retry(_query_balance)
            
            if side == OrderSide.BUY:
                # Pour un BUY, vérifie le solde en EUR (ou devise de quote)
                # XXBTZEUR -> EUR, XXBTZUSD -> USD
                quote_currency = "ZEUR"  # Par défaut EUR
                if "USD" in symbol:
                    quote_currency = "ZUSD"
                
                required = price * volume
                available = float(balances.get(quote_currency, 0))
                
                if available < required:
                    raise RuntimeError(
                        f"Solde insuffisant pour BUY: {available:.2f} < {required:.2f} {quote_currency}"
                    )
                
                logger.debug(f"✅ Solde OK: {available:.2f} {quote_currency} >= {required:.2f}")
                
            else:  # SELL
                # Pour un SELL, vérifie le solde en crypto (base currency)
                # XXBTZEUR -> XXBT (BTC)
                base_currency = symbol[:4] if len(symbol) >= 4 else symbol
                if base_currency not in balances and "XXBT" in symbol:
                    base_currency = "XXBT"
                elif base_currency not in balances and "XETH" in symbol:
                    base_currency = "XETH"
                
                required = volume
                available = float(balances.get(base_currency, 0))
                
                if available < required:
                    raise RuntimeError(
                        f"Solde insuffisant pour SELL: {available:.6f} < {required:.6f} {base_currency}"
                    )
                
                logger.debug(f"✅ Solde OK: {available:.6f} {base_currency} >= {required:.6f}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Erreur vérification solde: {e}")
            raise
    
    def _validate_order(self, symbol: str, price: float, volume: float) -> None:
        """
        Valide les paramètres d'un ordre avant placement.
        
        Raises:
            ValueError: Si un paramètre est invalide
        """
        if not symbol or not isinstance(symbol, str):
            raise ValueError(f"Symbole invalide: {symbol}")
        
        if price <= 0:
            raise ValueError(f"Prix invalide: {price}")
        
        if volume <= 0:
            raise ValueError(f"Volume invalide: {volume}")
        
        # Vérification limite volume
        if volume > self.max_volume:
            raise ValueError(f"Volume {volume} dépasse la limite max ({self.max_volume})")
        
        # Vérification limite valeur
        order_value = price * volume
        if order_value > self.max_order_value:
            raise ValueError(
                f"Valeur ordre {order_value:.2f}€ dépasse la limite max ({self.max_order_value}€)"
            )
    
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
        # Validation complète avant placement
        self._validate_order(symbol, price, volume)
        
        # Vérification du solde (nouveau)
        self._check_balance(side, price, volume, symbol)
        
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
    
    def get_order_status(self, order_id: str, force_refresh: bool = False) -> Optional[Order]:
        """
        Récupère le statut d'un ordre.
        
        CORRECTION CRITIQUE: Force toujours la vérification via API si 
        l'ordre n'est pas fermé (closed/canceled).
        
        Args:
            order_id: ID de l'ordre
            force_refresh: Force le rafraîchissement depuis l'API
            
        Returns:
            Ordre avec statut à jour, ou None si non trouvé
        """
        # Si en sandbox et ordre pas dans le cache, retourne None
        if self.sandbox and order_id not in self._active_orders:
            return None
        
        # Si l'ordre est dans le cache et fermé, retourne le cache
        if (order_id in self._active_orders and 
            self._active_orders[order_id].status in ("closed", "canceled", "error") and 
            not force_refresh):
            return self._active_orders[order_id]
        
        # Sinon, vérifie toujours via l'API
        if self.sandbox:
            # En sandbox, simule la mise à jour
            if order_id in self._active_orders:
                return self._active_orders[order_id]
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
                # Met à jour l'ordre existant ou crée un nouveau
                if order_id in self._active_orders:
                    order = self._active_orders[order_id]
                    order.status = info.get('status', order.status)
                    order.filled_volume = float(info.get('vol_exec', order.filled_volume))
                else:
                    order = Order(
                        id=order_id,
                        status=info.get('status', 'unknown'),
                        filled_volume=float(info.get('vol_exec', 0))
                    )
                    self._active_orders[order_id] = order
                return order
        except Exception as e:
            logger.error(f"❌ Erreur récupération statut ordre {order_id}: {e}")
            # En cas d'erreur, retourne le cache si disponible
            if order_id in self._active_orders:
                return self._active_orders[order_id]
        
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
    
    def cleanup_closed_orders(self, max_age_hours: int = 24) -> int:
        """
        Nettoie les ordres fermés du cache pour éviter la fuite mémoire.
        
        Args:
            max_age_hours: Âge max avant suppression (non implémenté - supprime tout)
            
        Returns:
            Nombre d'ordres nettoyés
        """
        closed_statuses = ("closed", "canceled", "error")
        to_remove = [
            order_id for order_id, order in self._active_orders.items()
            if order.status in closed_statuses
        ]
        
        for order_id in to_remove:
            del self._active_orders[order_id]
        
        if to_remove:
            logger.info(f"🧹 {len(to_remove)} ordres fermés nettoyés du cache")
        
        return len(to_remove)
