"""
Vote Multi-Indicateurs — Système de vote pondéré entre indicateurs.

Chaque indicateur (RSI, MACD, Bollinger, Momentum, ATR...) émet un
vote (BUY, SELL, NEUTRAL) avec un niveau de confiance. Le système
agrège les votes pour produire un signal consensus.

Règles :
  - Unanimité = signal fort (confidence > 0.8)
  - Majorité simple = signal modéré (confidence 0.5-0.8)
  - Pas de majorité = NEUTRAL

Thread-safe (RLock), O(N) avec N = nombre d'indicateurs (petit, ~10).

Usage:
    from autobot.v2.modules.multi_indicator_vote import MultiIndicatorVoter

    voter = MultiIndicatorVoter()
    voter.register_indicator("rsi", weight=1.5)
    voter.submit_vote("rsi", "BUY", confidence=0.8)
    result = voter.tally()
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Votes possibles
VOTE_BUY = "BUY"
VOTE_SELL = "SELL"
VOTE_NEUTRAL = "NEUTRAL"


class MultiIndicatorVoter:
    """
    Système de vote multi-indicateurs pondéré.

    Chaque indicateur a un poids et émet un vote avec confiance.
    Le résultat est un signal consensus avec score de confiance global.

    Args:
        min_votes_required: Nombre minimum de votes pour un signal valide. Défaut 3.
        unanimity_threshold: Seuil pour unanimité (ratio). Défaut 0.8.
        expiry_ticks: Nombre de ticks avant expiration d'un vote. Défaut 50.
    """

    def __init__(
        self,
        min_votes_required: int = 3,
        unanimity_threshold: float = 0.8,
        expiry_ticks: int = 50,
    ) -> None:
        self._lock = threading.RLock()
        self._min_votes = min_votes_required
        self._unanimity_threshold = unanimity_threshold
        self._expiry_ticks = expiry_ticks

        # Indicateurs enregistrés : {name: {"weight": float, "enabled": bool}}
        self._indicators: Dict[str, Dict[str, Any]] = {}

        # Votes courants : {name: {"vote": str, "confidence": float, "tick": int, "reason": str}}
        self._votes: Dict[str, Dict[str, Any]] = {}

        # Tick counter
        self._tick_count: int = 0

        # Historique des résultats
        self._history: List[Dict[str, Any]] = []
        self._max_history = 100

        logger.info(
            "MultiIndicatorVoter initialisé — min_votes=%d, unanimity=%.0f%%",
            min_votes_required, unanimity_threshold * 100,
        )

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def register_indicator(
        self, name: str, weight: float = 1.0, enabled: bool = True
    ) -> None:
        """Enregistre un indicateur avec son poids."""
        with self._lock:
            self._indicators[name] = {"weight": weight, "enabled": enabled}
            logger.info("📊 Indicateur '%s' enregistré (poids=%.2f)", name, weight)

    def enable_indicator(self, name: str) -> None:
        """Active un indicateur."""
        with self._lock:
            if name in self._indicators:
                self._indicators[name]["enabled"] = True

    def disable_indicator(self, name: str) -> None:
        """Désactive un indicateur."""
        with self._lock:
            if name in self._indicators:
                self._indicators[name]["enabled"] = False

    # ------------------------------------------------------------------
    # Soumission de votes
    # ------------------------------------------------------------------

    def submit_vote(
        self,
        indicator_name: str,
        vote: str,
        confidence: float = 1.0,
        reason: str = "",
    ) -> None:
        """
        Soumet un vote pour un indicateur.

        Args:
            indicator_name: Nom de l'indicateur.
            vote: "BUY", "SELL", ou "NEUTRAL".
            confidence: Confiance du vote (0.0-1.0).
            reason: Raison textuelle du vote.
        """
        if vote not in (VOTE_BUY, VOTE_SELL, VOTE_NEUTRAL):
            logger.warning("Vote invalide ignoré: %s de %s", vote, indicator_name)
            return

        confidence = max(0.0, min(1.0, confidence))

        with self._lock:
            # Auto-register si pas encore connu
            if indicator_name not in self._indicators:
                self._indicators[indicator_name] = {"weight": 1.0, "enabled": True}

            self._votes[indicator_name] = {
                "vote": vote,
                "confidence": confidence,
                "tick": self._tick_count,
                "reason": reason,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    def tick(self) -> None:
        """Avance le compteur de ticks (pour expiration des votes)."""
        with self._lock:
            self._tick_count += 1

    # ------------------------------------------------------------------
    # Décompte des votes
    # ------------------------------------------------------------------

    def tally(self) -> Dict[str, Any]:
        """
        Effectue le décompte des votes et retourne le consensus.

        Returns:
            Dict avec:
            - signal: "BUY", "SELL", ou "NEUTRAL"
            - confidence: float (0-1)
            - votes_for: int
            - votes_against: int
            - votes_neutral: int
            - total_voters: int
            - details: dict per-indicator
            - strength: "strong", "moderate", "weak"
        """
        with self._lock:
            active_votes = self._get_active_votes()

            if len(active_votes) < self._min_votes:
                result = {
                    "signal": VOTE_NEUTRAL,
                    "confidence": 0.0,
                    "votes_for": 0,
                    "votes_against": 0,
                    "votes_neutral": len(active_votes),
                    "total_voters": len(active_votes),
                    "details": active_votes,
                    "strength": "insufficient",
                    "reason": f"Pas assez de votes ({len(active_votes)}/{self._min_votes})",
                }
                self._history.append(result)
                if len(self._history) > self._max_history:
                    self._history.pop(0)
                return result

            # Calcul des scores pondérés
            buy_score = 0.0
            sell_score = 0.0
            neutral_score = 0.0
            total_weight = 0.0

            buy_count = 0
            sell_count = 0
            neutral_count = 0

            for name, vote_data in active_votes.items():
                ind = self._indicators.get(name, {"weight": 1.0, "enabled": True})
                if not ind["enabled"]:
                    continue

                weight = ind["weight"]
                conf = vote_data["confidence"]
                weighted = weight * conf
                total_weight += weight

                if vote_data["vote"] == VOTE_BUY:
                    buy_score += weighted
                    buy_count += 1
                elif vote_data["vote"] == VOTE_SELL:
                    sell_score += weighted
                    sell_count += 1
                else:
                    neutral_score += weighted
                    neutral_count += 1

            if total_weight == 0:
                signal = VOTE_NEUTRAL
                confidence = 0.0
            else:
                buy_ratio = buy_score / total_weight
                sell_ratio = sell_score / total_weight

                if buy_ratio > sell_ratio and buy_ratio > 0.5:
                    signal = VOTE_BUY
                    confidence = buy_ratio
                elif sell_ratio > buy_ratio and sell_ratio > 0.5:
                    signal = VOTE_SELL
                    confidence = sell_ratio
                else:
                    signal = VOTE_NEUTRAL
                    confidence = max(buy_ratio, sell_ratio)

            # Calcul de la force
            total_directional = buy_count + sell_count
            if total_directional > 0:
                majority = max(buy_count, sell_count) / total_directional
            else:
                majority = 0.0

            if majority >= self._unanimity_threshold and confidence >= 0.7:
                strength = "strong"
            elif majority >= 0.6 and confidence >= 0.5:
                strength = "moderate"
            else:
                strength = "weak"

            result = {
                "signal": signal,
                "confidence": round(confidence, 3),
                "votes_for": buy_count if signal == VOTE_BUY else sell_count,
                "votes_against": sell_count if signal == VOTE_BUY else buy_count,
                "votes_neutral": neutral_count,
                "total_voters": buy_count + sell_count + neutral_count,
                "buy_score": round(buy_score, 3),
                "sell_score": round(sell_score, 3),
                "details": active_votes,
                "strength": strength,
                "tick": self._tick_count,
            }

            self._history.append(result)
            if len(self._history) > self._max_history:
                self._history.pop(0)

            return result

    def get_last_result(self) -> Optional[Dict[str, Any]]:
        """Retourne le dernier résultat de tally."""
        with self._lock:
            return self._history[-1] if self._history else None

    def get_status(self) -> Dict[str, Any]:
        """Retourne l'état du voter."""
        with self._lock:
            return {
                "registered_indicators": len(self._indicators),
                "active_votes": len(self._get_active_votes()),
                "tick_count": self._tick_count,
                "history_size": len(self._history),
                "indicators": {
                    name: {
                        "weight": ind["weight"],
                        "enabled": ind["enabled"],
                        "has_vote": name in self._votes,
                    }
                    for name, ind in self._indicators.items()
                },
            }

    def reset(self) -> None:
        """Réinitialise le voter."""
        with self._lock:
            self._votes.clear()
            self._history.clear()
            self._tick_count = 0
            logger.info("MultiIndicatorVoter: réinitialisé")

    # ------------------------------------------------------------------
    # Méthodes privées
    # ------------------------------------------------------------------

    def _get_active_votes(self) -> Dict[str, Dict[str, Any]]:
        """Retourne les votes non-expirés."""
        active = {}
        for name, vote_data in self._votes.items():
            if self._tick_count - vote_data["tick"] <= self._expiry_ticks:
                active[name] = vote_data
        return active


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

    print("\n🧪 Tests MultiIndicatorVoter")
    print("=" * 50)

    voter = MultiIndicatorVoter(min_votes_required=3)

    # Test 1: Init
    assert_test("Init OK", voter._tick_count == 0)

    # Test 2: Register indicators
    voter.register_indicator("rsi", weight=1.5)
    voter.register_indicator("macd", weight=1.0)
    voter.register_indicator("bollinger", weight=1.0)
    voter.register_indicator("momentum", weight=0.8)
    assert_test("4 indicateurs enregistrés", len(voter._indicators) == 4)

    # Test 3: Not enough votes → NEUTRAL
    voter.submit_vote("rsi", VOTE_BUY, confidence=0.9)
    result = voter.tally()
    assert_test("Pas assez de votes = insufficient", result["strength"] == "insufficient")

    # Test 4: Unanimous BUY
    voter.submit_vote("rsi", VOTE_BUY, confidence=0.9)
    voter.submit_vote("macd", VOTE_BUY, confidence=0.8)
    voter.submit_vote("bollinger", VOTE_BUY, confidence=0.7)
    voter.submit_vote("momentum", VOTE_BUY, confidence=0.85)
    result = voter.tally()
    assert_test("Unanimité BUY", result["signal"] == VOTE_BUY)
    assert_test("Signal fort", result["strength"] == "strong")
    assert_test("Confidence > 0.7", result["confidence"] > 0.7)

    # Test 5: Mixed votes
    voter.submit_vote("rsi", VOTE_BUY, confidence=0.9)
    voter.submit_vote("macd", VOTE_SELL, confidence=0.8)
    voter.submit_vote("bollinger", VOTE_NEUTRAL, confidence=0.5)
    voter.submit_vote("momentum", VOTE_BUY, confidence=0.6)
    result = voter.tally()
    assert_test("Votes mixtes = weak ou moderate", result["strength"] in ("weak", "moderate"))

    # Test 6: Unanimous SELL
    voter.submit_vote("rsi", VOTE_SELL, confidence=0.85)
    voter.submit_vote("macd", VOTE_SELL, confidence=0.9)
    voter.submit_vote("bollinger", VOTE_SELL, confidence=0.8)
    voter.submit_vote("momentum", VOTE_SELL, confidence=0.75)
    result = voter.tally()
    assert_test("Unanimité SELL", result["signal"] == VOTE_SELL)
    assert_test("SELL signal fort", result["strength"] == "strong")

    # Test 7: Vote expiry
    voter2 = MultiIndicatorVoter(min_votes_required=2, expiry_ticks=5)
    voter2.submit_vote("ind1", VOTE_BUY, confidence=0.9)
    voter2.submit_vote("ind2", VOTE_BUY, confidence=0.8)
    r = voter2.tally()
    assert_test("Votes valides", r["signal"] == VOTE_BUY)
    for _ in range(10):
        voter2.tick()
    r2 = voter2.tally()
    assert_test("Votes expirés", r2["strength"] == "insufficient")

    # Test 8: Weight influence
    voter3 = MultiIndicatorVoter(min_votes_required=2)
    voter3.register_indicator("heavy", weight=10.0)
    voter3.register_indicator("light", weight=0.1)
    voter3.submit_vote("heavy", VOTE_BUY, confidence=0.9)
    voter3.submit_vote("light", VOTE_SELL, confidence=0.9)
    r3 = voter3.tally()
    assert_test("Heavy weight domine", r3["signal"] == VOTE_BUY)

    # Test 9: Disable indicator
    voter.disable_indicator("momentum")
    voter.submit_vote("rsi", VOTE_BUY, confidence=0.9)
    voter.submit_vote("macd", VOTE_BUY, confidence=0.9)
    voter.submit_vote("bollinger", VOTE_BUY, confidence=0.9)
    voter.submit_vote("momentum", VOTE_SELL, confidence=0.9)  # disabled
    r4 = voter.tally()
    assert_test("Indicateur désactivé ignoré", r4["signal"] == VOTE_BUY)

    # Test 10: Status
    status = voter.get_status()
    assert_test("Status has registered_indicators", status["registered_indicators"] == 4)
    assert_test("Status has active_votes", "active_votes" in status)

    # Test 11: Thread safety
    import concurrent.futures
    ts_voter = MultiIndicatorVoter(min_votes_required=1)

    def submit_many(n):
        for i in range(n):
            ts_voter.submit_vote(f"ind_{i % 5}", VOTE_BUY, confidence=0.8)
            ts_voter.tick()
        return n

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(submit_many, 100) for _ in range(4)]
        [f.result() for f in futures]
    assert_test("Thread safety: tick_count = 400", ts_voter._tick_count == 400)

    # Test 12: Reset
    voter.reset()
    assert_test("Reset: 0 votes", len(voter._votes) == 0)
    assert_test("Reset: 0 history", len(voter._history) == 0)

    print(f"\n{'=' * 50}")
    print(f"Résultat: {passed}/{passed + failed} tests passés")
    sys.exit(0 if failed == 0 else 1)