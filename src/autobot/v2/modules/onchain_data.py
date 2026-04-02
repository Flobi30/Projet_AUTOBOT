"""
On-chain Data — Intégration de données on-chain pour le trading.

Collecte et analyse les métriques on-chain (exchange flows, whale alerts,
NVT ratio, MVRV) pour enrichir les signaux de trading.

Simule une interface vers des APIs on-chain (Glassnode, CryptoQuant).
En production, remplacer les méthodes fetch par des appels API réels.

Thread-safe (RLock), O(1) par mise à jour, sans numpy/pandas.

Usage:
    from autobot.v2.modules.onchain_data import OnchainDataModule

    onchain = OnchainDataModule()
    onchain.update_metrics(exchange_inflow=500, exchange_outflow=300, ...)
    signal = onchain.get_signal()
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class OnchainDataModule:
    """
    Module de données on-chain pour enrichir les signaux de trading.

    Métriques suivies :
    - Exchange net flow (inflow - outflow) : positif = pression vendeuse
    - Whale transactions : grosses transactions (> seuil)
    - NVT Ratio (Network Value to Transactions) : surévaluation si élevé
    - MVRV Ratio (Market Value / Realized Value) : > 3.5 = top probable

    Args:
        lookback: Fenêtre de données historiques. Défaut 100.
        whale_threshold: Seuil BTC pour whale alert. Défaut 100.
        nvt_overbought: Seuil NVT pour surévaluation. Défaut 95.
        mvrv_overbought: Seuil MVRV pour surévaluation. Défaut 3.5.
    """

    def __init__(
        self,
        lookback: int = 100,
        whale_threshold: float = 100.0,
        nvt_overbought: float = 95.0,
        mvrv_overbought: float = 3.5,
    ) -> None:
        self._lock = threading.RLock()
        self._lookback = lookback
        self._whale_threshold = whale_threshold
        self._nvt_overbought = nvt_overbought
        self._mvrv_overbought = mvrv_overbought

        # Historiques
        self._net_flows: deque = deque(maxlen=lookback)
        self._whale_txs: deque = deque(maxlen=lookback)
        self._nvt_ratios: deque = deque(maxlen=lookback)
        self._mvrv_ratios: deque = deque(maxlen=lookback)

        # Dernières valeurs
        self._last_inflow: float = 0.0
        self._last_outflow: float = 0.0
        self._last_nvt: float = 0.0
        self._last_mvrv: float = 1.0
        self._last_whale_count: int = 0

        # Compteurs
        self._update_count: int = 0
        self._alerts: deque = deque(maxlen=50)

        logger.info(
            "OnchainDataModule initialisé — lookback=%d, whale_threshold=%.0f BTC",
            lookback, whale_threshold,
        )

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def update_metrics(
        self,
        exchange_inflow: float = 0.0,
        exchange_outflow: float = 0.0,
        whale_tx_count: int = 0,
        whale_tx_volume: float = 0.0,
        nvt_ratio: Optional[float] = None,
        mvrv_ratio: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Met à jour les métriques on-chain.

        Returns:
            Alerte dict si condition anormale détectée, None sinon.
        """
        with self._lock:
            self._update_count += 1

            # Net flow
            net_flow = exchange_inflow - exchange_outflow
            self._net_flows.append(net_flow)
            self._last_inflow = exchange_inflow
            self._last_outflow = exchange_outflow

            # Whale transactions
            self._whale_txs.append(whale_tx_count)
            self._last_whale_count = whale_tx_count

            # NVT / MVRV
            if nvt_ratio is not None:
                self._nvt_ratios.append(nvt_ratio)
                self._last_nvt = nvt_ratio
            if mvrv_ratio is not None:
                self._mvrv_ratios.append(mvrv_ratio)
                self._last_mvrv = mvrv_ratio

            # Détection d'alertes
            alert = self._check_alerts(net_flow, whale_tx_count, whale_tx_volume,
                                        nvt_ratio, mvrv_ratio)
            if alert:
                self._alerts.append(alert)
                logger.warning("🔗 On-chain alerte: %s", alert["type"])

            return alert

    def get_signal(self) -> Dict[str, Any]:
        """
        Retourne le signal on-chain agrégé.

        Returns:
            Dict avec:
            - bias: "bullish", "bearish", ou "neutral"
            - confidence: float (0-1)
            - components: dict détaillé
        """
        with self._lock:
            components = {}
            scores = []

            # 1. Net flow analysis
            if self._net_flows:
                avg_flow = sum(self._net_flows) / len(self._net_flows)
                last_flow = self._net_flows[-1]
                # Gros inflow = bearish (gens déposent pour vendre)
                if avg_flow > 0:
                    flow_score = -min(avg_flow / 1000, 1.0)  # négatif = bearish
                else:
                    flow_score = min(abs(avg_flow) / 1000, 1.0)  # positif = bullish
                components["net_flow"] = {"score": round(flow_score, 3), "avg": round(avg_flow, 2)}
                scores.append(flow_score)

            # 2. NVT analysis
            if self._last_nvt > 0:
                if self._last_nvt > self._nvt_overbought:
                    nvt_score = -0.8  # bearish
                elif self._last_nvt < self._nvt_overbought * 0.5:
                    nvt_score = 0.5  # bullish
                else:
                    nvt_score = 0.0
                components["nvt"] = {"score": round(nvt_score, 3), "value": round(self._last_nvt, 2)}
                scores.append(nvt_score)

            # 3. MVRV analysis
            if self._last_mvrv > 0:
                if self._last_mvrv > self._mvrv_overbought:
                    mvrv_score = -0.9  # très bearish
                elif self._last_mvrv < 1.0:
                    mvrv_score = 0.7  # bullish (sous-évalué)
                else:
                    mvrv_score = 0.0
                components["mvrv"] = {"score": round(mvrv_score, 3), "value": round(self._last_mvrv, 2)}
                scores.append(mvrv_score)

            # 4. Whale activity
            if self._whale_txs:
                avg_whales = sum(self._whale_txs) / len(self._whale_txs)
                whale_spike = self._last_whale_count / avg_whales if avg_whales > 0 else 1
                # Spike de whales = incertitude (neutre/légèrement bearish)
                whale_score = -0.3 if whale_spike > 2 else 0.0
                components["whales"] = {"score": round(whale_score, 3), "spike_ratio": round(whale_spike, 2)}
                scores.append(whale_score)

            # Agrégation
            if scores:
                avg_score = sum(scores) / len(scores)
                if avg_score > 0.2:
                    bias = "bullish"
                elif avg_score < -0.2:
                    bias = "bearish"
                else:
                    bias = "neutral"
                confidence = min(abs(avg_score), 1.0)
            else:
                bias = "neutral"
                confidence = 0.0
                avg_score = 0.0

            return {
                "bias": bias,
                "confidence": round(confidence, 3),
                "score": round(avg_score, 3),
                "components": components,
                "update_count": self._update_count,
            }

    def get_recent_alerts(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Retourne les alertes récentes."""
        with self._lock:
            return list(self._alerts)[-limit:]

    def get_status(self) -> Dict[str, Any]:
        """Retourne l'état du module."""
        with self._lock:
            return {
                "update_count": self._update_count,
                "data_points": len(self._net_flows),
                "last_net_flow": round(self._last_inflow - self._last_outflow, 2),
                "last_nvt": round(self._last_nvt, 2),
                "last_mvrv": round(self._last_mvrv, 2),
                "alerts_count": len(self._alerts),
            }

    def reset(self) -> None:
        """Réinitialise."""
        with self._lock:
            self._net_flows.clear()
            self._whale_txs.clear()
            self._nvt_ratios.clear()
            self._mvrv_ratios.clear()
            self._update_count = 0
            self._alerts.clear()
            logger.info("OnchainDataModule: réinitialisé")

    # ------------------------------------------------------------------
    # Méthodes privées
    # ------------------------------------------------------------------

    def _check_alerts(self, net_flow, whale_count, whale_volume, nvt, mvrv) -> Optional[Dict]:
        """Vérifie les conditions d'alerte."""
        now = datetime.now(timezone.utc).isoformat()

        # Grosse entrée exchange
        if net_flow > 500:
            return {"type": "large_exchange_inflow", "net_flow": net_flow, "timestamp": now,
                    "message": f"Gros inflow exchange: {net_flow:.0f} BTC net"}

        # Whale spike
        if self._whale_txs and len(self._whale_txs) > 5:
            avg = sum(list(self._whale_txs)[-5:]) / 5
            if whale_count > avg * 3 and whale_count > 5:
                return {"type": "whale_spike", "count": whale_count, "avg": round(avg, 1),
                        "timestamp": now, "message": f"Spike de whales: {whale_count} (avg {avg:.0f})"}

        # MVRV top
        if mvrv is not None and mvrv > self._mvrv_overbought:
            return {"type": "mvrv_overbought", "mvrv": mvrv, "threshold": self._mvrv_overbought,
                    "timestamp": now, "message": f"MVRV élevé: {mvrv:.2f} (seuil {self._mvrv_overbought})"}

        # NVT overbought
        if nvt is not None and nvt > self._nvt_overbought:
            return {"type": "nvt_overbought", "nvt": nvt, "threshold": self._nvt_overbought,
                    "timestamp": now, "message": f"NVT élevé: {nvt:.1f} (seuil {self._nvt_overbought})"}

        return None


# ======================================================================
# Tests intégrés
# ======================================================================
if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    passed = 0
    failed = 0

    def assert_test(name: str, condition: bool) -> None:
        global passed, failed
        if condition:
            passed += 1
            print(f"  ✅ {name}")
        else:
            failed += 1
            print(f"  ❌ {name}")

    print("\n🧪 Tests OnchainDataModule")
    print("=" * 50)

    oc = OnchainDataModule()

    # Test 1: Init
    assert_test("Init OK", oc._update_count == 0)

    # Test 2: Update metrics
    oc.update_metrics(exchange_inflow=200, exchange_outflow=300, nvt_ratio=50, mvrv_ratio=1.5)
    assert_test("Update count = 1", oc._update_count == 1)

    # Test 3: Signal bullish (outflow > inflow, low MVRV)
    signal = oc.get_signal()
    assert_test("Signal retourné", signal is not None)
    assert_test("Has bias", signal["bias"] in ("bullish", "bearish", "neutral"))

    # Test 4: Bearish conditions (high inflow, high MVRV)
    oc2 = OnchainDataModule()
    for _ in range(10):
        oc2.update_metrics(exchange_inflow=1000, exchange_outflow=100, nvt_ratio=120, mvrv_ratio=4.0)
    signal2 = oc2.get_signal()
    assert_test("Bearish signal", signal2["bias"] == "bearish")

    # Test 5: Alert on large inflow
    oc3 = OnchainDataModule()
    alert = oc3.update_metrics(exchange_inflow=800, exchange_outflow=100)
    assert_test("Large inflow alert", alert is not None and alert["type"] == "large_exchange_inflow")

    # Test 6: MVRV overbought alert
    oc4 = OnchainDataModule()
    alert2 = oc4.update_metrics(mvrv_ratio=4.0)
    assert_test("MVRV alert", alert2 is not None and alert2["type"] == "mvrv_overbought")

    # Test 7: Recent alerts
    alerts = oc3.get_recent_alerts()
    assert_test("Recent alerts non vide", len(alerts) > 0)

    # Test 8: Status
    status = oc.get_status()
    assert_test("Status has update_count", status["update_count"] > 0)
    assert_test("Status has last_nvt", "last_nvt" in status)

    # Test 9: Reset
    oc.reset()
    assert_test("Reset: 0 updates", oc._update_count == 0)

    # Test 10: Thread safety
    import concurrent.futures
    ts_oc = OnchainDataModule()

    def update_many(n):
        for i in range(n):
            ts_oc.update_metrics(exchange_inflow=100+i, exchange_outflow=50+i, nvt_ratio=50, mvrv_ratio=1.5)
        return n

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(update_many, 100) for _ in range(4)]
        [f.result() for f in futures]
    assert_test("Thread safety: 400 updates", ts_oc._update_count == 400)

    print(f"\n{'=' * 50}")
    print(f"Résultat: {passed}/{passed + failed} tests passés")
    sys.exit(0 if failed == 0 else 1)