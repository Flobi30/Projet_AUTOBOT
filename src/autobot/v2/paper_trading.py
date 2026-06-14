"""
CORRECTIONS CRITIQUES — Audit Opus 2026-04-07

Problèmes identifiés et fixes appliqués:

1. PAPER TRADING MANQUANT
   - OrderExecutorAsync n'avait aucune logique de simulation
   - Tout ordre allait directement sur Kraken LIVE
   → FIX: Ajout PaperTradingExecutor avec persistance SQLite

2. WEBSOCKET DISPATCH SILENCIEUX
   - Aucun log de prix traité en 30 minutes
   - Possible problème de dispatch vers les instances
   → FIX: Ajout logs de debugging dans on_price et ring_buffer

3. BASE DE DONNÉES — TABLE TRADES MANQUANTE
   - SQLite existait mais pas de table 'trades'
   → FIX: Création automatique de la table trades au démarrage

4. CODE MORT — 22+ modules non branchés
   → DOCUMENTÉ: Liste des modules développés mais non wirés
"""

# =============================================================================
# FIX 1: PaperTradingExecutor — Mode simulation complet
# =============================================================================

import asyncio
import json
import logging
import os
import sqlite3
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

from autobot.v2.cost_profiles import get_cost_profile
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable, Coroutine

from .order_executor import OrderResult, OrderSide, OrderStatus, OrderType

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float, minimum: float, maximum: float) -> float:
    raw = os.getenv(name)
    try:
        value = float(raw) if raw not in (None, "") else default
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


