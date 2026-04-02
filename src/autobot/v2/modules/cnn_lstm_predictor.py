"""
Heuristic Predictor — Module Phase 4 pour AutoBot V2

Prédiction directionnelle légère basée sur des heuristiques techniques
(momentum, RSI, moyennes mobiles). Pas de deep learning ni GPU requis,
tourne sur VPS 5€/mois.

Note: Ce module était historiquement nommé « CNN-LSTM Predictor » mais
n'utilise en réalité aucun réseau de neurones. Il a été renommé
HeuristicPredictor pour refléter fidèlement son implémentation.

Architecture:
- Feature engineering : rolling stats + indicateurs techniques simples
- Scoring : règles heuristiques pondérées (momentum, RSI, distance MA)
- Prédiction : probabilité haussière [0, 1]
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from dataclasses import dataclass
from typing import Optional

import math

logger = logging.getLogger(__name__)


@dataclass
class PredictionResult:
    """Résultat de prédiction."""
    probability_up: float  # 0.0 à 1.0
    confidence: float      # Niveau de confiance
    features_used: int     # Nombre de features utilisées


class HeuristicPredictor:
    """
    Prédicteur heuristique léger pour AutoBot V2.

    Utilise des règles techniques simples (momentum, RSI, distance aux
    moyennes mobiles) pour estimer la probabilité de hausse.
    Aucun modèle ML n'est entraîné — le scoring est déterministe.

    Pas de GPU requis, tourne sur VPS standard.

    Args:
        sequence_length: Taille de la séquence d'entrée (défaut 60)
        warmup_period: Période de warmup avant prédiction fiable
    """
    
    def __init__(self, sequence_length: int = 60, warmup_period: int = 100) -> None:
        if sequence_length < 20:
            raise ValueError("sequence_length doit être >= 20")
        
        self._sequence_length = sequence_length
        self._warmup_period = warmup_period
        self._lock = threading.RLock()
        
        # Historique des prix
        self._prices: deque[float] = deque(maxlen=sequence_length)
        self._volumes: deque[float] = deque(maxlen=sequence_length)
        
        # Compteurs
        self._update_count = 0
        self._prediction_count = 0
        
        logger.info("HeuristicPredictor initialisé — sequence=%d, warmup=%d",
                   sequence_length, warmup_period)
    
    def update(self, price: float, volume: float = 0.0) -> None:
        """Met à jour avec un nouveau tick."""
        with self._lock:
            self._prices.append(price)
            self._volumes.append(volume)
            self._update_count += 1
    
    def predict(self) -> Optional[PredictionResult]:
        """
        Prédit la direction probable.
        
        Returns:
            PredictionResult si assez de données, None sinon
        """
        with self._lock:
            if len(self._prices) < self._sequence_length:
                return None
            
            if self._update_count < self._warmup_period:
                return None
            
            # Feature engineering simple
            features = self._extract_features()
            
            # Prédiction basée sur momentum + tendance
            prob_up = self._calculate_probability(features)
            
            self._prediction_count += 1
            
            return PredictionResult(
                probability_up=prob_up,
                confidence=features['confidence'],
                features_used=len(features)
            )
    
    def _extract_features(self) -> dict:
        """Extrait les features techniques."""
        prices = list(self._prices)
        
        # Returns
        returns = [(prices[i] - prices[i-1]) / prices[i-1] 
                   for i in range(1, len(prices))]
        
        # Moyennes mobiles
        sma_20 = sum(prices[-20:]) / 20
        sma_50 = sum(prices[-50:]) / 50 if len(prices) >= 50 else sma_20
        
        # Volatilité (std des returns)
        if len(returns) >= 20:
            mean_ret = sum(returns[-20:]) / 20
            variance = sum((r - mean_ret) ** 2 for r in returns[-20:]) / 20
            volatility = math.sqrt(variance)
        else:
            volatility = 0.0
        
        # Momentum
        momentum = (prices[-1] - prices[-20]) / prices[-20] if len(prices) >= 20 else 0.0
        
        # RSI simplifié
        gains = [r for r in returns if r > 0]
        losses = [-r for r in returns if r < 0]
        avg_gain = sum(gains[-14:]) / 14 if gains else 0.0
        avg_loss = sum(losses[-14:]) / 14 if losses else 0.0
        rs = avg_gain / avg_loss if avg_loss > 0 else float('inf')
        rsi = 100.0 - (100.0 / (1.0 + rs)) if rs != float('inf') else 100.0
        
        # Distance aux moyennes
        dist_sma20 = (prices[-1] - sma_20) / sma_20 if sma_20 > 0 else 0.0
        dist_sma50 = (prices[-1] - sma_50) / sma_50 if sma_50 > 0 else 0.0
        
        # Confiance basée sur volatilité et volume de données
        confidence = min(1.0, self._update_count / self._warmup_period)
        if volatility > 0.05:  # Forte volatilité = moins confiant
            confidence *= 0.8
        
        return {
            'sma_20': sma_20,
            'sma_50': sma_50,
            'volatility': volatility,
            'momentum': momentum,
            'rsi': rsi,
            'dist_sma20': dist_sma20,
            'dist_sma50': dist_sma50,
            'returns_mean': sum(returns[-20:]) / 20 if returns else 0.0,
            'confidence': confidence
        }
    
    def _calculate_probability(self, features: dict) -> float:
        """Calcule la probabilité haussière."""
        score = 0.0
        
        # Momentum positif
        if features['momentum'] > 0.02:
            score += 0.3
        elif features['momentum'] > 0:
            score += 0.1
        elif features['momentum'] < -0.02:
            score -= 0.3
        
        # Prix au-dessus des moyennes
        if features['dist_sma20'] > 0:
            score += 0.2
        if features['dist_sma50'] > 0:
            score += 0.2
        
        # RSI
        if features['rsi'] > 60:
            score += 0.2
        elif features['rsi'] < 40:
            score -= 0.2
        
        # Convertir en probabilité [0, 1]
        prob = 0.5 + score
        return max(0.0, min(1.0, prob))
    
    def get_status(self) -> dict:
        """Retourne l'état du prédicteur."""
        with self._lock:
            return {
                'sequence_length': self._sequence_length,
                'warmup_period': self._warmup_period,
                'updates': self._update_count,
                'predictions': self._prediction_count,
                'ready': self._update_count >= self._warmup_period,
                'data_points': len(self._prices)
            }
    
    def reset(self) -> None:
        """Réinitialise le prédicteur."""
        with self._lock:
            self._prices.clear()
            self._volumes.clear()
            self._update_count = 0
            self._prediction_count = 0
            logger.info("HeuristicPredictor réinitialisé")


