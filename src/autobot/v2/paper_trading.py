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
import sqlite3
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable, Coroutine

from .order_executor import OrderResult, OrderSide, OrderStatus, OrderType

logger = logging.getLogger(__name__)


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
        fee_rate: float = 0.0016,  # 0.16% maker fee Kraken
    ):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.initial_capital = initial_capital
        self.fee_rate = fee_rate
        self._lock = asyncio.Lock()
        
        # Circuit breaker (même interface que OrderExecutorAsync)
        self._consecutive_errors = 0
        self._max_consecutive_errors = 10
        self._circuit_breaker_callback: Optional[Callable[[], Coroutine[Any, Any, None]]] = None
        
        # Callback pour notifier l'orchestrator d'un trade
        self._on_trade_executed: Optional[Callable[[PaperTrade], None]] = None
        
        self._init_db()
        logger.info(f"📊 PaperTradingExecutor initialisé (capital: {initial_capital}€, fees: {fee_rate:.2%})")
    
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
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
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

    @staticmethod
    def _asset_for_symbol(symbol: str) -> str:
        if "ETH" in symbol:
            return "XETH"
        if "BTC" in symbol or "XBT" in symbol:
            return "XXBT"
        return symbol.replace("ZEUR", "").replace("EUR", "")

    @staticmethod
    def _symbol_for_asset(asset: str) -> str:
        if asset == "XETH":
            return "XETHZEUR"
        if asset == "XXBT":
            return "XXBTZEUR"
        return f"{asset}ZEUR"

    @staticmethod
    def _fallback_price_for_symbol(symbol: str) -> float:
        if "ETH" in symbol:
            return 2000.0
        return 60000.0

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
    ) -> OrderResult:
        """Simule un ordre MARKET avec exécution immédiate."""
        logger.info(f"📊 [PAPER] Ordre MARKET {side.value.upper()} {volume:.6f} {symbol}")
        
        MIN_VOLUME = 0.0001
        if volume < MIN_VOLUME:
            return OrderResult(
                success=False,
                error=f"Volume {volume:.6f} inférieur au minimum ({MIN_VOLUME})",
            )
        
        # Récupère le prix actuel du WebSocket
        price = await self._get_current_price(symbol)
        if price is None:
            logger.warning(f"⚠️ [PAPER] Prix non disponible pour {symbol}, utilisation prix fallback 60000")
            price = 60000.0  # Fallback
        
        # Calcule les frais
        notional = volume * price
        fees = notional * self.fee_rate
        
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
            raw_response=trade.to_dict(),
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

        notional = volume * limit_price
        fees = notional * self.fee_rate
        trade = PaperTrade(
            id=str(uuid.uuid4()),
            txid=f"PAPER_LMT_{uuid.uuid4().hex[:16]}",
            symbol=symbol,
            side=side.value,
            volume=volume,
            price=limit_price,
            fees=fees,
            timestamp=datetime.now(timezone.utc).isoformat(),
            status="filled",
            userref=userref,
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
            executed_price=limit_price,
            fees=fees,
            liquidity="maker" if post_only else "unknown",
            raw_response=trade.to_dict(),
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
                # Convertit XXBTZEUR → XBT/EUR pour le ring buffer
                ws_symbol = symbol.replace("XXBTZ", "XBT/").replace("Z", "/")
                snapshot = rb.get_snapshot(ws_symbol)
                if snapshot and len(snapshot) > 0:
                    return float(snapshot[-1])
        except Exception as e:
            logger.debug(f"Impossible de récupérer prix depuis ring buffer: {e}")
        
        return None
    
    def _save_trade(self, trade: PaperTrade):
        """Sauvegarde un trade dans SQLite."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO trades 
                (id, txid, symbol, side, volume, price, fees, timestamp, status, userref)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade.id, trade.txid, trade.symbol, trade.side,
                trade.volume, trade.price, trade.fees, trade.timestamp,
                trade.status, trade.userref
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
            symbol = self._symbol_for_asset(paper_asset)
            price = await self._get_current_price(symbol) or self._fallback_price_for_symbol(symbol)
            asset_value += qty * price
        
        return {
            "equivalent_balance": eur + asset_value,
            "trade_balance": eur,
            "margin": eur + asset_value,
        }
    
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
            
            return {
                "total_trades": total,
                "buys": buys[0] or 0,
                "sells": sells[0] or 0,
                "total_volume_btc": (buys[1] or 0.0) + (sells[1] or 0.0),
                "total_fees_eur": conn.execute("SELECT SUM(fees) FROM trades").fetchone()[0] or 0.0,
                "estimated_pnl_eur": pnl,
                "profit_factor": pf,
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
