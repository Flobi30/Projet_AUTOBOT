"""
XGBoost Auto-Activation — Prédicteur ML avec activation automatique.

Collecte des features (prix, volume, indicateurs techniques) et
entraîne/utilise un modèle XGBoost pour prédire la direction du prix.

Le modèle s'active automatiquement quand sa précision dépasse un seuil
sur les données de validation récentes.

Thread-safe (RLock). Utilise xgboost si disponible, sinon un fallback
basé sur un arbre de décision simpliste.

Usage:
    from autobot.v2.modules.xgboost_predictor import XGBoostPredictor

    predictor = XGBoostPredictor(min_accuracy=0.55)
    predictor.add_sample(features=[...], label=1)
    prediction = predictor.predict(features=[...])
"""

from __future__ import annotations

import logging
import math
import threading
from collections import deque
from datetime import datetime, timezone, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Tente d'importer xgboost
_HAS_XGBOOST = False
try:
    import xgboost as xgb
    _HAS_XGBOOST = True
except ImportError:
    pass


class XGBoostPredictor:
    """
    Prédicteur XGBoost avec auto-activation.

    Collecte des échantillons (features, label), entraîne un modèle
    quand suffisamment de données sont disponibles, et s'auto-active
    quand la précision dépasse le seuil.

    Args:
        min_samples: Minimum d'échantillons pour entraîner. Défaut 200.
        min_accuracy: Précision minimum pour activation. Défaut 0.55.
        retrain_interval: Nombre de nouveaux échantillons avant re-train. Défaut 100.
        max_samples: Taille max du dataset. Défaut 10000.
        feature_names: Noms des features (optionnel).
    """

    def __init__(
        self,
        min_samples: int = 200,
        min_accuracy: float = 0.55,
        retrain_interval: int = 100,
        max_samples: int = 10000,
        feature_names: Optional[List[str]] = None,
    ) -> None:
        self._lock = threading.RLock()
        self._min_samples = min_samples
        self._min_accuracy = min_accuracy
        self._retrain_interval = retrain_interval
        self._max_samples = max_samples
        self._feature_names = feature_names

        # Dataset
        self._features: deque = deque(maxlen=max_samples)
        self._labels: deque = deque(maxlen=max_samples)
        self._samples_since_train: int = 0

        # Modèle
        self._model: Any = None
        self._is_active: bool = False
        self._accuracy: float = 0.0
        self._train_count: int = 0

        # Prédictions
        self._prediction_count: int = 0
        self._correct_predictions: int = 0

        # Feature engineering incrémental
        self._price_history: deque = deque(maxlen=200)
        self._volume_history: deque = deque(maxlen=200)

        logger.info(
            "XGBoostPredictor initialisé — xgboost=%s, min_samples=%d, min_accuracy=%.2f",
            "OUI" if _HAS_XGBOOST else "NON (fallback)", min_samples, min_accuracy,
        )

    # ------------------------------------------------------------------
    # Feature engineering
    # ------------------------------------------------------------------

    def extract_features(self, price: float, volume: float = 0.0) -> Optional[List[float]]:
        """
        Extrait les features techniques à partir du prix et volume.

        Returns:
            Liste de features, ou None si pas assez de données.
        """
        with self._lock:
            self._price_history.append(price)
            if volume > 0:
                self._volume_history.append(volume)

            if len(self._price_history) < 50:
                return None

            prices = list(self._price_history)
            n = len(prices)

            # ROC (Rate of Change) multi-fenêtre
            roc_5 = (prices[-1] - prices[-6]) / prices[-6] if n > 5 and prices[-6] != 0 else 0
            roc_10 = (prices[-1] - prices[-11]) / prices[-11] if n > 10 and prices[-11] != 0 else 0
            roc_20 = (prices[-1] - prices[-21]) / prices[-21] if n > 20 and prices[-21] != 0 else 0

            # MA ratios
            ma_10 = sum(prices[-10:]) / 10
            ma_20 = sum(prices[-20:]) / 20 if n >= 20 else ma_10
            ma_50 = sum(prices[-50:]) / 50 if n >= 50 else ma_20
            ma_ratio_10_20 = ma_10 / ma_20 if ma_20 != 0 else 1.0
            ma_ratio_10_50 = ma_10 / ma_50 if ma_50 != 0 else 1.0

            # Volatilité
            if n >= 20:
                recent = prices[-20:]
                mean = sum(recent) / 20
                var = sum((p - mean) ** 2 for p in recent) / 20
                volatility = math.sqrt(var) / mean if mean != 0 else 0
            else:
                volatility = 0

            # RSI simplifié
            gains = []
            losses = []
            for i in range(-14, 0):
                if n + i > 0:
                    change = prices[i] - prices[i - 1]
                    gains.append(max(change, 0))
                    losses.append(max(-change, 0))
            avg_gain = sum(gains) / len(gains) if gains else 0
            avg_loss = sum(losses) / len(losses) if losses else 0
            rs = avg_gain / avg_loss if avg_loss > 0 else 100
            rsi = 100 - (100 / (1 + rs))

            # Volume ratio
            vol_ratio = 1.0
            if self._volume_history and len(self._volume_history) >= 10:
                vols = list(self._volume_history)
                avg_vol = sum(vols[-10:]) / 10
                vol_ratio = vols[-1] / avg_vol if avg_vol > 0 else 1.0

            features = [
                roc_5, roc_10, roc_20,
                ma_ratio_10_20, ma_ratio_10_50,
                volatility,
                rsi / 100.0,  # normalisé 0-1
                vol_ratio,
            ]

            return features

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def add_sample(self, features: List[float], label: int) -> None:
        """
        Ajoute un échantillon d'entraînement.

        Args:
            features: Vecteur de features.
            label: 1 = prix monte, 0 = prix baisse.
        """
        need_train = False
        with self._lock:
            self._features.append(features)
            self._labels.append(label)
            self._samples_since_train += 1

            # Auto-train si assez de données
            if (
                len(self._features) >= self._min_samples
                and self._samples_since_train >= self._retrain_interval
            ):
                need_train = True

        if need_train:
            self._train()

    def _train(self) -> None:
        """
        Entraîne le modèle.

        Le lock est pris brièvement pour copier les données, relâché
        pendant l'entraînement (potentiellement long), puis repris pour
        stocker le modèle résultant.
        """
        # --- 1. Copie des données sous lock ---
        with self._lock:
            n = len(self._features)
            if n < self._min_samples:
                return
            features_list = list(self._features)
            labels_list = list(self._labels)
            was_active = self._is_active

        # --- 2. Entraînement HORS lock ---
        # Split train/val (80/20)
        split = int(n * 0.8)
        train_X = features_list[:split]
        train_y = labels_list[:split]
        val_X = features_list[split:]
        val_y = labels_list[split:]

        if not val_X:
            return

        try:
            if _HAS_XGBOOST:
                dtrain = xgb.DMatrix(train_X, label=train_y)
                dval = xgb.DMatrix(val_X, label=val_y)

                params = {
                    "max_depth": 3,
                    "eta": 0.1,
                    "objective": "binary:logistic",
                    "eval_metric": "error",
                    "nthread": 1,
                    "verbosity": 0,
                }

                model = xgb.train(params, dtrain, num_boost_round=50)

                # Validation
                preds = model.predict(dval)
                pred_labels = [1 if p > 0.5 else 0 for p in preds]
            else:
                # Fallback : majority vote basé sur features moyennes
                model = self._train_simple(train_X, train_y)
                pred_labels = [self._predict_simple_static(model, f) for f in val_X]

            correct = sum(1 for p, a in zip(pred_labels, val_y) if p == a)
            accuracy = correct / len(val_y)
            is_active = accuracy >= self._min_accuracy

            # --- 3. Stockage du modèle sous lock ---
            with self._lock:
                self._model = model
                self._accuracy = accuracy
                self._is_active = is_active
                self._train_count += 1
                self._samples_since_train = 0
                train_count = self._train_count

            status = "ACTIVÉ" if is_active else "INACTIF"
            logger.info(
                "🤖 XGBoost re-entraîné (#%d) — accuracy=%.2f%% → %s",
                train_count, accuracy * 100, status,
            )

            if is_active and not was_active:
                logger.info("🟢 XGBoost AUTO-ACTIVÉ (accuracy=%.2f%%)", accuracy * 100)
            elif not is_active and was_active:
                logger.warning("🔴 XGBoost DÉSACTIVÉ (accuracy=%.2f%% < %.2f%%)",
                              accuracy * 100, self._min_accuracy * 100)

        except Exception:
            logger.exception("Erreur entraînement XGBoost")

    def _train_simple(self, X: List[List[float]], y: List[int]) -> Dict:
        """Fallback : calcule les moyennes de features par classe."""
        class_0 = [f for f, l in zip(X, y) if l == 0]
        class_1 = [f for f, l in zip(X, y) if l == 1]

        n_features = len(X[0]) if X else 0
        mean_0 = [0.0] * n_features
        mean_1 = [0.0] * n_features

        if class_0:
            for i in range(n_features):
                mean_0[i] = sum(f[i] for f in class_0) / len(class_0)
        if class_1:
            for i in range(n_features):
                mean_1[i] = sum(f[i] for f in class_1) / len(class_1)

        return {"mean_0": mean_0, "mean_1": mean_1}

    def _predict_simple(self, features: List[float]) -> int:
        """Fallback : nearest mean classifier (utilise self._model)."""
        if not self._model:
            return 0
        return self._predict_simple_static(self._model, features)

    @staticmethod
    def _predict_simple_static(model: Dict, features: List[float]) -> int:
        """Fallback : nearest mean classifier (modèle passé en paramètre)."""
        if not model:
            return 0
        mean_0 = model["mean_0"]
        mean_1 = model["mean_1"]

        dist_0 = sum((f - m) ** 2 for f, m in zip(features, mean_0))
        dist_1 = sum((f - m) ** 2 for f, m in zip(features, mean_1))

        return 1 if dist_1 < dist_0 else 0

    # ------------------------------------------------------------------
    # Prédiction
    # ------------------------------------------------------------------

    def predict(self, features: List[float]) -> Optional[Dict[str, Any]]:
        """
        Prédit la direction à partir de features.

        Returns:
            Dict avec prediction (0/1), probability, is_active.
            None si modèle non entraîné.
        """
        with self._lock:
            if self._model is None:
                return None

            try:
                if _HAS_XGBOOST and isinstance(self._model, xgb.Booster):
                    # LOG-02: Optimization: use inplace_predict for low-latency single-row inference
                    try:
                        import numpy as np
                        prob = float(self._model.inplace_predict(np.array([features], dtype=np.float32))[0])
                    except (ImportError, AttributeError):
                        # Fallback if numpy is missing or old xgboost version
                        dtest = xgb.DMatrix([features])
                        prob = float(self._model.predict(dtest)[0])
                    pred = 1 if prob > 0.5 else 0
                else:
                    pred = self._predict_simple(features)
                    prob = 0.6 if pred == 1 else 0.4

                self._prediction_count += 1

                return {
                    "prediction": pred,
                    "probability": round(prob, 4),
                    "direction": "UP" if pred == 1 else "DOWN",
                    "is_active": self._is_active,
                    "model_accuracy": round(self._accuracy, 4),
                    "should_trade": self._is_active,
                }

            except Exception:
                logger.exception("Erreur prédiction XGBoost")
                return None

    def get_status(self) -> Dict[str, Any]:
        """Retourne l'état du prédicteur."""
        with self._lock:
            return {
                "has_xgboost": _HAS_XGBOOST,
                "is_active": self._is_active,
                "accuracy": round(self._accuracy, 4),
                "samples": len(self._features),
                "train_count": self._train_count,
                "prediction_count": self._prediction_count,
                "min_accuracy": self._min_accuracy,
                "min_samples": self._min_samples,
            }

    def reset(self) -> None:
        """Réinitialise."""
        with self._lock:
            self._features.clear()
            self._labels.clear()
            self._model = None
            self._is_active = False
            self._accuracy = 0.0
            self._train_count = 0
            self._prediction_count = 0
            self._price_history.clear()
            self._volume_history.clear()
            logger.info("XGBoostPredictor: réinitialisé")


