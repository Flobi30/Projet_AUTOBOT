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

# Universe Manager (Lot 1)
ENABLE_UNIVERSE_MANAGER = os.getenv("ENABLE_UNIVERSE_MANAGER", "false").lower() in ("1", "true", "yes", "on")
UNIVERSE_MAX_SUPPORTED = int(os.getenv("UNIVERSE_MAX_SUPPORTED", "50"))
UNIVERSE_MAX_ELIGIBLE = int(os.getenv("UNIVERSE_MAX_ELIGIBLE", "30"))
UNIVERSE_ENABLE_FOREX = os.getenv("UNIVERSE_ENABLE_FOREX", "false").lower() in ("1", "true", "yes", "on")

# Pair Ranking Engine (Lot 2)
ENABLE_PAIR_RANKING_ENGINE = os.getenv("ENABLE_PAIR_RANKING_ENGINE", "false").lower() in ("1", "true", "yes", "on")
RANKING_UPDATE_SECONDS = int(os.getenv("RANKING_UPDATE_SECONDS", "300"))
RANKING_MIN_SCORE_ACTIVATE = float(os.getenv("RANKING_MIN_SCORE_ACTIVATE", "55"))

# Scalability Guard (Lot 3)
ENABLE_SCALABILITY_GUARD = os.getenv("ENABLE_SCALABILITY_GUARD", "false").lower() in ("1", "true", "yes", "on")
SCALING_GUARD_CPU_PCT_MAX = float(os.getenv("SCALING_GUARD_CPU_PCT_MAX", "90"))
SCALING_GUARD_MEMORY_PCT_MAX = float(os.getenv("SCALING_GUARD_MEMORY_PCT_MAX", "90"))
SCALING_GUARD_WS_STALE_SECONDS_MAX = float(os.getenv("SCALING_GUARD_WS_STALE_SECONDS_MAX", "45"))
SCALING_GUARD_WS_LAG_MAX = int(os.getenv("SCALING_GUARD_WS_LAG_MAX", "10000"))
SCALING_GUARD_EXEC_FAILURE_RATE_MAX = float(os.getenv("SCALING_GUARD_EXEC_FAILURE_RATE_MAX", "0.35"))
SCALING_GUARD_RECON_MISMATCH_MAX = float(os.getenv("SCALING_GUARD_RECON_MISMATCH_MAX", "0.05"))
SCALING_GUARD_PF_MIN = float(os.getenv("SCALING_GUARD_PF_MIN", "1.0"))
SCALING_GUARD_VALIDATION_FAIL_MAX = float(os.getenv("SCALING_GUARD_VALIDATION_FAIL_MAX", "0.5"))

# Instance Activation Manager (Lot 4)
ENABLE_INSTANCE_ACTIVATION_MANAGER = os.getenv("ENABLE_INSTANCE_ACTIVATION_MANAGER", "false").lower() in ("1", "true", "yes", "on")
ACTIVATION_DEFAULT_TIER = int(os.getenv("ACTIVATION_DEFAULT_TIER", "1"))
ACTIVATION_PROMOTE_SCORE_MIN = float(os.getenv("ACTIVATION_PROMOTE_SCORE_MIN", "70"))
ACTIVATION_DEMOTE_SCORE_MAX = float(os.getenv("ACTIVATION_DEMOTE_SCORE_MAX", "45"))
ACTIVATION_PROMOTE_HEALTH_MIN = float(os.getenv("ACTIVATION_PROMOTE_HEALTH_MIN", "70"))
ACTIVATION_DEMOTE_HEALTH_MAX = float(os.getenv("ACTIVATION_DEMOTE_HEALTH_MAX", "50"))
ACTIVATION_HYSTERESIS_CYCLES = int(os.getenv("ACTIVATION_HYSTERESIS_CYCLES", "2"))
ACTIVATION_COOLDOWN_SECONDS = int(os.getenv("ACTIVATION_COOLDOWN_SECONDS", "1800"))