# Backward-compatible alias
CNNLSTMPredictor = HeuristicPredictor


# ======================================================================
# Tests intégrés
# ======================================================================

if __name__ == "__main__":
    import random
    import sys
    
    logging.basicConfig(level=logging.INFO)
    
    passed = 0
    failed = 0
    
    def assert_true(name: str, cond: bool):
        global passed, failed
        if cond:
            passed += 1
            print(f"✅ {name}")
        else:
            failed += 1
            print(f"❌ {name}")
    
    # Test 1 : Initialisation
    print("\n=== Test 1 : Initialisation ===")
    pred = HeuristicPredictor(sequence_length=60, warmup_period=100)
    assert_true("Initialisation OK", pred is not None)
    
    # Test 2 : Pas de prédiction avant warmup
    print("\n=== Test 2 : Warmup ===")
    for i in range(50):
        pred.update(100.0 + i * 0.1, volume=1000.0)
    result = pred.predict()
    assert_true("Pas de prédiction avant warmup", result is None)
    
    # Test 3 : Prédiction après warmup (tendance haussière)
    print("\n=== Test 3 : Prédiction tendance haussière ===")
    for i in range(150):
        # Tendance haussière forte
        price = 100.0 + i * 0.5 + random.uniform(-0.5, 0.5)
        pred.update(price, volume=1000.0)
    result = pred.predict()
    assert_true("Prédiction retournée", result is not None)
    if result:
        assert_true("Probabilité dans [0,1]", 0 <= result.probability_up <= 1)
        assert_true("Confiance > 0", result.confidence > 0)
        print(f"   Probabilité haussière: {result.probability_up:.2f}")
    
    # Test 4 : Reset
    print("\n=== Test 4 : Reset ===")
    pred.reset()
    status = pred.get_status()
    assert_true("Reset OK", status['updates'] == 0)
    
    # Test 5 : Thread safety
    print("\n=== Test 5 : Thread safety ===")
    pred2 = HeuristicPredictor()
    errors = []
    
    def worker():
        try:
            for i in range(100):
                pred2.update(100.0 + random.uniform(-1, 1))
                pred2.predict()
        except Exception as e:
            errors.append(str(e))
    
    import threading
    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    
    assert_true("Pas d'erreur thread", len(errors) == 0)
    
    # Résumé
    print(f"\n{'='*50}")
    print(f"RÉSULTATS : {passed}/{passed+failed} passés")
    print(f"{'='*50}")
    
    sys.exit(0 if failed == 0 else 1)
