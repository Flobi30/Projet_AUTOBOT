"""Configuration runtime centralisée pour AUTOBOT v2.

Ce module externalise les paramètres sensibles qui étaient hardcodés.
Chaque variable lit d'abord l'environnement, puis applique une valeur par défaut
alignée avec le comportement historique.
"""

from __future__ import annotations

import os


# Score de santé minimum [0..100] avant alerte LOW_HEALTH_SCORE.
HEALTH_SCORE_THRESHOLD = int(os.getenv("HEALTH_SCORE_THRESHOLD", "60"))

# Intervalle minimum (secondes) entre deux actions de trading automatiques.
TRADE_ACTION_MIN_INTERVAL_S = float(os.getenv("TRADE_ACTION_MIN_INTERVAL_S", "1.5"))

# Nombre maximum d'actions auto répétées autorisées avant blocage.
MAX_REPEATED_AUTO_ACTIONS = int(os.getenv("MAX_REPEATED_AUTO_ACTIONS", "3"))

# Plafond du backoff exponentiel des modules instables (secondes).
MAX_BACKOFF_SECONDS = int(os.getenv("MAX_BACKOFF_SECONDS", "300"))

# Nombre max d'instances traitées par cycle d'orchestration.
MAX_INSTANCES_PER_CYCLE = int(os.getenv("MAX_INSTANCES_PER_CYCLE", "45"))

# Capital minimum global (EUR) pour autoriser un spin-off.
SPIN_OFF_THRESHOLD = int(os.getenv("SPIN_OFF_THRESHOLD", "1800"))

# Profit Factor minimum sur 30 jours pour autoriser un spin-off.
MIN_PF_FOR_SPINOFF = float(os.getenv("MIN_PF_FOR_SPINOFF", "1.2"))

# Volatilité cible utilisée pour adapter la taille de position.
TARGET_VOLATILITY = float(os.getenv("TARGET_VOLATILITY", "0.02"))

# Nombre de flux websocket désirés (contrainte runtime).
WEBSOCKET_STREAMS = int(os.getenv("WEBSOCKET_STREAMS", "1"))


if not 0 <= HEALTH_SCORE_THRESHOLD <= 100:
    raise ValueError("HEALTH_SCORE_THRESHOLD must be in [0, 100]")

if TRADE_ACTION_MIN_INTERVAL_S <= 0:
    raise ValueError("TRADE_ACTION_MIN_INTERVAL_S must be > 0")

if MAX_REPEATED_AUTO_ACTIONS < 1:
    raise ValueError("MAX_REPEATED_AUTO_ACTIONS must be >= 1")

if MAX_BACKOFF_SECONDS < 1:
    raise ValueError("MAX_BACKOFF_SECONDS must be >= 1")

if MAX_INSTANCES_PER_CYCLE < 1:
    raise ValueError("MAX_INSTANCES_PER_CYCLE must be >= 1")

if SPIN_OFF_THRESHOLD < 0:
    raise ValueError("SPIN_OFF_THRESHOLD must be >= 0")

if MIN_PF_FOR_SPINOFF <= 0:
    raise ValueError("MIN_PF_FOR_SPINOFF must be > 0")

if TARGET_VOLATILITY <= 0:
    raise ValueError("TARGET_VOLATILITY must be > 0")

if WEBSOCKET_STREAMS < 1:
    raise ValueError("WEBSOCKET_STREAMS must be >= 1")
