"""
OrderExecutor - Exécution réelle des ordres sur Kraken

CORRECTION CRITIQUE : Ce module remplace l'exécution "simulation" par de vrais appels API Kraken.
"""

import logging
import time
from typing import Callable, Optional, Dict, Any, Tuple
from dataclasses import dataclass
from enum import Enum
import threading

logger = logging.getLogger(__name__)

try:
    import krakenex  # type: ignore
except Exception:  # pragma: no cover - optional in some test environments
    krakenex = None


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP_LOSS = "stop-loss"


@dataclass
class OrderResult:
    """Résultat d'exécution d'ordre"""
    success: bool
    txid: Optional[str] = None
    executed_volume: float = 0.0
    executed_price: float = 0.0
    fees: float = 0.0
    error: Optional[str] = None
    raw_response: Optional[Dict] = None

    @property
    def total_cost(self) -> float:
        return (self.executed_price * self.executed_volume) + self.fees


@dataclass
class OrderStatus:
    """Statut d'un ordre existant"""
    txid: str
    status: str  # "open", "closed", "canceled", "expired"
    volume: float
    volume_exec: float
    price: Optional[float] = None
    avg_price: Optional[float] = None
    fee: float = 0.0


class OrderExecutor:
    """
    Exécuteur d'ordres Kraken avec gestion complète du cycle de vie.
    
    Responsabilités:
    - Exécuter ordres via API Kraken (réel, pas simulation)
    - Attendre confirmation et prix d'exécution
    - Gérer ordres partiellement remplis
    - Rate limiting avec backoff exponentiel
    - Logging sécurisé (clés API masquées)
    """
    
    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None, use_queue: bool = False):
        self.api_key = api_key
        self.api_secret = api_secret
        self._lock = threading.RLock()

        # Rate limiting
        self._last_call_time = 0
        self._min_interval = 1.0  # 1 seconde min entre appels

        # Cache Kraken client
        self._client = None

        # CORRECTION E6: Circuit breaker pour erreurs API
        self._consecutive_errors = 0
        self._max_consecutive_errors = 10  # Seuil avant circuit breaker
        self._circuit_breaker_callback: Optional[Callable] = None  # Callback à déclencher
        
        # OPTIMISATION: File d'attente globale pour ordres
        self._order_queue = None
        if use_queue:
            from .order_queue import get_order_queue
            self._order_queue = get_order_queue(self, max_rate=1.0)
            self._order_queue.start()
            logger.info("📡 OrderExecutor initialisé (avec OrderQueue)")
        else:
            logger.info("📡 OrderExecutor initialisé (mode direct)")

    def set_circuit_breaker_callback(self, callback: Callable):
        """
        Définit la callback à appeler si le circuit breaker se déclenche.
        La callback devrait typiquement appeler emergency_stop().
        """
        self._circuit_breaker_callback = callback

    def _reset_error_count(self):
        """Reset le compteur d'erreurs (appelé après un succès)."""
        with self._lock:
            if self._consecutive_errors > 0:
                logger.info(f"✅ Reset compteur erreurs (était à {self._consecutive_errors})")
                self._consecutive_errors = 0

    def _increment_error_count(self) -> bool:
        """
        Incrémente le compteur d'erreurs et vérifie si circuit breaker doit se déclencher.

        Returns:
            True si circuit breaker déclenché
        """
        with self._lock:
            self._consecutive_errors += 1
            current = self._consecutive_errors

            if current >= self._max_consecutive_errors:
                logger.error(f"🚨 CIRCUIT BREAKER DÉCLENCHÉ: {current} erreurs consécutives!")
                if self._circuit_breaker_callback:
                    try:
                        self._circuit_breaker_callback()
                    except Exception as e:
                        logger.exception(f"❌ Erreur circuit breaker callback: {e}")
                return True

            logger.warning(f"⚠️ Erreur API consécutive #{current}/{self._max_consecutive_errors}")
            return False
    
    def _get_client(self):
        """Retourne client Krakenex (lazy init)"""
        if self._client is None:
            if not self.api_key or not self.api_secret:
                raise ValueError("Clés API Kraken non configurées")
            if krakenex is None:
                raise RuntimeError("krakenex n'est pas disponible")
            self._client = krakenex.API(key=self.api_key, secret=self.api_secret)
            self._client.session.timeout = 30
        return self._client
    
    def _rate_limit(self):
        """Attend si nécessaire pour respecter rate limiting"""
        with self._lock:
            elapsed = time.time() - self._last_call_time
            if elapsed < self._min_interval:
                time.sleep(self._min_interval - elapsed)
            self._last_call_time = time.time()
    
    def _safe_api_call(self, method: str, max_retries: int = 3, **params) -> Tuple[bool, Dict]:
        """
        Appel API avec retry et backoff exponentiel.

        CORRECTION E2: Ajoute ClosedOrders, Balance, TradeBalance, Ticker à la whitelist.

        Returns:
            (success, response)
        """
        for attempt in range(max_retries):
            try:
                self._rate_limit()
                k = self._get_client()

                # CORRECTION E2: Whitelist complète des méthodes supportées
                if method == 'AddOrder':
                    response = k.query_private('AddOrder', params)
                elif method == 'CancelOrder':
                    response = k.query_private('CancelOrder', params)
                elif method == 'QueryOrders':
                    response = k.query_private('QueryOrders', params)
                elif method == 'OpenOrders':
                    response = k.query_private('OpenOrders', params)
                elif method == 'ClosedOrders':
                    response = k.query_private('ClosedOrders', params)
                elif method == 'Balance':
                    response = k.query_private('Balance', params)
                elif method == 'TradeBalance':
                    response = k.query_private('TradeBalance', params)
                elif method == 'Ticker':
                    response = k.query_public('Ticker', params)
                else:
                    return False, {'error': f'Méthode inconnue: {method}'}
                
                # Vérifier erreurs
                if 'error' in response and response['error']:
                    error_msg = str(response['error'])
                    
                    # Rate limit → backoff
                    if 'Rate limit exceeded' in error_msg:
                        wait_time = 2 ** attempt
                        logger.warning(f"⏳ Rate limit, attente {wait_time}s...")
                        time.sleep(wait_time)
                        continue
                    
                    # Autre erreur → retry
                    logger.error(f"❌ Erreur API Kraken: {error_msg}")
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
                        continue
                    # CORRECTION E6: Circuit breaker - incrémente erreur après tous les retries échoués
                    self._increment_error_count()
                    return False, response

                # CORRECTION E6: Succès - reset compteur erreurs
                self._reset_error_count()
                return True, response

            except Exception as e:
                logger.error(f"❌ Exception API Kraken: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                # CORRECTION E6: Circuit breaker - incrémente erreur après tous les retries échoués
                self._increment_error_count()
                return False, {'error': str(e)}

        # CORRECTION E6: Circuit breaker - incrémente erreur si on arrive ici (max retries exceeded)
        self._increment_error_count()
        return False, {'error': 'Max retries exceeded'}
    
    def execute_market_order(
        self,
        symbol: str,
        side: OrderSide,
        volume: float,
        userref: Optional[int] = None
    ) -> OrderResult:
        """
        Exécute un ordre MARKET (exécution immédiate au prix du marché).
        
        Args:
            symbol: Paire Kraken (ex: XXBTZEUR)
            side: BUY ou SELL
            volume: Volume en BTC (ou unité base)
            userref: ID utilisateur pour tracking (optional)
            
        Returns:
            OrderResult avec prix d'exécution réel
        """
        logger.info(f"📤 Ordre MARKET {side.value.upper()} {volume:.6f} {symbol}")

        # CORRECTION F6: Validation volume minimum Kraken
        MIN_VOLUME_KRAKEN = 0.0001  # 0.0001 BTC minimum
        if volume < MIN_VOLUME_KRAKEN:
            error_msg = f"Volume {volume:.6f} inférieur au minimum Kraken ({MIN_VOLUME_KRAKEN})"
            logger.error(f"❌ {error_msg}")
            return OrderResult(success=False, error=error_msg)

        # Validation
        if volume <= 0:
            return OrderResult(success=False, error="Volume doit être > 0")
        
        # Paramètres ordre
        order_params = {
            'pair': symbol,
            'type': side.value,
            'ordertype': 'market',
            'volume': str(volume),
        }
        if userref:
            order_params['userref'] = str(userref)
        
        # Exécution
        success, response = self._safe_api_call('AddOrder', **order_params)
        
        if not success:
            error_msg = response.get('error', ['Unknown'])[0] if isinstance(response.get('error'), list) else str(response.get('error', 'Unknown'))
            logger.error(f"❌ Échec ordre MARKET: {error_msg}")
            return OrderResult(success=False, error=error_msg)
        
        # Récupération txid
        txid = None
        if 'result' in response and 'txid' in response['result']:
            txid = response['result']['txid'][0]
            logger.info(f"✅ Ordre accepté, txid: {txid[:8]}...")
        else:
            return OrderResult(success=False, error="Pas de txid dans réponse")
        
        # Attente exécution et récupération prix réel
        return self._wait_for_execution(txid, max_wait=60)
    
    def execute_stop_loss_order(
        self,
        symbol: str,
        side: OrderSide,
        volume: float,
        stop_price: float,
        userref: Optional[int] = None
    ) -> OrderResult:
        """
        Pose un ordre STOP-LOSS sur Kraken (déclenchement automatique).
        
        CRITIQUE : Ce stop-loss est géré par Kraken, pas par le bot.
        Si le bot crash, le stop-loss reste actif.
        
        Args:
            symbol: Paire Kraken
            side: BUY ou SELL
            volume: Volume
            stop_price: Prix de déclenchement
            userref: ID pour tracking
            
        Returns:
            OrderResult avec txid du stop-loss
        """
        logger.info(f"📤 Ordre STOP-LOSS {side.value.upper()} {volume:.6f} {symbol} @ {stop_price:.2f}")

        # CORRECTION F6: Validation volume minimum Kraken
        MIN_VOLUME_KRAKEN = 0.0001
        if volume < MIN_VOLUME_KRAKEN:
            error_msg = f"Volume {volume:.6f} inférieur au minimum Kraken ({MIN_VOLUME_KRAKEN})"
            logger.error(f"❌ {error_msg}")
            return OrderResult(success=False, error=error_msg)

        if volume <= 0:
            return OrderResult(success=False, error="Volume doit être > 0")
        
        order_params = {
            'pair': symbol,
            'type': side.value,
            'ordertype': 'stop-loss',
            'volume': str(volume),
            'price': str(stop_price),  # Prix stop
        }
        if userref:
            order_params['userref'] = str(userref)
        
        success, response = self._safe_api_call('AddOrder', **order_params)
        
        if not success:
            error_msg = response.get('error', ['Unknown'])[0] if isinstance(response.get('error'), list) else str(response.get('error', 'Unknown'))
            logger.error(f"❌ Échec stop-loss: {error_msg}")
            return OrderResult(success=False, error=error_msg)
        
        txid = None
        if 'result' in response and 'txid' in response['result']:
            txid = response['result']['txid'][0]
            logger.info(f"✅ Stop-loss posé, txid: {txid[:8]}...")
            return OrderResult(success=True, txid=txid)
        
        return OrderResult(success=False, error="Pas de txid")
    
    def _wait_for_execution(self, txid: str, max_wait: int = 60) -> OrderResult:
        """
        Attend l'exécution complète d'un ordre et récupère les détails.
        
        Args:
            txid: ID de transaction Kraken
            max_wait: Temps max d'attente en secondes
            
        Returns:
            OrderResult avec prix d'exécution réel
        """
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            success, response = self._safe_api_call('QueryOrders', txid=txid)
            
            if not success:
                time.sleep(1)
                continue
            
            if 'result' not in response or txid not in response['result']:
                time.sleep(1)
                continue
            
            order_info = response['result'][txid]
            status = order_info.get('status', 'unknown')
            
            # Ordre fermé (exécuté ou annulé)
            if status == 'closed':
                volume = float(order_info.get('vol', 0))
                volume_exec = float(order_info.get('vol_exec', 0))
                avg_price = float(order_info.get('avg_price', 0)) or float(order_info.get('price', 0))
                fee = float(order_info.get('fee', 0))
                
                logger.info(f"✅ Ordre exécuté: {volume_exec:.6f} @ {avg_price:.2f}€ (frais: {fee:.4f}€)")
                
                return OrderResult(
                    success=True,
                    txid=txid,
                    executed_volume=volume_exec,
                    executed_price=avg_price,
                    fees=fee,
                    raw_response=order_info
                )
            
            # Ordre ouvert → continuer attente
            if status == 'open':
                logger.debug(f"⏳ Ordre {txid[:8]}... toujours ouvert...")
                time.sleep(2)
                continue
            
            # Ordre annulé/expiré
            if status in ('canceled', 'expired'):
                error_msg = f"Ordre {status}"
                logger.error(f"❌ {error_msg}")
                return OrderResult(success=False, txid=txid, error=error_msg)
            
            time.sleep(1)
        
        # Timeout
        logger.warning(f"⏱️ Timeout attente exécution ordre {txid[:8]}...")
        return OrderResult(success=False, txid=txid, error="Timeout exécution")
    
    def get_order_status(self, txid: str) -> Optional[OrderStatus]:
        """
        Récupère le statut d'un ordre existant.
        
        Returns:
            OrderStatus ou None si erreur
        """
        success, response = self._safe_api_call('QueryOrders', txid=txid)
        
        if not success or 'result' not in response or txid not in response['result']:
            return None
        
        info = response['result'][txid]
        
        return OrderStatus(
            txid=txid,
            status=info.get('status', 'unknown'),
            volume=float(info.get('vol', 0)),
            volume_exec=float(info.get('vol_exec', 0)),
            price=float(info.get('price', 0)) if info.get('price') else None,
            avg_price=float(info.get('avg_price', 0)) if info.get('avg_price') else None,
            fee=float(info.get('fee', 0))
        )
    
    def cancel_order(self, txid: str) -> bool:
        """
        Annule un ordre ouvert.
        
        Returns:
            True si annulé ou déjà fermé
        """
        logger.info(f"🚫 Annulation ordre {txid[:8]}...")
        
        success, response = self._safe_api_call('CancelOrder', txid=txid)
        
        if success:
            logger.info(f"✅ Ordre annulé")
            return True
        
        # Vérifier si déjà fermé (pas une erreur)
        error = response.get('error', [''])[0] if isinstance(response.get('error'), list) else str(response.get('error', ''))
        if 'Order not found' in error or 'already closed' in error:
            return True
        
        logger.error(f"❌ Échec annulation: {error}")
        return False
    
    def cancel_all_orders(self, userref: Optional[int] = None) -> bool:
        """
        Annule tous les ordres ouverts (optionnellement filtrés par userref).
        
        CORRECTION : Utilise userref pour ne pas annuler ordres manuels utilisateur.
        
        Args:
            userref: Si spécifié, annule seulement ordres avec ce userref
            
        Returns:
            True si succès
        """
        logger.info(f"🚫 Annulation tous ordres" + (f" (userref={userref})" if userref else ""))
        
        # Récupère ordres ouverts
        success, response = self._safe_api_call('OpenOrders')
        
        if not success:
            logger.error("❌ Impossible de récupérer ordres ouverts")
            return False
        
        if 'result' not in response or 'open' not in response['result']:
            return True  # Pas d'ordres ouverts
        
        open_orders = response['result']['open']
        cancelled = 0
        
        for txid, order_info in open_orders.items():
            # Filtre userref si spécifié
            if userref is not None:
                order_userref = order_info.get('userref')
                if order_userref != userref:
                    continue
            
            if self.cancel_order(txid):
                cancelled += 1
        
        logger.info(f"✅ {cancelled} ordre(s) annulé(s)")
        return True
    
    # =========================================================================
    # PHASE 3: Méthodes pour réconciliation
    # =========================================================================
    
    def get_closed_orders(
        self,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        symbol: Optional[str] = None
    ) -> Dict[str, Dict]:
        """
        Récupère les ordres fermés sur Kraken.
        
        Args:
            start_time: Timestamp Unix de début (optionnel)
            end_time: Timestamp Unix de fin (optionnel)
            symbol: Filtrer par paire (optionnel)
            
        Returns:
            Dict {txid: order_info}
        """
        params = {}
        if start_time:
            params['start'] = start_time
        if end_time:
            params['end'] = end_time
        
        success, response = self._safe_api_call('ClosedOrders', **params)
        
        if not success or 'result' not in response or 'closed' not in response['result']:
            return {}
        
        closed_orders = response['result']['closed']
        
        # Filtrer par symbole si spécifié
        if symbol:
            symbol_clean = symbol.replace('/', '')
            closed_orders = {
                txid: info for txid, info in closed_orders.items()
                if info.get('descr', {}).get('pair', '').replace('/', '') == symbol_clean
            }
        
        return closed_orders
    
    def get_balance(self) -> Dict[str, float]:
        """
        Récupère le solde complet du compte Kraken.
        
        Returns:
            Dict {asset: balance}
        """
        success, response = self._safe_api_call('Balance')
        
        if not success or 'result' not in response:
            return {}
        
        balances = {}
        for asset, amount in response['result'].items():
            try:
                balances[asset] = float(amount)
            except (ValueError, TypeError):
                continue
        
        return balances
    
    def get_trade_balance(self, asset: str = 'EUR') -> Dict[str, float]:
        """
        Récupère les informations de balance de trading.
        
        Args:
            asset: Devise de référence (EUR, USD, etc.)
            
        Returns:
            Dict avec 'equivalent_balance', 'trade_balance', etc.
        """
        params = {'asset': asset}
        success, response = self._safe_api_call('TradeBalance', **params)
        
        if not success or 'result' not in response:
            return {}
        
        result = {}
        for key, value in response['result'].items():
            try:
                result[key] = float(value)
            except (ValueError, TypeError):
                result[key] = value
        
        return result


# Singleton
_executor_instance: Optional[OrderExecutor] = None
_executor_lock = threading.Lock()


def get_order_executor(api_key: Optional[str] = None, api_secret: Optional[str] = None, use_queue: bool = False) -> OrderExecutor:
    """
    Retourne l'exécuteur d'ordres (singleton)
    
    Args:
        api_key: Clé API Kraken
        api_secret: Secret API Kraken  
        use_queue: Si True, utilise OrderQueue pour sérialiser les ordres
    """
    global _executor_instance
    
    with _executor_lock:
        if _executor_instance is None:
            _executor_instance = OrderExecutor(api_key, api_secret, use_queue=use_queue)
        return _executor_instance


def reset_order_executor():
    """Reset le singleton (pour tests)"""
    global _executor_instance
    _executor_instance = None
