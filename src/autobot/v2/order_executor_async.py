"""
OrderExecutor — Full Async (aiohttp)
MIGRATION P0: Replaces order_executor.py (threading + requests/krakenex)

Uses:
- aiohttp.ClientSession instead of krakenex (requests)
- asyncio.Lock instead of threading.RLock
- asyncio.sleep instead of time.sleep
- Kraken REST API v0 direct calls with HMAC-SHA512 signing

Public API is identical to OrderExecutor (with async/await).
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import time
import urllib.parse
from typing import Any, Callable, Coroutine, Dict, Optional, Tuple

import aiohttp

from .order_executor import OrderResult, OrderSide, OrderStatus, OrderType
from .nonce_manager import NonceManager

logger = logging.getLogger(__name__)

# Re-export for consumers
__all__ = [
    "OrderExecutorAsync",
    "OrderResult",
    "OrderSide",
    "OrderStatus",
    "OrderType",
    "get_order_executor_async",
    "reset_order_executor_async",
]


def _kraken_signature(urlpath: str, data: dict, secret: str) -> str:
    """Compute Kraken API signature (HMAC-SHA512)."""
    postdata = urllib.parse.urlencode(data)
    encoded = (str(data["nonce"]) + postdata).encode("utf-8")
    message = urlpath.encode("utf-8") + hashlib.sha256(encoded).digest()
    mac = hmac.new(base64.b64decode(secret), message, hashlib.sha512)
    return base64.b64encode(mac.digest()).decode("utf-8")


def _build_error_response(
    code: str,
    message: str,
    *,
    http_status: Optional[int] = None,
) -> dict:
    """Standardized internal error payload for coherent error mapping."""
    payload: Dict[str, Any] = {
        "error": [f"{code}:{message}"],
        "error_code": code,
    }
    if http_status is not None:
        payload["http_status"] = http_status
    return payload


def _truncate_payload(value: str, max_len: int = 300) -> str:
    return value if len(value) <= max_len else value[:max_len] + "..."


class OrderExecutorAsync:
    """
    Async order executor using aiohttp + Kraken REST API v0.

    Drop-in async replacement for OrderExecutor.
    """

    def __repr__(self) -> str:
        key_hint = self._api_key[:6] + "..." if self._api_key else "None"
        return f"OrderExecutorAsync(api_key={key_hint!r})"

    KRAKEN_API_URL = "https://api.kraken.com"

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        nonce_manager: Optional[NonceManager] = None,
    ) -> None:
        # SEC-03: clés privées, fallback sur variables d'env
        import os as _os
        self._api_key: Optional[str] = api_key or _os.getenv("KRAKEN_API_KEY")
        self._api_secret: Optional[str] = api_secret or _os.getenv("KRAKEN_API_SECRET")
        self._lock = asyncio.Lock()
        self._session: Optional[aiohttp.ClientSession] = None

        # Centralized nonce manager (cross-worker/process monotonicity)
        self._nonce_manager: NonceManager = nonce_manager or NonceManager()
        self._nonce_cache_lock = asyncio.Lock()
        self._nonce_block_size: int = 64
        self._nonce_next: Optional[int] = None
        self._nonce_high: Optional[int] = None

        # Rate limiting
        self._last_call_time: float = 0
        self._min_interval: float = 1.0

        # Circuit breaker
        self._consecutive_errors: int = 0
        self._max_consecutive_errors: int = 10
        self._invalid_nonce_errors: int = 0
        self._max_invalid_nonce_errors: int = 3
        self._circuit_breaker_callback: Optional[
            Callable[[], Coroutine[Any, Any, None]]
        ] = None

        logger.info("📡 OrderExecutorAsync initialisé")

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    async def _get_session(self) -> aiohttp.ClientSession:
        """Lazy-init aiohttp session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        """Close underlying HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    # ------------------------------------------------------------------
    # Low-level Kraken API
    # ------------------------------------------------------------------

    async def _query_public(self, method: str, **params: Any) -> dict:
        """Call Kraken public API endpoint."""
        url = f"{self.KRAKEN_API_URL}/0/public/{method}"
        session = await self._get_session()
        async with session.post(url, data=params) as resp:
            return await self._parse_kraken_http_response(resp, method=method, is_private=False)

    async def _query_private(self, method: str, **params: Any) -> dict:
        """Call Kraken private API endpoint with HMAC signing."""
        if not self._api_key or not self._api_secret:
            raise ValueError("Clés API Kraken non configurées")

        urlpath = f"/0/private/{method}"
        url = f"{self.KRAKEN_API_URL}{urlpath}"

        # Centralized monotonic nonce generation per API key fingerprint
        api_key_id = hashlib.sha256((self._api_key or "none").encode("utf-8")).hexdigest()[:16]
        nonce = await self._next_nonce(api_key_id)
        params["nonce"] = str(int(nonce))
        sig = _kraken_signature(urlpath, params, self._api_secret)

        headers = {
            "API-Key": self._api_key,
            "API-Sign": sig,
        }

        session = await self._get_session()
        async with session.post(url, data=params, headers=headers) as resp:
            return await self._parse_kraken_http_response(resp, method=method, is_private=True)

    async def _parse_kraken_http_response(
        self,
        resp: aiohttp.ClientResponse,
        *,
        method: str,
        is_private: bool,
    ) -> dict:
        """Validate HTTP status and defensively parse JSON response body."""
        scope = "private" if is_private else "public"
        status = resp.status
        body = await resp.text()

        if status != 200:
            logger.error(
                "❌ Kraken HTTP %s %s/%s: status=%s body=%s",
                "POST",
                scope,
                method,
                status,
                _truncate_payload(body),
            )
            return _build_error_response(
                "HTTP_STATUS_ERROR",
                f"HTTP {status} sur endpoint {scope}/{method}",
                http_status=status,
            )

        if not body.strip():
            logger.error("❌ Réponse vide Kraken sur %s/%s", scope, method)
            return _build_error_response(
                "EMPTY_RESPONSE",
                f"Réponse vide sur endpoint {scope}/{method}",
                http_status=status,
            )

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            logger.error(
                "❌ JSON invalide Kraken sur %s/%s: %s",
                scope,
                method,
                _truncate_payload(body),
            )
            return _build_error_response(
                "INVALID_JSON",
                f"Réponse JSON invalide sur endpoint {scope}/{method}",
                http_status=status,
            )

        if not isinstance(payload, dict):
            logger.error(
                "❌ Format inattendu Kraken sur %s/%s (type=%s)",
                scope,
                method,
                type(payload).__name__,
            )
            return _build_error_response(
                "INVALID_RESPONSE_FORMAT",
                f"Format réponse inattendu ({type(payload).__name__}) sur endpoint {scope}/{method}",
                http_status=status,
            )

        if "error" not in payload:
            payload["error"] = []
        elif not isinstance(payload["error"], list):
            payload["error"] = [str(payload["error"])]

        return payload

    async def _next_nonce(self, api_key_id: str) -> int:
        """
        Consume a locally cached hi/lo nonce range.

        A fresh range is reserved durably in SQLite only when local cache is exhausted.
        """
        async with self._nonce_cache_lock:
            if (
                self._nonce_next is None
                or self._nonce_high is None
                or self._nonce_next > self._nonce_high
            ):
                low, high = await asyncio.to_thread(
                    self._nonce_manager.reserve_range,
                    api_key_id,
                    self._nonce_block_size,
                )
                self._nonce_next = int(low)
                self._nonce_high = int(high)

            nonce = int(self._nonce_next)
            self._nonce_next += 1
            return nonce

    # ------------------------------------------------------------------
    # Rate limiting
    # ------------------------------------------------------------------

    async def _rate_limit(self) -> None:
        async with self._lock:
            elapsed = time.monotonic() - self._last_call_time
            if elapsed < self._min_interval:
                await asyncio.sleep(self._min_interval - elapsed)
            self._last_call_time = time.monotonic()

    # ------------------------------------------------------------------
    # Circuit breaker
    # ------------------------------------------------------------------

    def set_circuit_breaker_callback(
        self,
        callback: Callable[[], Coroutine[Any, Any, None]],
    ) -> None:
        self._circuit_breaker_callback = callback

    def _reset_error_count(self) -> None:
        if self._consecutive_errors > 0:
            logger.info(
                f"✅ Reset compteur erreurs (était à {self._consecutive_errors})"
            )
            self._consecutive_errors = 0

    async def _increment_error_count(self) -> bool:
        self._consecutive_errors += 1
        current = self._consecutive_errors
        if current >= self._max_consecutive_errors:
            logger.error(
                f"🚨 CIRCUIT BREAKER: {current} erreurs consécutives!"
            )
            if self._circuit_breaker_callback:
                try:
                    await self._circuit_breaker_callback()
                except Exception as exc:
                    logger.exception(f"❌ Erreur circuit breaker callback: {exc}")
            return True
        logger.warning(
            f"⚠️ Erreur API consécutive #{current}/{self._max_consecutive_errors}"
        )
        return False

    # ------------------------------------------------------------------
    # Safe API call with retry
    # ------------------------------------------------------------------

    async def _safe_api_call(
        self, method: str, max_retries: int = 3, **params: Any
    ) -> Tuple[bool, dict]:
        """API call with retry + exponential backoff."""
        _PRIVATE = {
            "AddOrder",
            "CancelOrder",
            "QueryOrders",
            "OpenOrders",
            "ClosedOrders",
            "Balance",
            "TradeBalance",
        }
        _PUBLIC = {"Ticker"}

        for attempt in range(max_retries):
            try:
                await self._rate_limit()

                if method in _PRIVATE:
                    response = await self._query_private(method, **params)
                elif method in _PUBLIC:
                    response = await self._query_public(method, **params)
                else:
                    return False, _build_error_response(
                        "UNKNOWN_METHOD",
                        f"Méthode inconnue: {method}",
                    )

                if not isinstance(response, dict):
                    logger.error("❌ Réponse API non dict pour %s", method)
                    await self._increment_error_count()
                    return False, _build_error_response(
                        "INVALID_RESPONSE_FORMAT",
                        f"Réponse API inattendue (type={type(response).__name__}) pour {method}",
                    )

                # Check errors
                if response.get("error"):
                    error_msg = str(response["error"])
                    if "Rate limit exceeded" in error_msg:
                        wait = 2 ** attempt
                        logger.warning(f"⏳ Rate limit, attente {wait}s...")
                        await asyncio.sleep(wait)
                        continue

                    logger.error(f"❌ Erreur API Kraken: {error_msg}")
                    if "invalid nonce" in error_msg.lower():
                        self._invalid_nonce_errors += 1
                        if self._invalid_nonce_errors >= self._max_invalid_nonce_errors:
                            await self._increment_error_count()
                            if self._circuit_breaker_callback:
                                await self._circuit_breaker_callback()
                            return False, response
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    await self._increment_error_count()
                    return False, response

                self._reset_error_count()
                self._invalid_nonce_errors = 0
                return True, response

            except Exception as exc:
                logger.error(f"❌ Exception API Kraken: {exc}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                await self._increment_error_count()
                return False, {"error": str(exc)}

        await self._increment_error_count()
        return False, {"error": "Max retries exceeded"}

    # ------------------------------------------------------------------
    # Order execution
    # ------------------------------------------------------------------

    async def execute_market_order(
        self,
        symbol: str,
        side: OrderSide,
        volume: float,
        userref: Optional[int] = None,
    ) -> OrderResult:
        """Execute a MARKET order on Kraken (async)."""
        logger.info(f"📤 Ordre MARKET {side.value.upper()} {volume:.6f} {symbol}")

        MIN_VOLUME = 0.0001
        if volume < MIN_VOLUME:
            return OrderResult(
                success=False,
                error=f"Volume {volume:.6f} inférieur au minimum Kraken ({MIN_VOLUME})",
            )
        if volume <= 0:
            return OrderResult(success=False, error="Volume doit être > 0")

        order_params: Dict[str, Any] = {
            "pair": symbol,
            "type": side.value,
            "ordertype": "market",
            "volume": str(volume),
        }
        if userref:
            order_params["userref"] = str(userref)

        success, response = await self._safe_api_call("AddOrder", **order_params)
        if not success:
            error_msg = _extract_error(response)
            logger.error(f"❌ Échec ordre MARKET: {error_msg}")
            return OrderResult(success=False, error=error_msg)

        txid, txid_error = _extract_txid(response)
        if txid_error:
            return OrderResult(success=False, error=txid_error)
        assert txid is not None
        logger.info(f"✅ Ordre accepté, txid: {txid[:8]}...")

        return await self._wait_for_execution(txid, max_wait=60, fallback_liquidity="taker")

    async def execute_limit_order(
        self,
        symbol: str,
        side: OrderSide,
        volume: float,
        limit_price: float,
        post_only: bool = False,
        userref: Optional[int] = None,
    ) -> OrderResult:
        """Execute a LIMIT order on Kraken (async), optionally post-only."""
        logger.info(
            "📤 Ordre LIMIT %s %.6f %s @ %.2f post_only=%s",
            side.value.upper(),
            volume,
            symbol,
            limit_price,
            post_only,
        )

        MIN_VOLUME = 0.0001
        if volume < MIN_VOLUME:
            return OrderResult(
                success=False,
                error=f"Volume {volume:.6f} inférieur au minimum Kraken ({MIN_VOLUME})",
            )
        if volume <= 0:
            return OrderResult(success=False, error="Volume doit être > 0")
        if limit_price <= 0:
            return OrderResult(success=False, error="Prix limite doit être > 0")

        order_params: Dict[str, Any] = {
            "pair": symbol,
            "type": side.value,
            "ordertype": "limit",
            "price": str(limit_price),
            "volume": str(volume),
        }
        if post_only:
            order_params["oflags"] = "post"
        if userref:
            order_params["userref"] = str(userref)

        success, response = await self._safe_api_call("AddOrder", **order_params)
        if not success:
            error_msg = _extract_error(response)
            logger.error(f"❌ Échec ordre LIMIT: {error_msg}")
            return OrderResult(success=False, error=error_msg)

        txid, txid_error = _extract_txid(response)
        if txid_error:
            return OrderResult(success=False, error=txid_error)
        assert txid is not None
        logger.info(f"✅ Ordre LIMIT accepté, txid: {txid[:8]}...")
        return await self._wait_for_execution(
            txid,
            max_wait=60,
            fallback_liquidity="maker" if post_only else "unknown",
        )

    async def execute_stop_loss_order(
        self,
        symbol: str,
        side: OrderSide,
        volume: float,
        stop_price: float,
        userref: Optional[int] = None,
    ) -> OrderResult:
        """Place a STOP-LOSS order on Kraken (async)."""
        logger.info(
            f"📤 Ordre STOP-LOSS {side.value.upper()} {volume:.6f} {symbol} @ {stop_price:.2f}"
        )

        MIN_VOLUME = 0.0001
        if volume < MIN_VOLUME:
            return OrderResult(
                success=False,
                error=f"Volume {volume:.6f} inférieur au minimum Kraken ({MIN_VOLUME})",
            )
        if volume <= 0:
            return OrderResult(success=False, error="Volume doit être > 0")

        order_params: Dict[str, Any] = {
            "pair": symbol,
            "type": side.value,
            "ordertype": "stop-loss",
            "volume": str(volume),
            "price": str(stop_price),
        }
        if userref:
            order_params["userref"] = str(userref)

        success, response = await self._safe_api_call("AddOrder", **order_params)
        if not success:
            error_msg = _extract_error(response)
            logger.error(f"❌ Échec stop-loss: {error_msg}")
            return OrderResult(success=False, error=error_msg)

        txid, txid_error = _extract_txid(response)
        if txid_error:
            return OrderResult(success=False, error=txid_error)
        assert txid is not None
        logger.info(f"✅ Stop-loss posé, txid: {txid[:8]}...")
        return OrderResult(success=True, txid=txid)

    async def _wait_for_execution(
        self,
        txid: str,
        max_wait: int = 60,
        fallback_liquidity: str = "unknown",
    ) -> OrderResult:
        """Wait for order execution and retrieve fill details."""
        deadline = time.monotonic() + max_wait

        while time.monotonic() < deadline:
            success, response = await self._safe_api_call(
                "QueryOrders", txid=txid
            )
            if not success or "result" not in response or txid not in response["result"]:
                await asyncio.sleep(1)
                continue

            info = response["result"][txid]
            status = info.get("status", "unknown")

            if status == "closed":
                vol_exec = float(info.get("vol_exec", 0))
                avg_price = float(info.get("price", 0)) or float(
                    info.get("avg_price", 0)
                )
                fee = float(info.get("fee", 0))
                liquidity = str(info.get("liquidity") or fallback_liquidity or "unknown").lower()
                logger.info(
                    "✅ Ordre exécuté: %.6f @ %.2f€ (frais: %.4f€, liquidité: %s)",
                    vol_exec,
                    avg_price,
                    fee,
                    liquidity,
                )
                return OrderResult(
                    success=True,
                    txid=txid,
                    executed_volume=vol_exec,
                    executed_price=avg_price,
                    fees=fee,
                    liquidity=liquidity,
                    raw_response=info,
                )

            if status == "open":
                logger.debug(f"⏳ Ordre {txid[:8]}... toujours ouvert...")
                await asyncio.sleep(2)
                continue

            if status in ("canceled", "expired"):
                return OrderResult(
                    success=False, txid=txid, error=f"Ordre {status}"
                )

            await asyncio.sleep(1)

        logger.warning(f"⏱️ Timeout exécution ordre {txid[:8]}...")
        return OrderResult(success=False, txid=txid, error="Timeout exécution")

    # ------------------------------------------------------------------
    # Order management
    # ------------------------------------------------------------------

    async def get_order_status(self, txid: str) -> Optional[OrderStatus]:
        success, response = await self._safe_api_call("QueryOrders", txid=txid)
        if (
            not success
            or "result" not in response
            or txid not in response["result"]
        ):
            return None
        info = response["result"][txid]
        return OrderStatus(
            txid=txid,
            status=info.get("status", "unknown"),
            volume=float(info.get("vol", 0)),
            volume_exec=float(info.get("vol_exec", 0)),
            price=float(info.get("price", 0)) if info.get("price") else None,
            avg_price=float(info.get("avg_price", 0))
            if info.get("avg_price")
            else None,
            fee=float(info.get("fee", 0)),
        )

    async def cancel_order(self, txid: str) -> bool:
        logger.info(f"🚫 Annulation ordre {txid[:8]}...")
        success, response = await self._safe_api_call("CancelOrder", txid=txid)
        if success:
            logger.info("✅ Ordre annulé")
            return True
        error = _extract_error(response)
        if "not found" in error.lower() or "already closed" in error.lower():
            return True
        logger.error(f"❌ Échec annulation: {error}")
        return False

    async def cancel_all_orders(
        self, userref: Optional[int] = None,
    ) -> bool:
        """Cancel all open orders."""
        logger.info(f"🚫 Annulation tous ordres" + (f" (userref={userref})" if userref else ""))
        success, response = await self._safe_api_call("OpenOrders")
        if not success:
            logger.error("❌ Impossible de récupérer ordres ouverts")
            return False
        if "result" not in response or "open" not in response["result"]:
            return True
        open_orders = response["result"]["open"]
        cancelled = 0
        for txid, order_info in open_orders.items():
            if userref is not None and order_info.get("userref") != userref:
                continue
            if await self.cancel_order(txid):
                cancelled += 1
        logger.info(f"✅ {cancelled} ordre(s) annulé(s)")
        return True

    # ------------------------------------------------------------------
    # Phase 3: reconciliation helpers
    # ------------------------------------------------------------------


    async def find_order_by_userref(self, userref: int) -> Optional[tuple[str, dict]]:
        """Find an order (open or closed) by its userref (ROB-01 recovery)."""
        # Check open orders
        open_orders = await self.get_open_orders()
        for txid, info in open_orders.items():
            if int(info.get("userref", 0)) == userref:
                return txid, info
        
        # Check closed orders (recent)
        closed_orders = await self.get_closed_orders()
        for txid, info in closed_orders.items():
            if int(info.get("userref", 0)) == userref:
                return txid, info
        
        return None

    async def get_closed_orders(
        self,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        symbol: Optional[str] = None,
    ) -> Dict[str, dict]:
        params: Dict[str, Any] = {}
        if start_time:
            params["start"] = start_time
        if end_time:
            params["end"] = end_time
        success, response = await self._safe_api_call("ClosedOrders", **params)
        if not success or "result" not in response or "closed" not in response["result"]:
            return {}
        closed = response["result"]["closed"]
        if symbol:
            sym_clean = symbol.replace("/", "")
            closed = {
                t: i
                for t, i in closed.items()
                if i.get("descr", {}).get("pair", "").replace("/", "") == sym_clean
            }
        return closed

    async def get_open_orders(self) -> Dict[str, dict]:
        success, response = await self._safe_api_call("OpenOrders")
        if not success or "result" not in response or "open" not in response["result"]:
            return {}
        return response["result"]["open"]

    async def get_balance(self) -> Dict[str, float]:
        success, response = await self._safe_api_call("Balance")
        if not success or "result" not in response:
            return {}
        out: Dict[str, float] = {}
        for asset, amount in response["result"].items():
            try:
                out[asset] = float(amount)
            except (ValueError, TypeError):
                continue
        return out

    async def get_trade_balance(self, asset: str = "EUR") -> Dict[str, float]:
        success, response = await self._safe_api_call("TradeBalance", asset=asset)
        if not success or "result" not in response:
            return {}
        out: Dict[str, Any] = {}
        for k, v in response["result"].items():
            try:
                out[k] = float(v)
            except (ValueError, TypeError):
                out[k] = v
        return out


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _extract_error(response: dict) -> str:
    err = response.get("error", "Unknown")
    if isinstance(err, list):
        return err[0] if err else "Unknown"
    return str(err)


def _extract_txid(response: dict) -> Tuple[Optional[str], Optional[str]]:
    """Extract txid from Kraken AddOrder response with explicit shape checks."""
    result = response.get("result")
    if not isinstance(result, dict):
        return None, "Champ 'result' manquant ou invalide dans réponse Kraken"

    txid_list = result.get("txid")
    if not isinstance(txid_list, list) or not txid_list:
        return None, "Champ 'txid' manquant, vide ou invalide dans réponse Kraken"

    txid = txid_list[0]
    if not isinstance(txid, str) or not txid:
        return None, "Premier txid invalide dans réponse Kraken"
    return txid, None


# ------------------------------------------------------------------
# Singleton
# ------------------------------------------------------------------

_executor_instance: Optional[OrderExecutorAsync] = None


def get_order_executor_async(
    api_key: Optional[str] = None,
    api_secret: Optional[str] = None,
) -> OrderExecutorAsync:
    global _executor_instance
    if _executor_instance is None:
        _executor_instance = OrderExecutorAsync(api_key, api_secret)
    return _executor_instance


def reset_order_executor_async() -> None:
    global _executor_instance
    _executor_instance = None
