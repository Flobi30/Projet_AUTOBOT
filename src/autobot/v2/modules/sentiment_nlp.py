"""
Sentiment Analysis NLP — Analyse de sentiment pour signaux de trading.

Analyse le sentiment de marché à partir de textes (news, tweets, Reddit)
et génère un score de sentiment agrégé (-1 à +1).

Méthode : Lexicon-based avec pondération TF-IDF simplifiée.
  - Dictionnaire de mots financiers avec polarité
  - Détection de négation (inverse le sentiment)
  - Amplificateurs et réducteurs ("very bullish" vs "slightly bullish")
  - Score EMA temporel (les textes récents pèsent plus)

Pas de dépendance ML lourde — utilise un lexique intégré.
Pour un modèle BERT/FinBERT, voir cnn_lstm_predictor.py.

Thread-safe (RLock), O(n) par texte (n = nombre de mots).

Usage:
    from autobot.v2.modules.sentiment_nlp import SentimentAnalyzer

    analyzer = SentimentAnalyzer()
    score = analyzer.analyze("Bitcoin surges past 100k, massive bull run!")
    # score: {"sentiment": 0.82, "label": "bullish", "confidence": 0.75}

    analyzer.add_text("BTC crashes 20% in one hour", source="twitter")
    aggregate = analyzer.get_aggregate_sentiment()
    # aggregate: {"score": -0.3, "label": "bearish", "texts_analyzed": 42}
"""

from __future__ import annotations

import logging
import math
import re
import threading
import time
from collections import deque
from datetime import datetime, timezone, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------
# Financial sentiment lexicon (English + crypto slang)
# Scores: -1.0 (very bearish) to +1.0 (very bullish)
# ---------------------------------------------------------------
FINANCIAL_LEXICON: Dict[str, float] = {
    # Strong bullish
    "surge": 0.8, "surges": 0.8, "surging": 0.8,
    "moon": 0.9, "mooning": 0.9,
    "bullish": 0.8, "bull": 0.6,
    "rally": 0.7, "rallies": 0.7, "rallying": 0.7,
    "breakout": 0.7, "breakthrough": 0.7,
    "soar": 0.8, "soars": 0.8, "soaring": 0.8,
    "pump": 0.6, "pumping": 0.6, "pumped": 0.6,
    "ath": 0.8, "highs": 0.5, "high": 0.3,
    "profit": 0.5, "profits": 0.5, "profitable": 0.5,
    "gain": 0.5, "gains": 0.5, "gained": 0.5,
    "up": 0.3, "rise": 0.4, "rises": 0.4, "rising": 0.4,
    "green": 0.4, "recover": 0.5, "recovery": 0.5,
    "buy": 0.3, "buying": 0.3, "bought": 0.2,
    "accumulate": 0.4, "accumulation": 0.4,
    "outperform": 0.5, "upgrade": 0.5,
    "adoption": 0.6, "institutional": 0.4,
    "hodl": 0.3, "diamond": 0.3, "lambo": 0.4,

    # Moderate bullish
    "support": 0.3, "stable": 0.2, "consolidation": 0.1,
    "growth": 0.4, "growing": 0.4,
    "positive": 0.4, "optimistic": 0.5, "optimism": 0.5,
    "strong": 0.3, "strength": 0.3,

    # Strong bearish
    "crash": -0.9, "crashes": -0.9, "crashed": -0.9, "crashing": -0.9,
    "dump": -0.7, "dumping": -0.7, "dumped": -0.7,
    "bearish": -0.8, "bear": -0.6,
    "plunge": -0.8, "plunges": -0.8, "plunging": -0.8,
    "collapse": -0.9, "collapsed": -0.9,
    "tank": -0.7, "tanking": -0.7, "tanked": -0.7,
    "rekt": -0.8, "liquidated": -0.7, "liquidation": -0.7,
    "sell": -0.3, "selling": -0.4, "sold": -0.2,
    "selloff": -0.7, "panic": -0.8,
    "fear": -0.6, "fearful": -0.6,
    "scam": -0.8, "fraud": -0.9, "hack": -0.8, "hacked": -0.8,
    "ban": -0.7, "banned": -0.7, "regulation": -0.3,
    "red": -0.4, "loss": -0.5, "losses": -0.5,
    "down": -0.3, "drop": -0.5, "drops": -0.5, "dropped": -0.5,
    "decline": -0.5, "declining": -0.5,
    "weak": -0.4, "weakness": -0.4,
    "bubble": -0.6, "ponzi": -0.9,
    "fud": -0.5, "rug": -0.9, "rugpull": -0.9,

    # Moderate bearish
    "resistance": -0.2, "overbought": -0.3, "overvalued": -0.4,
    "correction": -0.3, "pullback": -0.2,
    "risk": -0.3, "risky": -0.4, "volatile": -0.2, "volatility": -0.1,
    "uncertainty": -0.3, "uncertain": -0.3,
    "warning": -0.4, "caution": -0.3,
    "downgrade": -0.5,
}