@dataclass
class PaperTrade:
    """Un trade simulé en paper trading."""
    id: str
    txid: str  # Fake txid pour compatibilité
    symbol: str
    side: str  # "buy" | "sell"
    volume: float
    price: float
    fees: float
    timestamp: str
    status: str  # "filled" | "pending" | "cancelled"
    userref: Optional[int] = None
    liquidity: str = "unknown"  # "maker" | "taker" | "unknown"
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PaperTradingExecutor:
    """
    Exécuteur de ordres en mode PAPER TRADING (simulation).
    
    Au lieu d'appeler Kraken, simule l'exécution immédiate au prix du marché
    et persiste les trades dans SQLite pour analyse.
    """
    
    def __init__(
        self,
        db_path: str = "data/paper_trades.db",
        initial_capital: float = 1000.0,
        fee_rate: Optional[float] = None,
    ):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.initial_capital = initial_capital
        canonical_paper_profile = get_cost_profile("paper_current_taker")
        explicit_fee_rate = fee_rate is not None
        default_maker_bps = (
            float(fee_rate) * 10000.0 if explicit_fee_rate else canonical_paper_profile.maker_fee_bps
        )
        default_taker_bps = (
            float(fee_rate) * 10000.0 if explicit_fee_rate else canonical_paper_profile.taker_fee_bps
        )
        self.maker_fee_rate = _env_float("PAPER_MAKER_FEE_BPS", default_maker_bps, 0.0, 250.0) / 10000.0
        self.taker_fee_rate = _env_float("PAPER_TAKER_FEE_BPS", default_taker_bps, 0.0, 250.0) / 10000.0
        self.fee_rate = float(fee_rate) if explicit_fee_rate else self.taker_fee_rate
        self.cost_profile_name = (
            "paper_current_taker"
            if not explicit_fee_rate
            and self.maker_fee_rate * 10000.0 == canonical_paper_profile.maker_fee_bps
            and self.taker_fee_rate * 10000.0 == canonical_paper_profile.taker_fee_bps
            else "paper_runtime_override"
        )
        self.allow_synthetic_price_fallback = _env_bool(
            "PAPER_ALLOW_SYNTHETIC_PRICE_FALLBACK",
            False,
        )
        self.maker_realism_enabled = _env_bool("PAPER_MAKER_REALISM_ENABLED", True)
        self.maker_require_book = _env_bool("PAPER_MAKER_REQUIRE_BOOK", True)
        self.maker_touch_bps = _env_float("PAPER_MAKER_TOUCH_BPS", 2.0, 0.0, 100.0)
        self.maker_max_spread_bps = _env_float("PAPER_MAKER_MAX_SPREAD_BPS", 12.0, 0.1, 1000.0)
        self.maker_max_adverse_risk = _env_float("PAPER_MAKER_MAX_ADVERSE_RISK", 0.58, 0.0, 1.0)
        self.maker_min_depth_eur = _env_float("PAPER_MAKER_MIN_DEPTH_EUR", 50.0, 0.0, 1_000_000.0)
        self.maker_missing_book_taker_fallback = _env_bool(
            "PAPER_MAKER_MISSING_BOOK_TAKER_FALLBACK",
            False,
        )
        self._lock = asyncio.Lock()
        self._microstructure_provider: Optional[Callable[[str], Any]] = None
        
        # Circuit breaker (même interface que OrderExecutorAsync)
        self._consecutive_errors = 0
        self._max_consecutive_errors = 10
        self._circuit_breaker_callback: Optional[Callable[[], Coroutine[Any, Any, None]]] = None
        
        # Callback pour notifier l'orchestrator d'un trade
        self._on_trade_executed: Optional[Callable[[PaperTrade], None]] = None
        
        self._init_db()
        logger.info(
            "PaperTradingExecutor initialised (capital=%.2f EUR, maker=%.2fbps, taker=%.2fbps, maker_realism=%s)",
            initial_capital,
            self.maker_fee_rate * 10000.0,
            self.taker_fee_rate * 10000.0,
            self.maker_realism_enabled,
        )
    
    def _init_db(self):
        """Crée la table trades si elle n'existe pas."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id TEXT PRIMARY KEY,
                    txid TEXT UNIQUE,
                    symbol TEXT,
                    side TEXT,
                    volume REAL,
                    price REAL,
                    fees REAL,
                    timestamp TEXT,
                    status TEXT,
                    userref INTEGER,
                    liquidity TEXT DEFAULT 'unknown',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            columns = {
                str(row[1])
                for row in conn.execute("PRAGMA table_info(trades)").fetchall()
            }
            if "liquidity" not in columns:
                conn.execute("ALTER TABLE trades ADD COLUMN liquidity TEXT DEFAULT 'unknown'")
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp)
            """)
            conn.commit()
    
    def set_circuit_breaker_callback(self, callback: Callable[[], Coroutine[Any, Any, None]]):
        """Pour compatibilité avec OrderExecutorAsync."""
        self._circuit_breaker_callback = callback
    
    def set_on_trade_callback(self, callback: Callable[[PaperTrade], None]):
        """Callback appelé quand un trade est exécuté."""
        self._on_trade_executed = callback

    def set_microstructure_provider(self, provider: Callable[[str], Any]) -> None:
        """Attach a callable returning order-book microstructure snapshots."""
        self._microstructure_provider = provider

    def _fee_rate_for_liquidity(self, liquidity: str) -> float:
        normalized = str(liquidity or "unknown").lower()
        if normalized == "maker":
            return self.maker_fee_rate
        if normalized == "taker":
            return self.taker_fee_rate
        return self.fee_rate

    @staticmethod
    def _asset_for_symbol(symbol: str) -> str:
        symbol = symbol.upper().replace("/", "").replace("-", "")
        if "ETH" in symbol:
            return "XETH"
        if "BTC" in symbol or "XBT" in symbol:
            return "XXBT"
        if "LTC" in symbol:
            return "XLTC"
        if "XRP" in symbol:
            return "XXRP"
        if "XLM" in symbol:
            return "XXLM"
        if "DOGE" in symbol or "XDG" in symbol:
            return "XDG"
        return symbol.replace("ZEUR", "").replace("EUR", "")

    @staticmethod
    def _symbol_for_asset(asset: str) -> str:
        asset = asset.upper()
        if asset == "XETH":
            return "XETHZEUR"
        if asset == "XXBT":
            return "XXBTZEUR"
        if asset == "XLTC":
            return "XLTCZEUR"
        if asset == "XXRP":
            return "XXRPZEUR"
        if asset == "XXLM":
            return "XXLMZEUR"
        if asset == "XDG":
            return "XDGEUR"
        direct_eur_assets = {"SOL", "TRX", "ADA", "DOT", "LINK", "AVAX", "BCH", "AAVE", "ATOM"}
        if asset in direct_eur_assets:
            return f"{asset}EUR"
        return f"{asset}ZEUR"

    @staticmethod
    def _fallback_price_for_symbol(symbol: str) -> float:
        """Legacy synthetic prices, disabled by default for market execution."""
        normalized = symbol.upper().replace("/", "").replace("-", "")
        fallback_prices = {
            "XXBTZEUR": 65000.0,
            "XBTZEUR": 65000.0,
            "BTCEUR": 65000.0,
            "XETHZEUR": 2000.0,
            "ETHEUR": 2000.0,
            "XLTCZEUR": 90.0,
            "LTCEUR": 90.0,
            "XXRPZEUR": 2.0,
            "XRPEUR": 2.0,
            "XXLMZEUR": 0.15,
            "XLMEUR": 0.15,
            "SOLEUR": 150.0,
            "TRXEUR": 0.30,
            "ADAEUR": 0.70,
            "XDGEUR": 0.20,
            "DOGEEUR": 0.20,
            "DOTEUR": 6.0,
            "LINKEUR": 15.0,
            "AVAXEUR": 35.0,
            "BCHEUR": 450.0,
        }
        return fallback_prices.get(normalized, 1.0)

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        return symbol.upper().replace("/", "").replace("-", "")

    @staticmethod
    def _ws_symbol_for_symbol(symbol: str) -> str:
        normalized = symbol.upper().replace("/", "").replace("-", "")
        aliases = {
            "XXBTZEUR": "XBT/EUR",
            "XBTZEUR": "XBT/EUR",
            "BTCEUR": "XBT/EUR",
            "XETHZEUR": "ETH/EUR",
            "ETHEUR": "ETH/EUR",
            "XLTCZEUR": "LTC/EUR",
            "LTCEUR": "LTC/EUR",
            "XXRPZEUR": "XRP/EUR",
            "XRPEUR": "XRP/EUR",
            "XXLMZEUR": "XLM/EUR",
            "XLMEUR": "XLM/EUR",
        }
        if normalized in aliases:
            return aliases[normalized]
        if normalized.endswith("ZEUR"):
            return f"{normalized[:-4]}/EUR"
        if normalized.endswith("EUR"):
            return f"{normalized[:-3]}/EUR"
        return symbol

    @staticmethod
    def _timestamp_to_epoch(timestamp: str) -> float:
        try:
            return datetime.fromisoformat(str(timestamp).replace("Z", "+00:00")).timestamp()
        except Exception:
            return datetime.now(timezone.utc).timestamp()

    @staticmethod
    def _order_type_from_txid(txid: str) -> str:
        if txid.startswith("PAPER_SL_"):
            return "stop-loss"
        if txid.startswith("PAPER_TP_"):
            return "take-profit"
        return "market"

    def _row_to_kraken_order(self, row: tuple[Any, ...]) -> Dict[str, Any]:
        txid = row[1]
        symbol = row[2]
        side = row[3]
        volume = float(row[4] or 0.0)
        price = float(row[5] or 0.0)
        status = row[8]
        return {
            "txid": txid,
            "descr": {
                "pair": symbol,
                "type": side,
                "ordertype": self._order_type_from_txid(txid),
                "price": str(price),
            },
            "vol": str(volume),
            "vol_exec": str(volume if status == "filled" else 0.0),
            "price": str(price),
            "avg_price": str(price if status == "filled" else 0.0),
            "fee": str(float(row[6] or 0.0)),
            "status": "closed" if status == "filled" else status,
            "opentm": self._timestamp_to_epoch(row[7]),
            "userref": row[9],
            "liquidity": row[10] if len(row) > 10 else "unknown",
        }
    
    # ------------------------------------------------------------------
    # Simulation des ordres
    # ------------------------------------------------------------------
    
    async def execute_market_order(
        self,
        symbol: str,
        side: OrderSide,
        volume: float,
        userref: Optional[int] = None,
        price_hint: Optional[float] = None,
    ) -> OrderResult:
        """Simule un ordre MARKET avec exécution immédiate."""
        logger.info(f"📊 [PAPER] Ordre MARKET {side.value.upper()} {volume:.6f} {symbol}")
        
        MIN_VOLUME = 0.0001
        if volume < MIN_VOLUME:
            return OrderResult(
                success=False,
                error=f"Volume {volume:.6f} inférieur au minimum ({MIN_VOLUME})",
            )
        
        # MARKET paper fills use the live book when available, then fall back to trusted tick/signal prices.
        book_price, book_source, book_snapshot = self._market_execution_price_from_book(symbol, side)
        if book_price is not None:
            price = book_price
            price_source = book_source
        else:
            price, price_source = await self._resolve_market_price(symbol, price_hint=price_hint)
        if price is None:
            logger.warning(
                "[PAPER] Ordre refuse pour %s: prix indisponible (websocket absent, signal sans prix fiable)",
                symbol,
            )
            return OrderResult(
                success=False,
                error=(
                    "paper_price_unavailable: aucun prix WebSocket ni prix de signal fiable "
                    f"pour {symbol}"
                ),
                raw_response={
                    "symbol": symbol,
                    "price_source": "unavailable",
                    "price_hint": price_hint,
                    "microstructure": book_snapshot,
                },
            )
        
        notional = volume * price
        liquidity = "taker"
        fees = notional * self._fee_rate_for_liquidity(liquidity)
        
        # Crée le trade
        trade = PaperTrade(
            id=str(uuid.uuid4()),
            txid=f"PAPER_{uuid.uuid4().hex[:16]}",
            symbol=symbol,
            side=side.value,
            volume=volume,
            price=price,
            fees=fees,
            timestamp=datetime.now(timezone.utc).isoformat(),
            status="filled",
            userref=userref,
            liquidity=liquidity,
        )
        
        # Persiste
        async with self._lock:
            self._save_trade(trade)
        
        # Notifie
        if self._on_trade_executed:
            try:
                self._on_trade_executed(trade)
            except Exception as e:
                logger.error(f"Erreur callback trade: {e}")
        
        logger.info(f"✅ [PAPER] Trade exécuté: {volume:.6f} @ {price:.2f}€ (frais: {fees:.4f}€)")
        
        return OrderResult(
            success=True,
            txid=trade.txid,
            executed_volume=volume,
            executed_price=price,
            fees=fees,
            liquidity=liquidity,
            raw_response={**trade.to_dict(), "price_source": price_source, "microstructure": book_snapshot},
        )

    async def execute_limit_order(
        self,
        symbol: str,
        side: OrderSide,
        volume: float,
        limit_price: float,
        post_only: bool = False,
        userref: Optional[int] = None,
    ) -> OrderResult:
        """Simule un ordre LIMIT avec exécution immédiate au prix limite."""
        logger.info(
            "[PAPER] Ordre LIMIT %s %.6f %s @ %.2f post_only=%s",
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
                error=f"Volume {volume:.6f} inférieur au minimum ({MIN_VOLUME})",
            )
        if limit_price <= 0:
            return OrderResult(success=False, error="Prix limite doit être > 0")

        fill_decision = self._paper_limit_fill_decision(
            symbol=symbol,
            side=side,
            volume=volume,
            limit_price=limit_price,
            post_only=post_only,
        )
        if (
            not fill_decision["filled"]
            and post_only
            and self.maker_missing_book_taker_fallback
            and str(fill_decision.get("reason")) == "paper_maker_book_unavailable"
        ):
            fallback_price, price_source = await self._resolve_market_price(symbol, price_hint=limit_price)
            if fallback_price is not None and fallback_price > 0:
                logger.info(
                    "[PAPER] Fallback maker->taker pour %s: carnet absent, execution taker a %.6f (source=%s)",
                    symbol,
                    fallback_price,
                    price_source,
                )
                fill_decision = {
                    "filled": True,
                    "reason": "paper_maker_missing_book_taker_fallback",
                    "fallback_from": "paper_maker_book_unavailable",
                    "executed_price": float(fallback_price),
                    "liquidity": "taker",
                    "price_source": price_source,
                    "original_limit_price": float(limit_price),
                    "microstructure": fill_decision.get("microstructure", {}),
                }
            else:
                fill_decision = {
                    **fill_decision,
                    "fallback_attempted": True,
                    "fallback_reason": "paper_taker_price_unavailable",
                }

        if not fill_decision["filled"]:
            return OrderResult(
                success=False,
                error=str(fill_decision["reason"]),
                liquidity="maker" if post_only else "unknown",
                raw_response=fill_decision,
            )

        execution_price = float(fill_decision.get("executed_price") or limit_price)
        liquidity = str(fill_decision.get("liquidity") or ("maker" if post_only else "unknown"))
        notional = volume * execution_price
        fees = notional * self._fee_rate_for_liquidity(liquidity)
        trade = PaperTrade(
            id=str(uuid.uuid4()),
            txid=f"PAPER_LMT_{uuid.uuid4().hex[:16]}",
            symbol=symbol,
            side=side.value,
            volume=volume,
            price=execution_price,
            fees=fees,
            timestamp=datetime.now(timezone.utc).isoformat(),
            status="filled",
            userref=userref,
            liquidity=liquidity,
        )

        async with self._lock:
            self._save_trade(trade)

        if self._on_trade_executed:
            try:
                self._on_trade_executed(trade)
            except Exception as e:
                logger.error(f"Erreur callback trade: {e}")

        return OrderResult(
            success=True,
            txid=trade.txid,
            executed_volume=volume,
            executed_price=execution_price,
            fees=fees,
            liquidity=liquidity,
            raw_response={**trade.to_dict(), "paper_fill_decision": fill_decision},
        )
    
    async def execute_stop_loss_order(
        self,
        symbol: str,
        side: OrderSide,
        volume: float,
        stop_price: float,
        userref: Optional[int] = None,
    ) -> OrderResult:
        """Simule un ordre STOP-LOSS (enregistré comme pending)."""
        logger.info(f"📊 [PAPER] Ordre STOP-LOSS {side.value.upper()} {volume:.6f} {symbol} @ {stop_price:.2f}")
        
        MIN_VOLUME = 0.0001
        if volume < MIN_VOLUME:
            return OrderResult(
                success=False,
                error=f"Volume {volume:.6f} inférieur au minimum ({MIN_VOLUME})",
            )
        
        trade = PaperTrade(
            id=str(uuid.uuid4()),
            txid=f"PAPER_SL_{uuid.uuid4().hex[:16]}",
            symbol=symbol,
            side=side.value,
            volume=volume,
            price=stop_price,
            fees=0.0,
            timestamp=datetime.now(timezone.utc).isoformat(),
            status="pending",  # En attente de déclenchement
            userref=userref,
        )
        
        async with self._lock:
            self._save_trade(trade)
        
        logger.info(f"✅ [PAPER] Stop-loss enregistré: {trade.txid[:16]}")
        
        return OrderResult(
            success=True,
            txid=trade.txid,
            raw_response=trade.to_dict(),
        )
    
    async def _get_current_price(self, symbol: str) -> Optional[float]:
        """Récupère le prix actuel du WebSocket."""
        try:
            # Tente de récupérer depuis le ring buffer
            from .ring_buffer_dispatcher import get_ring_buffer
            rb = get_ring_buffer()
            if rb:
                symbols_to_try = [symbol, self._ws_symbol_for_symbol(symbol)]
                for ws_symbol in dict.fromkeys(symbols_to_try):
                    snapshot = rb.get_snapshot(ws_symbol)
                    if snapshot and len(snapshot) > 0:
                        return float(snapshot[-1])
        except Exception as e:
            logger.debug(f"Impossible de récupérer prix depuis ring buffer: {e}")
        
        return None

    async def _resolve_market_price(
        self,
        symbol: str,
        *,
        price_hint: Optional[float] = None,
    ) -> tuple[Optional[float], str]:
        """Resolve a paper execution price without inventing one by default."""
        price = await self._get_current_price(symbol)
        if price is not None and price > 0:
            return float(price), "websocket"

        if price_hint is not None and price_hint > 0:
            price = float(price_hint)
            logger.info(
                "[PAPER] Prix WebSocket indisponible pour %s, utilisation prix signal %.6f",
                symbol,
                price,
            )
            return price, "signal"

        if self.allow_synthetic_price_fallback:
            price = self._fallback_price_for_symbol(symbol)
            logger.warning(
                "[PAPER] Prix non disponible pour %s, fallback synthetique active %.6f",
                symbol,
                price,
            )
            return price, "synthetic_fallback"

        return None, "unavailable"

    def _get_microstructure_snapshot(self, symbol: str) -> dict[str, Any]:
        provider = self._microstructure_provider
        if provider is None:
            return {"symbol": self._normalize_symbol(symbol), "has_book": False, "reason": "provider_unavailable"}
        for candidate in dict.fromkeys([symbol, self._ws_symbol_for_symbol(symbol), self._normalize_symbol(symbol)]):
            try:
                snapshot = provider(candidate)
            except Exception as exc:
                logger.debug("Paper microstructure provider failed for %s: %s", candidate, exc)
                continue
            if snapshot is None:
                continue
            if hasattr(snapshot, "to_dict"):
                snapshot = snapshot.to_dict()
            if isinstance(snapshot, dict):
                return dict(snapshot)
        return {"symbol": self._normalize_symbol(symbol), "has_book": False, "reason": "snapshot_unavailable"}

    def _market_execution_price_from_book(
        self,
        symbol: str,
        side: OrderSide,
    ) -> tuple[Optional[float], str, dict[str, Any]]:
        """Resolve a paper MARKET fill from best bid/ask when a valid book is available."""
        snapshot = self._get_microstructure_snapshot(symbol)
        snapshot["symbol"] = snapshot.get("symbol") or self._normalize_symbol(symbol)
        if not snapshot.get("has_book"):
            return None, "book_unavailable", snapshot

        try:
            bid = float(snapshot.get("bid") or 0.0)
            ask = float(snapshot.get("ask") or 0.0)
        except (TypeError, ValueError):
            return None, "book_invalid", snapshot

        if bid <= 0.0 or ask <= 0.0 or bid >= ask:
            return None, "book_invalid", snapshot

        side_value = side.value if isinstance(side, OrderSide) else str(side)
        if side_value == "buy":
            return ask, "book_ask", snapshot
        if side_value == "sell":
            return bid, "book_bid", snapshot
        return None, "book_side_unknown", snapshot

    def _paper_limit_fill_decision(
        self,
        *,
        symbol: str,
        side: OrderSide,
        volume: float,
        limit_price: float,
        post_only: bool,
    ) -> dict[str, Any]:
        """Conservative immediate-fill simulation for paper post-only orders."""
        if not post_only or not self.maker_realism_enabled:
            return {
                "filled": True,
                "reason": "legacy_limit_fill" if not post_only else "maker_realism_disabled",
                "executed_price": float(limit_price),
                "liquidity": "maker" if post_only else "unknown",
            }

        snapshot = self._get_microstructure_snapshot(symbol)
        snapshot["symbol"] = snapshot.get("symbol") or self._normalize_symbol(symbol)
        if not snapshot.get("has_book"):
            if self.maker_require_book:
                return {
                    "filled": False,
                    "reason": "paper_maker_book_unavailable",
                    "executed_price": 0.0,
                    "liquidity": "maker",
                    "microstructure": snapshot,
                }
            return {
                "filled": True,
                "reason": "maker_book_optional",
                "executed_price": float(limit_price),
                "liquidity": "maker",
                "microstructure": snapshot,
            }

        bid = float(snapshot.get("bid") or 0.0)
        ask = float(snapshot.get("ask") or 0.0)
        spread_bps = float(snapshot.get("spread_bps") or 0.0)
        side_value = side.value if isinstance(side, OrderSide) else str(side)
        if bid <= 0.0 or ask <= 0.0 or bid >= ask:
            return {
                "filled": False,
                "reason": "paper_maker_invalid_book",
                "executed_price": 0.0,
                "liquidity": "maker",
                "microstructure": snapshot,
            }
        if side_value == "buy" and limit_price >= ask:
            return {
                "filled": False,
                "reason": "paper_post_only_would_take_liquidity",
                "executed_price": 0.0,
                "liquidity": "maker",
                "microstructure": snapshot,
            }
        if side_value == "sell" and limit_price <= bid:
            return {
                "filled": False,
                "reason": "paper_post_only_would_take_liquidity",
                "executed_price": 0.0,
                "liquidity": "maker",
                "microstructure": snapshot,
            }
        if spread_bps > self.maker_max_spread_bps:
            return {
                "filled": False,
                "reason": "paper_maker_spread_too_wide",
                "executed_price": 0.0,
                "liquidity": "maker",
                "microstructure": snapshot,
            }

        notional = max(0.0, float(volume) * float(limit_price))
        if side_value == "buy":
            depth = float(snapshot.get("bid_depth_eur") or 0.0)
            risk = float(snapshot.get("buy_adverse_selection_risk") or snapshot.get("adverse_selection_risk") or 0.0)
            reference = bid
            too_far = limit_price < reference * (1.0 - self.maker_touch_bps / 10000.0)
        else:
            depth = float(snapshot.get("ask_depth_eur") or 0.0)
            risk = float(snapshot.get("sell_adverse_selection_risk") or snapshot.get("adverse_selection_risk") or 0.0)
            reference = ask
            too_far = limit_price > reference * (1.0 + self.maker_touch_bps / 10000.0)

        if depth < max(self.maker_min_depth_eur, notional):
            return {
                "filled": False,
                "reason": "paper_maker_depth_insufficient",
                "executed_price": 0.0,
                "liquidity": "maker",
                "microstructure": snapshot,
            }
        if risk > self.maker_max_adverse_risk:
            return {
                "filled": False,
                "reason": "paper_maker_adverse_selection",
                "executed_price": 0.0,
                "liquidity": "maker",
                "microstructure": snapshot,
            }
        if too_far:
            return {
                "filled": False,
                "reason": "paper_maker_not_touched",
                "executed_price": 0.0,
                "liquidity": "maker",
                "microstructure": snapshot,
            }
        return {
            "filled": True,
            "reason": "paper_maker_touch_fill",
            "executed_price": float(limit_price),
            "liquidity": "maker",
            "microstructure": snapshot,
        }

    def _save_trade(self, trade: PaperTrade):
        """Sauvegarde un trade dans SQLite."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO trades 
                (id, txid, symbol, side, volume, price, fees, timestamp, status, userref, liquidity)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade.id, trade.txid, trade.symbol, trade.side,
                trade.volume, trade.price, trade.fees, trade.timestamp,
                trade.status, trade.userref, trade.liquidity
            ))
            conn.commit()
    
    # ------------------------------------------------------------------
    # Gestion des ordres (pour compatibilité API)
    # ------------------------------------------------------------------
    
    async def get_order_status(self, txid: str) -> Optional[OrderStatus]:
        """Récupère le statut d'un ordre paper."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM trades WHERE txid = ?", (txid,)
            ).fetchone()
            
            if not row:
                return None
            
            return OrderStatus(
                txid=row[1],  # txid
                status=row[8],  # status
                volume=row[4],  # volume
                volume_exec=row[4] if row[8] == "filled" else 0.0,
                price=row[5],
                avg_price=row[5],
                fee=row[6],
            )

    async def get_open_orders(self) -> Dict[str, dict]:
        """Récupère les ordres paper encore ouverts, au format Kraken-like."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM trades WHERE status = 'pending'"
            ).fetchall()
            return {row[1]: self._row_to_kraken_order(row) for row in rows}

    async def find_order_by_userref(self, userref: int) -> Optional[tuple[str, dict]]:
        """Find a paper order by userref across pending and filled rows."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT * FROM trades
                WHERE userref = ?
                ORDER BY datetime(timestamp) DESC
                LIMIT 1
                """,
                (userref,),
            ).fetchone()
            if not row:
                return None
            return row[1], self._row_to_kraken_order(row)
    
    async def cancel_order(self, txid: str) -> bool:
        """Annule un ordre paper pending."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE trades SET status = 'cancelled' WHERE txid = ? AND status = 'pending'",
                (txid,)
            )
            conn.commit()
            return True
    
    async def cancel_all_orders(self, userref: Optional[int] = None) -> bool:
        """Annule tous les ordres paper pending."""
        with sqlite3.connect(self.db_path) as conn:
            if userref:
                conn.execute(
                    "UPDATE trades SET status = 'cancelled' WHERE userref = ? AND status = 'pending'",
                    (userref,)
                )
            else:
                conn.execute("UPDATE trades SET status = 'cancelled' WHERE status = 'pending'")
            conn.commit()
            return True
    
    # ------------------------------------------------------------------
    # Reconciliation helpers (compatibilité)
    # ------------------------------------------------------------------
    
    async def get_closed_orders(
        self,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        symbol: Optional[str] = None,
    ) -> Dict[str, dict]:
        """Récupère les trades paper fermés."""
        query = "SELECT * FROM trades WHERE status = 'filled'"
        params = []
        
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
            
            result = {}
            for row in rows:
                txid = row[1]
                order = self._row_to_kraken_order(row)
                order.update({
                    "symbol": row[2],
                    "side": row[3],
                    "volume": row[4],
                    "fees": row[6],
                    "timestamp": row[7],
                })
                result[txid] = order
            return result
    
    async def get_balance(self) -> Dict[str, float]:
        """Calcule le solde simulé basé sur les trades."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT * FROM trades WHERE status = 'filled'").fetchall()
            
            eur_balance = self.initial_capital
            asset_balances: Dict[str, float] = {}
            
            for row in rows:
                side = row[3]
                volume = row[4]
                price = row[5]
                fees = row[6]
                
                notional = volume * price
                
                if side == "buy":
                    eur_balance -= notional + fees
                    asset = self._asset_for_symbol(row[2])
                    asset_balances[asset] = asset_balances.get(asset, 0.0) + volume
                else:  # sell
                    eur_balance += notional - fees
                    asset = self._asset_for_symbol(row[2])
                    asset_balances[asset] = asset_balances.get(asset, 0.0) - volume
            
            return {"ZEUR": eur_balance, **asset_balances}
    
    async def get_trade_balance(self, asset: str = "EUR") -> Dict[str, float]:
        """Retourne le trade balance simulé."""
        balance = await self.get_balance()
        eur = balance.get("ZEUR", 0.0)
        asset_value = 0.0
        
        # Valeur estimée du BTC en EUR (prix courant approximatif)
        for paper_asset, qty in balance.items():
            if paper_asset == "ZEUR" or qty == 0:
                continue
            symbol = self._last_filled_symbol_for_asset(paper_asset) or self._symbol_for_asset(paper_asset)
            price = await self._get_current_price(symbol)
            if price is None:
                price = self._last_filled_price_for_symbol(symbol)
            if price is None and self.allow_synthetic_price_fallback:
                price = self._fallback_price_for_symbol(symbol)
            if price is None:
                logger.warning(
                    "[PAPER] Valorisation ignoree pour %s: aucun prix WebSocket ni dernier fill",
                    symbol,
                )
                continue
            asset_value += qty * price
        
        return {
            "equivalent_balance": eur + asset_value,
            "trade_balance": eur,
            "margin": eur + asset_value,
        }

    def _last_filled_price_for_symbol(self, symbol: str) -> Optional[float]:
        normalized = self._normalize_symbol(symbol)
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT symbol, price
                FROM trades
                WHERE status = 'filled'
                ORDER BY datetime(timestamp) DESC
                """
            ).fetchall()
        for row_symbol, price in rows:
            if self._normalize_symbol(str(row_symbol or "")) != normalized:
                continue
            try:
                value = float(price)
            except (TypeError, ValueError):
                continue
            if value > 0:
                return value
        return None

    def _last_filled_symbol_for_asset(self, asset: str) -> Optional[str]:
        normalized_asset = self._asset_for_symbol(asset)
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT symbol
                FROM trades
                WHERE status = 'filled' AND symbol IS NOT NULL
                ORDER BY datetime(timestamp) DESC
                """
            ).fetchall()

        for (symbol,) in rows:
            candidate = str(symbol or "")
            if candidate and self._asset_for_symbol(candidate) == normalized_asset:
                return candidate
        return None
    
    # ------------------------------------------------------------------
    # Analytics
    # ------------------------------------------------------------------
    
    def get_trade_summary(self) -> Dict[str, Any]:
        """Retourne un résumé des trades paper."""
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM trades WHERE status = 'filled'").fetchone()[0]
            
            buys = conn.execute(
                "SELECT COUNT(*), SUM(volume), SUM(volume * price + fees) FROM trades WHERE side = 'buy' AND status = 'filled'"
            ).fetchone()
            
            sells = conn.execute(
                "SELECT COUNT(*), SUM(volume), SUM(volume * price - fees) FROM trades WHERE side = 'sell' AND status = 'filled'"
            ).fetchone()
            
            # Calcul du P&L approximatif
            pnl = 0.0
            if sells[2] and buys[2]:
                pnl = sells[2] - buys[2]
            
            # Profit Factor
            gross_profit = conn.execute(
                "SELECT SUM(volume * price - fees) FROM trades WHERE side = 'sell' AND status = 'filled' AND (volume * price) > (SELECT AVG(volume * price) FROM trades WHERE side = 'buy')"
            ).fetchone()[0] or 0.0
            
            gross_loss = conn.execute(
                "SELECT SUM(volume * price + fees) FROM trades WHERE side = 'buy' AND status = 'filled'"
            ).fetchone()[0] or 0.0
            
            pf = gross_profit / gross_loss if gross_loss > 0 else 0.0
            liquidity_rows = conn.execute(
                """
                SELECT COALESCE(liquidity, 'unknown'), COUNT(*)
                FROM trades
                WHERE status = 'filled'
                GROUP BY COALESCE(liquidity, 'unknown')
                """
            ).fetchall()
            liquidity_counts = {str(row[0] or "unknown"): int(row[1] or 0) for row in liquidity_rows}
            
            return {
                "total_trades": total,
                "buys": buys[0] or 0,
                "sells": sells[0] or 0,
                "total_volume_btc": (buys[1] or 0.0) + (sells[1] or 0.0),
                "total_fees_eur": conn.execute("SELECT SUM(fees) FROM trades").fetchone()[0] or 0.0,
                "estimated_pnl_eur": pnl,
                "profit_factor": pf,
                "maker_trades": liquidity_counts.get("maker", 0),
                "taker_trades": liquidity_counts.get("taker", 0),
                "unknown_liquidity_trades": liquidity_counts.get("unknown", 0),
                "maker_fee_bps": self.maker_fee_rate * 10000.0,
                "taker_fee_bps": self.taker_fee_rate * 10000.0,
                "cost_profile": self.cost_profile_name,
                "taker_taker_round_trip_fee_bps": self.taker_fee_rate * 20000.0,
                "maker_maker_round_trip_fee_bps": self.maker_fee_rate * 20000.0,
                "maker_realism_enabled": self.maker_realism_enabled,
                "db_path": str(self.db_path),
            }
    
    async def close(self):
        """Cleanup (pour compatibilité)."""
        pass


# =============================================================================
# FIX 2: OrderExecutorAsync avec mode Paper Trading
# =============================================================================

class OrderExecutorAsyncWithPaper:
    """
    Wrapper qui sélectionne entre OrderExecutorAsync (live) et PaperTradingExecutor.
    
    Utilise PAPER_TRADING=true dans .env pour activer le mode simulation.
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        paper_mode: bool = False,
        paper_initial_capital: float = 1000.0,
    ):
        self.paper_mode = paper_mode
        
        if paper_mode:
            logger.info("🎮 MODE PAPER TRADING ACTIVÉ")
            self._executor = PaperTradingExecutor(
                initial_capital=paper_initial_capital
            )
        else:
            logger.info("🔴 MODE LIVE TRADING — ORDRES RÉELS SUR KRAKEN")
            from .order_executor_async import OrderExecutorAsync
            self._executor = OrderExecutorAsync(api_key, api_secret)
    
    def __getattr__(self, name):
        """Délègue tous les appels à l'exécuteur sous-jacent."""
        return getattr(self._executor, name)
    
    async def close(self):
        """Ferme proprement l'exécuteur."""
        if hasattr(self._executor, 'close'):
            await self._executor.close()


# =============================================================================
# Singleton
# =============================================================================

_paper_executor_instance: Optional[PaperTradingExecutor] = None


def get_paper_executor(
    initial_capital: float = 1000.0,
    db_path: str = "data/paper_trades.db",
) -> PaperTradingExecutor:
    """Singleton pour PaperTradingExecutor."""
    global _paper_executor_instance
    if _paper_executor_instance is None:
        _paper_executor_instance = PaperTradingExecutor(
            initial_capital=initial_capital,
            db_path=db_path,
        )
    return _paper_executor_instance


def reset_paper_executor():
    """Reset le singleton (pour tests)."""
    global _paper_executor_instance
    _paper_executor_instance = None