# Portfolio Allocator (Lot 5)
ENABLE_PORTFOLIO_ALLOCATOR = os.getenv("ENABLE_PORTFOLIO_ALLOCATOR", "false").lower() in ("1", "true", "yes", "on")
PORTFOLIO_MAX_CAPITAL_PER_INSTANCE_RATIO = float(os.getenv("PORTFOLIO_MAX_CAPITAL_PER_INSTANCE_RATIO", "0.10"))
PORTFOLIO_MAX_CAPITAL_PER_CLUSTER_RATIO = float(os.getenv("PORTFOLIO_MAX_CAPITAL_PER_CLUSTER_RATIO", "0.35"))
PORTFOLIO_RESERVE_CASH_RATIO = float(os.getenv("PORTFOLIO_RESERVE_CASH_RATIO", "0.20"))
PORTFOLIO_MAX_TOTAL_ACTIVE_RISK_RATIO = float(os.getenv("PORTFOLIO_MAX_TOTAL_ACTIVE_RISK_RATIO", "0.50"))
PORTFOLIO_RISK_PER_CAPITAL_RATIO = float(os.getenv("PORTFOLIO_RISK_PER_CAPITAL_RATIO", "0.02"))

# Safety
SAFETY_DSR_TIMEOUT_MS = float(os.getenv("SAFETY_DSR_TIMEOUT_MS", "50"))
SAFETY_DSR_CACHE_S = int(os.getenv("SAFETY_DSR_CACHE_S", "300"))
SAFETY_WF_LEARNING_DAYS = int(os.getenv("SAFETY_WF_LEARNING_DAYS", "7"))
SAFETY_WF_MIN_TRADES_LEARNING = int(os.getenv("SAFETY_WF_MIN_TRADES_LEARNING", "10"))
SAFETY_MAX_BLOCK_RATIO = float(os.getenv("SAFETY_MAX_BLOCK_RATIO", "0.8"))
SAFETY_EMERGENCY_CYCLE_MS = float(os.getenv("SAFETY_EMERGENCY_CYCLE_MS", "100"))
SAFETY_EMERGENCY_CONSECUTIVE = int(os.getenv("SAFETY_EMERGENCY_CONSECUTIVE", "3"))


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

if UNIVERSE_MAX_SUPPORTED < 1:
    raise ValueError("UNIVERSE_MAX_SUPPORTED must be >= 1")

if UNIVERSE_MAX_ELIGIBLE < 1:
    raise ValueError("UNIVERSE_MAX_ELIGIBLE must be >= 1")

if UNIVERSE_MAX_ELIGIBLE > UNIVERSE_MAX_SUPPORTED:
    raise ValueError("UNIVERSE_MAX_ELIGIBLE must be <= UNIVERSE_MAX_SUPPORTED")

if RANKING_UPDATE_SECONDS < 1:
    raise ValueError("RANKING_UPDATE_SECONDS must be >= 1")

if not 0.0 <= RANKING_MIN_SCORE_ACTIVATE <= 100.0:
    raise ValueError("RANKING_MIN_SCORE_ACTIVATE must be in [0, 100]")

if not 0.0 <= SCALING_GUARD_CPU_PCT_MAX <= 100.0:
    raise ValueError("SCALING_GUARD_CPU_PCT_MAX must be in [0, 100]")

if not 0.0 <= SCALING_GUARD_MEMORY_PCT_MAX <= 100.0:
    raise ValueError("SCALING_GUARD_MEMORY_PCT_MAX must be in [0, 100]")

if SCALING_GUARD_WS_STALE_SECONDS_MAX < 1:
    raise ValueError("SCALING_GUARD_WS_STALE_SECONDS_MAX must be >= 1")

if SCALING_GUARD_WS_LAG_MAX < 1:
    raise ValueError("SCALING_GUARD_WS_LAG_MAX must be >= 1")

if not 0.0 <= SCALING_GUARD_EXEC_FAILURE_RATE_MAX <= 1.0:
    raise ValueError("SCALING_GUARD_EXEC_FAILURE_RATE_MAX must be in [0, 1]")

if not 0.0 <= SCALING_GUARD_RECON_MISMATCH_MAX <= 1.0:
    raise ValueError("SCALING_GUARD_RECON_MISMATCH_MAX must be in [0, 1]")

if SCALING_GUARD_PF_MIN <= 0:
    raise ValueError("SCALING_GUARD_PF_MIN must be > 0")

if not 0.0 <= SCALING_GUARD_VALIDATION_FAIL_MAX <= 1.0:
    raise ValueError("SCALING_GUARD_VALIDATION_FAIL_MAX must be in [0, 1]")

if ACTIVATION_DEFAULT_TIER < 1:
    raise ValueError("ACTIVATION_DEFAULT_TIER must be >= 1")

