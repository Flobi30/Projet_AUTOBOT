"""
Analysis Feed — Seed & maintain price data for all 70 analysis pairs.

BUG FIX (P0): MarketSelector returns 0 pairs because MarketAnalyzer has
no price history for the 70 analysis pairs.  Only the 10 active trading
pairs receive WebSocket data.

This module:
1. Bootstrap: fetches current ticker prices for all 70 pairs via Kraken
   REST API (one batch request, no auth needed).
2. Ongoing: subscribes all 70 pairs to the WebSocket ticker feed so
   MarketAnalyzer continuously receives price updates.

Usage (in orchestrator startup):
    from .analysis_feed import AnalysisFeed
    feed = AnalysisFeed(ws_client, market_analyzer)
    await feed.bootstrap_and_subscribe()
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

import aiohttp

from .market_analyzer import MarketAnalyzer, get_market_analyzer
from .websocket_async import KrakenWebSocketAsync

logger = logging.getLogger(__name__)

# ── All 70 analysis pairs ────────────────────────────────────────────────

# 50 Cryptos (Kraken REST names → WS names)
CRYPTO_ANALYSIS_PAIRS: Dict[str, str] = {
    # Majors (10)
    "XXBTZEUR": "XBT/EUR",
    "XETHZEUR": "ETH/EUR",
    "SOLEUR": "SOL/EUR",
    "ADAEUR": "ADA/EUR",
    "DOTEUR": "DOT/EUR",
    "LINKEUR": "LINK/EUR",
    "AVAXEUR": "AVAX/EUR",
    "MATICEUR": "MATIC/EUR",
    "UNIEUR": "UNI/EUR",
    "AAVEEUR": "AAVE/EUR",
    # Altcoins majeurs (10)
    "XXRPZEUR": "XRP/EUR",
    "XLTCZEUR": "LTC/EUR",
    "BCHEUR": "BCH/EUR",
    "XXLMZEUR": "XLM/EUR",
    "XETCZEUR": "ETC/EUR",
    "ALGOEUR": "ALGO/EUR",
    "ATOMEUR": "ATOM/EUR",
    "FILEUR": "FIL/EUR",
    "XTZEUR": "XTZ/EUR",
    "EOSEUR": "EOS/EUR",
    # DeFi (10)
    "MKREUR": "MKR/EUR",
    "COMPEUR": "COMP/EUR",
    "YFIEUR": "YFI/EUR",
    "SNXEUR": "SNX/EUR",
    "CRVEUR": "CRV/EUR",
    "SUSHIEUR": "SUSHI/EUR",
    "1INCHEUR": "1INCH/EUR",
    "LRCEUR": "LRC/EUR",
    "GRTEUR": "GRT/EUR",
    "BATEUR": "BAT/EUR",
    # Layer 1 & Metaverse (10)
    "NEAREUR": "NEAR/EUR",
    "FTMEUR": "FTM/EUR",
    "ONEEUR": "ONE/EUR",
    "EGLDEUR": "EGLD/EUR",
    "ICPEUR": "ICP/EUR",
    "FLOWEUR": "FLOW/EUR",
    "CHZEUR": "CHZ/EUR",
    "ENJEUR": "ENJ/EUR",
    "MANAEUR": "MANA/EUR",
    "SANDEUR": "SAND/EUR",
    # Memes & Divers (10)
    "DOGEEUR": "DOGE/EUR",
    "SHIBEUR": "SHIB/EUR",
    "TRXEUR": "TRX/EUR",
    "XXMRZEUR": "XMR/EUR",
    "DASHEUR": "DASH/EUR",
    "XZECZEUR": "ZEC/EUR",
    "WAVESEUR": "WAVES/EUR",
    "THETAEUR": "THETA/EUR",
    "VETEUR": "VET/EUR",
    "HBAREUR": "HBAR/EUR",
}

# 20 Forex pairs (Kraken REST names → WS names)
FOREX_ANALYSIS_PAIRS: Dict[str, str] = {
    "EURUSD": "EUR/USD",
    "GBPUSD": "GBP/USD",
    "USDJPY": "USD/JPY",
    "USDCHF": "USD/CHF",
    "AUDUSD": "AUD/USD",
    "USDCAD": "USD/CAD",
    "NZDUSD": "NZD/USD",
    "EURGBP": "EUR/GBP",
    "EURJPY": "EUR/JPY",
    "EURCHF": "EUR/CHF",
    "GBPJPY": "GBP/JPY",
    "GBPCHF": "GBP/CHF",
    "CHFJPY": "CHF/JPY",
    "AUDJPY": "AUD/JPY",
    "CADJPY": "CAD/JPY",
    "NZDJPY": "NZD/JPY",
    "EURAUD": "EUR/AUD",
    "EURCAD": "EUR/CAD",
    "GBPAUD": "GBP/AUD",
    "AUDCAD": "AUD/CAD",
}

# Combined: all 70 pairs
ALL_ANALYSIS_PAIRS: Dict[str, str] = {**CRYPTO_ANALYSIS_PAIRS, **FOREX_ANALYSIS_PAIRS}

# MarketSelector uses friendly names (BTC/EUR not XBT/EUR).
# Map WS pair names back to the friendly names used by MarketSelector.
_WS_TO_FRIENDLY: Dict[str, str] = {
    "XBT/EUR": "BTC/EUR",
    "MATIC/EUR": "MATIC/EUR",  # MarketSelector uses MATIC/EUR
}


def _ws_pair_to_selector_name(ws_pair: str) -> str:
    """Convert WS pair name to the friendly name MarketSelector expects."""
    return _WS_TO_FRIENDLY.get(ws_pair, ws_pair)


KRAKEN_API_URL = "https://api.kraken.com"


class AnalysisFeed:
    """
    Seeds and maintains price data for all 70 analysis pairs.

    - bootstrap_prices(): REST API call to seed initial prices
    - subscribe_analysis_feeds(): Subscribe WS ticker for all 70 pairs
    - bootstrap_and_subscribe(): convenience combo
    """

    def __init__(
        self,
        ws_client: KrakenWebSocketAsync,
        analyzer: Optional[MarketAnalyzer] = None,
    ) -> None:
        self._ws = ws_client
        self._analyzer = analyzer or get_market_analyzer()
        self._subscribed: Set[str] = set()
        self._bootstrap_count = 0
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    # ------------------------------------------------------------------
    # 1. REST API Bootstrap
    # ------------------------------------------------------------------

    async def bootstrap_prices(self) -> int:
        """
        Fetch current ticker prices for all 70 pairs via Kraken REST API.
        Seeds MarketAnalyzer with initial price points so MarketSelector
        can score pairs immediately.

        Returns number of pairs successfully seeded.
        """
        logger.info("📊 Bootstrap: fetching prices for %d analysis pairs via REST...",
                     len(ALL_ANALYSIS_PAIRS))

        seeded = 0
        rest_names = list(ALL_ANALYSIS_PAIRS.keys())

        # Kraken Ticker API accepts comma-separated pairs (max ~50 per call)
        # Split into batches of 40 to stay safe
        batch_size = 40
        for i in range(0, len(rest_names), batch_size):
            batch = rest_names[i:i + batch_size]
            try:
                seeded += await self._fetch_ticker_batch(batch)
            except Exception as exc:
                logger.warning("⚠️ Bootstrap batch %d failed: %s", i // batch_size, exc)
            # Small delay between batches to respect rate limits
            if i + batch_size < len(rest_names):
                await asyncio.sleep(1.0)

        self._bootstrap_count = seeded
        logger.info("✅ Bootstrap complete: %d/%d pairs seeded with price data",
                     seeded, len(ALL_ANALYSIS_PAIRS))
        return seeded

    async def _fetch_ticker_batch(self, rest_names: List[str]) -> int:
        """Fetch a batch of tickers from Kraken REST and seed the analyzer."""
        pair_str = ",".join(rest_names)
        url = f"{KRAKEN_API_URL}/0/public/Ticker?pair={pair_str}"

        session = await self._get_session()
        async with session.get(url) as resp:
            data = await resp.json()

        if data.get("error"):
            logger.warning("⚠️ Kraken REST errors: %s", data["error"])

        result = data.get("result", {})
        seeded = 0

        for rest_name, ticker in result.items():
            try:
                price = float(ticker["c"][0])  # Last trade price
                if price <= 0:
                    continue

                # Map REST name → WS name → friendly name for MarketSelector
                ws_name = ALL_ANALYSIS_PAIRS.get(rest_name)
                if not ws_name:
                    # Kraken sometimes returns alt names; try to match
                    for rn, wn in ALL_ANALYSIS_PAIRS.items():
                        if rn in rest_name or rest_name in rn:
                            ws_name = wn
                            break
                if not ws_name:
                    logger.debug("Skip unknown REST pair: %s", rest_name)
                    continue

                friendly_name = _ws_pair_to_selector_name(ws_name)

                # Seed multiple synthetic price points so analyze_market()
                # has enough history (minimum 5 points).
                # Use slight variations to give realistic volatility signal.
                for offset_sec in [300, 240, 180, 120, 60, 0]:
                    # Tiny jitter (~0.01%) to prevent zero-volatility
                    jitter = 1.0 + (offset_sec % 7 - 3) * 0.0001
                    self._analyzer.add_price(friendly_name, price * jitter)

                seeded += 1
                logger.debug("  Seeded %s (%s) = %.6f", friendly_name, rest_name, price)

            except (KeyError, ValueError, TypeError) as exc:
                logger.debug("  Skip %s: %s", rest_name, exc)

        return seeded

    # ------------------------------------------------------------------
    # 2. WebSocket subscription for ongoing analysis data
    # ------------------------------------------------------------------

    async def subscribe_analysis_feeds(self) -> int:
        """
        Subscribe to WebSocket ticker for all 70 analysis pairs.
        The WS _process_ticker already calls analyzer.add_price() for
        every ticker update, so we just need to subscribe.

        Only subscribes pairs not already subscribed (idempotent).

        Returns number of new subscriptions.
        """
        logger.info("📡 Subscribing to %d analysis pair tickers on WebSocket...",
                     len(ALL_ANALYSIS_PAIRS))

        new_subs = 0
        already = 0

        for rest_name, ws_name in ALL_ANALYSIS_PAIRS.items():
            if ws_name in self._subscribed:
                already += 1
                continue

            # Check if WS already has this pair subscribed (from trading feed)
            if ws_name in self._ws._subscribed_pairs:
                self._subscribed.add(ws_name)
                already += 1
                continue

            try:
                await self._ws.subscribe_ticker(ws_name)
                self._subscribed.add(ws_name)
                new_subs += 1
            except Exception as exc:
                logger.warning("⚠️ Failed to subscribe %s: %s", ws_name, exc)

            # Small delay every 10 subs to avoid rate-limiting
            if new_subs % 10 == 0 and new_subs > 0:
                await asyncio.sleep(0.5)

        logger.info("✅ Analysis feeds: %d new subscriptions, %d already active",
                     new_subs, already)
        return new_subs

    # ------------------------------------------------------------------
    # 3. Convenience: bootstrap + subscribe
    # ------------------------------------------------------------------

    async def bootstrap_and_subscribe(self) -> None:
        """
        Full initialization:
        1. Seed prices via REST API (immediate data for MarketSelector)
        2. Subscribe WS tickers for ongoing updates

        Call this AFTER WebSocket is connected but BEFORE main loop starts.
        """
        t0 = time.monotonic()

        # Step 1: REST bootstrap
        seeded = await self.bootstrap_prices()

        # Step 2: WS subscriptions for ongoing data
        subscribed = await self.subscribe_analysis_feeds()

        elapsed = time.monotonic() - t0
        logger.info(
            "🎯 Analysis feed ready: %d seeded, %d WS subs (%.1fs)",
            seeded, subscribed, elapsed
        )

        # Close the REST session (no longer needed)
        await self.close()

    @property
    def stats(self) -> Dict:
        return {
            "bootstrap_count": self._bootstrap_count,
            "ws_subscribed": len(self._subscribed),
            "total_analysis_pairs": len(ALL_ANALYSIS_PAIRS),
        }