# ======================================================================
# Tests intégrés
# ======================================================================
if __name__ == "__main__":
    import sys
    import random

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

    print("\n🧪 Tests XGBoostPredictor")
    print("=" * 50)

    pred = XGBoostPredictor(min_samples=50, min_accuracy=0.5, retrain_interval=30)

    # Test 1: Init
    assert_test("Init OK", pred._model is None)
    assert_test("Has xgboost flag", isinstance(_HAS_XGBOOST, bool))

    # Test 2: Feature extraction
    for i in range(60):
        feats = pred.extract_features(50000 + random.gauss(0, 100), volume=10)
    assert_test("Features extraites après warmup", feats is not None)
    assert_test("8 features", len(feats) == 8)

    # Test 3: Add samples with pattern
    random.seed(42)
    for i in range(100):
        # Simple pattern: positive ROC → UP
        features = [
            random.gauss(0.01, 0.02),   # roc_5
            random.gauss(0.02, 0.03),   # roc_10
            random.gauss(0.03, 0.04),   # roc_20
            1.01 + random.gauss(0, 0.01),  # ma_ratio
            1.02 + random.gauss(0, 0.01),  # ma_ratio_50
            0.02 + random.gauss(0, 0.01),  # volatility
            0.55 + random.gauss(0, 0.1),   # rsi
            1.0 + random.gauss(0, 0.3),    # vol_ratio
        ]
        label = 1 if features[0] > 0 else 0
        pred.add_sample(features, label)

    assert_test("100 samples ajoutés", len(pred._features) == 100)
    assert_test("Modèle entraîné", pred._model is not None)

    # Test 4: Predict
    test_features = [0.02, 0.03, 0.04, 1.01, 1.02, 0.02, 0.6, 1.0]
    result = pred.predict(test_features)
    assert_test("Prédiction retournée", result is not None)
    if result:
        assert_test("Prediction 0 ou 1", result["prediction"] in (0, 1))
        assert_test("Probability entre 0 et 1", 0 <= result["probability"] <= 1)
        assert_test("Direction UP ou DOWN", result["direction"] in ("UP", "DOWN"))

    # Test 5: Status
    status = pred.get_status()
    assert_test("Status has is_active", "is_active" in status)
    assert_test("Status has accuracy", "accuracy" in status)
    assert_test("Status has samples", status["samples"] == 100)

    # Test 6: Auto-activation check
    assert_test("Train count > 0", pred._train_count > 0)
    assert_test(f"Accuracy calculée ({pred._accuracy:.2f})", pred._accuracy > 0)

    # Test 7: Reset
    pred.reset()
    assert_test("Reset: model None", pred._model is None)
    assert_test("Reset: 0 samples", len(pred._features) == 0)

    # Test 8: Thread safety
    import concurrent.futures
    ts_pred = XGBoostPredictor(min_samples=50, retrain_interval=30)

    def add_samples(n):
        r = random.Random()
        for _ in range(n):
            feats = [r.gauss(0, 1) for _ in range(8)]
            ts_pred.add_sample(feats, r.choice([0, 1]))
        return n

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(add_samples, 50) for _ in range(4)]
        [f.result() for f in futures]
    assert_test("Thread safety: 200 samples", len(ts_pred._features) == 200)

    print(f"\n{'=' * 50}")
    print(f"Résultat: {passed}/{passed + failed} tests passés")
    sys.exit(0 if failed == 0 else 1)