if not 0.0 <= ACTIVATION_PROMOTE_SCORE_MIN <= 100.0:
    raise ValueError("ACTIVATION_PROMOTE_SCORE_MIN must be in [0, 100]")

if not 0.0 <= ACTIVATION_DEMOTE_SCORE_MAX <= 100.0:
    raise ValueError("ACTIVATION_DEMOTE_SCORE_MAX must be in [0, 100]")

if ACTIVATION_DEMOTE_SCORE_MAX > ACTIVATION_PROMOTE_SCORE_MIN:
    raise ValueError("ACTIVATION_DEMOTE_SCORE_MAX must be <= ACTIVATION_PROMOTE_SCORE_MIN")

if not 0.0 <= ACTIVATION_PROMOTE_HEALTH_MIN <= 100.0:
    raise ValueError("ACTIVATION_PROMOTE_HEALTH_MIN must be in [0, 100]")

if not 0.0 <= ACTIVATION_DEMOTE_HEALTH_MAX <= 100.0:
    raise ValueError("ACTIVATION_DEMOTE_HEALTH_MAX must be in [0, 100]")

if ACTIVATION_DEMOTE_HEALTH_MAX > ACTIVATION_PROMOTE_HEALTH_MIN:
    raise ValueError("ACTIVATION_DEMOTE_HEALTH_MAX must be <= ACTIVATION_PROMOTE_HEALTH_MIN")

if ACTIVATION_HYSTERESIS_CYCLES < 1:
    raise ValueError("ACTIVATION_HYSTERESIS_CYCLES must be >= 1")

if ACTIVATION_COOLDOWN_SECONDS < 1:
    raise ValueError("ACTIVATION_COOLDOWN_SECONDS must be >= 1")

if not 0.0 < PORTFOLIO_MAX_CAPITAL_PER_INSTANCE_RATIO <= 1.0:
    raise ValueError("PORTFOLIO_MAX_CAPITAL_PER_INSTANCE_RATIO must be in (0, 1]")

if not 0.0 < PORTFOLIO_MAX_CAPITAL_PER_CLUSTER_RATIO <= 1.0:
    raise ValueError("PORTFOLIO_MAX_CAPITAL_PER_CLUSTER_RATIO must be in (0, 1]")

if not 0.0 <= PORTFOLIO_RESERVE_CASH_RATIO < 1.0:
    raise ValueError("PORTFOLIO_RESERVE_CASH_RATIO must be in [0, 1)")

if not 0.0 < PORTFOLIO_MAX_TOTAL_ACTIVE_RISK_RATIO <= 1.0:
    raise ValueError("PORTFOLIO_MAX_TOTAL_ACTIVE_RISK_RATIO must be in (0, 1]")

if not 0.0 < PORTFOLIO_RISK_PER_CAPITAL_RATIO <= 1.0:
    raise ValueError("PORTFOLIO_RISK_PER_CAPITAL_RATIO must be in (0, 1]")

if PORTFOLIO_MAX_CAPITAL_PER_INSTANCE_RATIO > PORTFOLIO_MAX_CAPITAL_PER_CLUSTER_RATIO:
    raise ValueError("PORTFOLIO_MAX_CAPITAL_PER_INSTANCE_RATIO must be <= PORTFOLIO_MAX_CAPITAL_PER_CLUSTER_RATIO")

if SAFETY_DSR_TIMEOUT_MS <= 0:
    raise ValueError("SAFETY_DSR_TIMEOUT_MS must be > 0")

if SAFETY_DSR_CACHE_S < 1:
    raise ValueError("SAFETY_DSR_CACHE_S must be >= 1")

if SAFETY_WF_LEARNING_DAYS < 0:
    raise ValueError("SAFETY_WF_LEARNING_DAYS must be >= 0")

if SAFETY_WF_MIN_TRADES_LEARNING < 1:
    raise ValueError("SAFETY_WF_MIN_TRADES_LEARNING must be >= 1")

if not 0.0 <= SAFETY_MAX_BLOCK_RATIO <= 1.0:
    raise ValueError("SAFETY_MAX_BLOCK_RATIO must be in [0, 1]")

if SAFETY_EMERGENCY_CYCLE_MS <= 0:
    raise ValueError("SAFETY_EMERGENCY_CYCLE_MS must be > 0")

if SAFETY_EMERGENCY_CONSECUTIVE < 1:
    raise ValueError("SAFETY_EMERGENCY_CONSECUTIVE must be >= 1")
