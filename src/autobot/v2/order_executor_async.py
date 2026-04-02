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
import logging
import time
import urllib.parse
from typing import Any, Callable, Coroutine, Dict, Optional, Tuple

import aiohttp

from .order_executor import OrderResult, OrderSide, OrderStatus, OrderType

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


class OrderExecutorAsync:
    """
    Async order executor using aiohttp + Kraken REST API v0.

    Drop-in async replacement for OrderExecutor.
    """

    KRAKEN_API_URL = "https://api.kraken.com"

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
    ) -> None:
        # SEC-03: clés privées, fallback sur variables d'env
        import os as _os
        self._api_key: Optional[str] = api_key or _os.getenv("KRAKEN_API_KEY")
        self._api_secret: Optional[str] = api_secret or _os.getenv("KRAKEN_API_SECRET")
        self._lock = asyncio.Lock()
        self._session: Optional[aiohttp.ClientSession] = None

        # Rate limiting
        self._last_call_time: float = 0
        self._min_interval: float = 1.0

        # Circuit breaker
        self._consecutive_errors: int = 0
        self._max_consecutive_errors: int = 10
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
            return await resp.json()

    async def _query_private(self, method: str, **params: Any) -> dict:
        """Call Kraken private API endpoint with HMAC signing."""
        if not self._api_key or not self._api_secret:
            raise ValueError("Clés API Kraken non configurées")

        urlpath = f"/0/private/{method}"
        url = f"{self.KRAKEN_API_URL}{urlpath}"

        params["nonce"] = str(int(time.time() * 1000))
        sig = _kraken_signature(urlpath, params, self._api_secret)

        headers = {
            "API-Key": self._api_key,
            "API-Sign": sig,
        }

        session = await self._get_session()
        async with session.post(url, data=params, headers=headers) as resp:
            return await resp.json()

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
                    return False, {"error": f"Méthode inconnue: {method}"}

                # Check errors
                if response.get("error"):
                    error_msg = str(response["error"])
                    if "Rate limit exceeded" in error_msg:
                        wait = 2 ** attempt
                        logger.warning(f"⏳ Rate limit, attente {wait}s...")
                        await asyncio.sleep(wait)
                        continue

                    logger.error(f"❌ Erreur API Kraken: {error_msg}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    await self._increment_error_count()
                    return False, response

                self._reset_error_count()
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

        txid = None
        if "result" in response and "txid" in response["result"]:
            txid = response["result"]["txid"][0]
            logger.info(f"✅ Ordre accepté, txid: {txid[:8]}...")
        else:
            return OrderResult(success=False, error="Pas de txid dans réponse")

        return await self._wait_for_execution(txid, max_wait=60)

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

        txid = None
        if "result" in response and "txid" in response["result"]:
            txid = response["result"]["txid"][0]
            logger.info(f"✅ Stop-loss posé, txid: {txid[:8]}...")
            return OrderResult(success=True, txid=txid)

        return OrderResult(success=False, error="Pas de txid")

    async def _wait_for_execution(
        self, txid: str, max_wait: int = 60
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
                logger.info(
                    f"✅ Ordre exécuté: {vol_exec:.6f} @ {avg_price:.2f}€ (frais: {fee:.4f}€)"
                )
                return OrderResult(
                    success=True,
                    txid=txid,
                    executed_volume=vol_exec,
                    executed_price=avg_price,
                    fees=fee,
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