# Negation words (invert sentiment of next word)
NEGATION_WORDS = frozenset([
    "not", "no", "never", "neither", "nobody", "nothing",
    "nowhere", "nor", "cannot", "can't", "won't", "don't",
    "doesn't", "didn't", "isn't", "aren't", "wasn't", "weren't",
    "hasn't", "haven't", "hadn't", "shouldn't", "wouldn't",
    "couldn't", "without", "barely", "hardly", "scarcely",
])

# Amplifiers (multiply sentiment)
AMPLIFIERS: Dict[str, float] = {
    "very": 1.5, "extremely": 2.0, "incredibly": 1.8,
    "huge": 1.5, "massive": 1.7, "enormous": 1.7,
    "absolutely": 1.8, "totally": 1.5, "completely": 1.5,
    "super": 1.4, "mega": 1.5, "ultra": 1.5,
}

# Reducers (dampen sentiment)
REDUCERS: Dict[str, float] = {
    "slightly": 0.5, "somewhat": 0.6, "marginally": 0.4,
    "barely": 0.3, "little": 0.5, "minor": 0.5,
    "modest": 0.6, "moderate": 0.7,
}


class SentimentAnalyzer:
    """
    Analyseur de sentiment financier basé sur un lexique.

    Analyse des textes et maintient un score de sentiment agrégé
    avec décroissance temporelle (EMA).

    Args:
        ema_alpha: Facteur de lissage EMA pour le score agrégé. Défaut 0.1.
        max_history: Nombre max de textes en historique. Défaut 500.
        decay_hours: Demi-vie en heures pour la pondération temporelle. Défaut 6.
        min_confidence: Confiance minimum pour considérer un signal. Défaut 0.3.
    """

    def __init__(
        self,
        ema_alpha: float = 0.1,
        max_history: int = 500,
        decay_hours: float = 6.0,
        min_confidence: float = 0.3,
    ) -> None:
        self._lock = threading.RLock()
        self._ema_alpha = ema_alpha
        self._max_history = max_history
        self._decay_hours = decay_hours
        self._min_confidence = min_confidence

        # Historique des analyses
        self._history: deque = deque(maxlen=max_history)

        # Score agrégé (EMA)
        self._aggregate_score: float = 0.0
        self._texts_analyzed: int = 0

        # Stats par source
        self._source_counts: Dict[str, int] = {}
        self._source_scores: Dict[str, deque] = {}

        logger.info(
            f"SentimentAnalyzer initialisé: ema_alpha={ema_alpha}, "
            f"decay={decay_hours}h, max_history={max_history}"
        )

    # ------------------------------------------------------------------
    # Text analysis
    # ------------------------------------------------------------------

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """Tokenise un texte en mots normalisés."""
        # Lowercase et nettoyage
        text = text.lower()
        text = re.sub(r'[^a-z0-9\'\s-]', ' ', text)
        tokens = text.split()
        return [t.strip("'-") for t in tokens if len(t.strip("'-")) > 1]

    def analyze(self, text: str, source: str = "unknown") -> Dict[str, Any]:
        """
        Analyse le sentiment d'un texte.

        Args:
            text: Texte à analyser.
            source: Source du texte (twitter, reddit, news, etc.).

        Returns:
            Dict avec sentiment (-1 à +1), label, confidence.
        """
        if not text or not text.strip():
            return {
                "sentiment": 0.0,
                "label": "neutral",
                "confidence": 0.0,
                "word_count": 0,
                "matched_words": 0,
            }

        tokens = self._tokenize(text)
        if not tokens:
            return {
                "sentiment": 0.0,
                "label": "neutral",
                "confidence": 0.0,
                "word_count": 0,
                "matched_words": 0,
            }

        scores = []
        matched_words = 0
        negation_active = False
        amplifier = 1.0

        for i, token in enumerate(tokens):
            # Check negation
            if token in NEGATION_WORDS:
                negation_active = True
                continue

            # Check amplifier/reducer
            if token in AMPLIFIERS:
                amplifier = AMPLIFIERS[token]
                continue
            if token in REDUCERS:
                amplifier = REDUCERS[token]
                continue

            # Check lexicon
            if token in FINANCIAL_LEXICON:
                score = FINANCIAL_LEXICON[token] * amplifier
                if negation_active:
                    score *= -0.8  # Negation doesn't fully invert
                scores.append(score)
                matched_words += 1

            # Reset modifiers
            negation_active = False
            amplifier = 1.0

        # Calculate final score
        if not scores:
            sentiment = 0.0
            confidence = 0.0
        else:
            sentiment = sum(scores) / len(scores)
            # Confidence = ratio of matched words * strength of scores
            match_ratio = matched_words / len(tokens)
            avg_abs = sum(abs(s) for s in scores) / len(scores)
            confidence = min(1.0, match_ratio * 2.0) * avg_abs

        # Clamp
        sentiment = max(-1.0, min(1.0, sentiment))
        confidence = max(0.0, min(1.0, confidence))

        # Label
        if sentiment > 0.2:
            label = "bullish"
        elif sentiment < -0.2:
            label = "bearish"
        else:
            label = "neutral"

        return {
            "sentiment": round(sentiment, 4),
            "label": label,
            "confidence": round(confidence, 4),
            "word_count": len(tokens),
            "matched_words": matched_words,
        }

    # ------------------------------------------------------------------
    # Aggregate tracking
    # ------------------------------------------------------------------

    def add_text(self, text: str, source: str = "unknown", weight: float = 1.0) -> Dict[str, Any]:
        """
        Analyse un texte et l'ajoute à l'historique agrégé.

        Args:
            text: Texte à analyser.
            source: Source du texte.
            weight: Poids du texte (1.0 = normal).

        Returns:
            Résultat de l'analyse.
        """
        result = self.analyze(text, source)

        with self._lock:
            now = time.time()

            entry = {
                "time": now,
                "sentiment": result["sentiment"],
                "confidence": result["confidence"],
                "source": source,
                "weight": weight,
                "label": result["label"],
            }
            self._history.append(entry)
            self._texts_analyzed += 1

            # Update EMA
            weighted_score = result["sentiment"] * weight
            self._aggregate_score = (
                self._ema_alpha * weighted_score +
                (1 - self._ema_alpha) * self._aggregate_score
            )

            # Stats par source
            if source not in self._source_counts:
                self._source_counts[source] = 0
                self._source_scores[source] = deque(maxlen=100)
            self._source_counts[source] += 1
            self._source_scores[source].append(result["sentiment"])

        return result

    def get_aggregate_sentiment(self) -> Dict[str, Any]:
        """
        Retourne le sentiment agrégé avec pondération temporelle.

        Les textes récents pèsent plus que les anciens (décroissance
        exponentielle basée sur decay_hours).
        """
        with self._lock:
            if not self._history:
                return {
                    "score": 0.0,
                    "label": "neutral",
                    "confidence": 0.0,
                    "texts_analyzed": 0,
                    "ema_score": round(self._aggregate_score, 4),
                }

            now = time.time()
            decay_rate = math.log(2) / (self._decay_hours * 3600)

            weighted_sum = 0.0
            weight_total = 0.0

            for entry in self._history:
                age = now - entry["time"]
                time_weight = math.exp(-decay_rate * age)
                w = time_weight * entry["weight"] * entry["confidence"]
                weighted_sum += entry["sentiment"] * w
                weight_total += w

            if weight_total > 0:
                score = weighted_sum / weight_total
            else:
                score = 0.0

            score = max(-1.0, min(1.0, score))

            # Confidence = weighted average confidence
            conf_sum = sum(e["confidence"] for e in self._history)
            avg_conf = conf_sum / len(self._history) if self._history else 0.0

            if score > 0.2:
                label = "bullish"
            elif score < -0.2:
                label = "bearish"
            else:
                label = "neutral"

            return {
                "score": round(score, 4),
                "label": label,
                "confidence": round(avg_conf, 4),
                "texts_analyzed": self._texts_analyzed,
                "history_size": len(self._history),
                "ema_score": round(self._aggregate_score, 4),
            }

    def get_source_breakdown(self) -> Dict[str, Any]:
        """Retourne les stats de sentiment par source."""
        with self._lock:
            breakdown = {}
            for source, scores in self._source_scores.items():
                if scores:
                    avg = sum(scores) / len(scores)
                    breakdown[source] = {
                        "count": self._source_counts.get(source, 0),
                        "avg_sentiment": round(avg, 4),
                        "recent_count": len(scores),
                    }
            return breakdown

    def is_signal(self, threshold: float = 0.4) -> Optional[str]:
        """
        Vérifie si le sentiment agrégé constitue un signal.

        Args:
            threshold: Seuil absolu pour considérer un signal.

        Returns:
            "bullish", "bearish", ou None.
        """
        with self._lock:
            if abs(self._aggregate_score) >= threshold:
                return "bullish" if self._aggregate_score > 0 else "bearish"
            return None

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        """Retourne l'état complet du module."""
        with self._lock:
            return {
                "module": "sentiment_nlp",
                "aggregate_score": round(self._aggregate_score, 4),
                "texts_analyzed": self._texts_analyzed,
                "history_size": len(self._history),
                "sources": dict(self._source_counts),
                "config": {
                    "ema_alpha": self._ema_alpha,
                    "decay_hours": self._decay_hours,
                    "min_confidence": self._min_confidence,
                    "max_history": self._max_history,
                },
                "lexicon_size": len(FINANCIAL_LEXICON),
            }

    def reset(self) -> None:
        """Réinitialise le module."""
        with self._lock:
            self._history.clear()
            self._aggregate_score = 0.0
            self._texts_analyzed = 0
            self._source_counts.clear()
            self._source_scores.clear()
            logger.info("SentimentAnalyzer réinitialisé")