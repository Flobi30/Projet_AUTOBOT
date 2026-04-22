"""Configuration runtime centralisée pour AUTOBOT v2.

Ce module externalise les paramètres sensibles qui étaient hardcodés.
Chaque variable lit d'abord l'environnement, puis applique une valeur par défaut
alignée avec le comportement historique.
"""

from __future__ import annotations

import os
import warnings
from typing import Callable, TypeVar

T = TypeVar("T")

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


def _parse_bool(raw_value: str) -> bool:
    normalized = raw_value.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise ValueError(f"invalid boolean value: {raw_value!r}")


def _warn_or_raise(message: str) -> None:
    if STRICT_CONFIG:
        raise ValueError(message)
    warnings.warn(message, RuntimeWarning, stacklevel=2)


def _get_env(name: str, default: T, parser: Callable[[str], T]) -> T:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return parser(raw_value)
    except (TypeError, ValueError) as exc:
        _warn_or_raise(
            f"[{name}] invalid value {raw_value!r} ({exc}); fallback to default {default!r}"
        )
        return default


def _validate(name: str, value: T, default: T, predicate: Callable[[T], bool], rule: str) -> T:
    if predicate(value):
        return value
    _warn_or_raise(
        f"[{name}] value {value!r} violates '{rule}'; fallback to default {default!r}"
    )
    return default


def _validate_pair(
    left_name: str,
    left_value: T,
    right_name: str,
    right_value: T,
    predicate: Callable[[T, T], bool],
    fallback: Callable[[T, T], tuple[T, T]],
    rule: str,
) -> tuple[T, T]:
    if predicate(left_value, right_value):
        return left_value, right_value
    new_left, new_right = fallback(left_value, right_value)
    _warn_or_raise(
        f"[{left_name}/{right_name}] values ({left_value!r}, {right_value!r}) violate '{rule}'; "
        f"fallback to ({new_left!r}, {new_right!r})"
    )
    return new_left, new_right


# STRICT_CONFIG=true/1/yes/on => comportement fail-fast historique.
STRICT_CONFIG = _get_env("STRICT_CONFIG", False, _parse_bool)

# Score de santé minimum [0..100] avant alerte LOW_HEALTH_SCORE.
HEALTH_SCORE_THRESHOLD = _get_env("HEALTH_SCORE_THRESHOLD", 60, int)

# Intervalle minimum (secondes) entre deux actions de trading automatiques.
TRADE_ACTION_MIN_INTERVAL_S = _get_env("TRADE_ACTION_MIN_INTERVAL_S", 1.5, float)

# Nombre maximum d'actions auto répétées autorisées avant blocage.
MAX_REPEATED_AUTO_ACTIONS = _get_env("MAX_REPEATED_AUTO_ACTIONS", 3, int)

# Plafond du backoff exponentiel des modules instables (secondes).
MAX_BACKOFF_SECONDS = _get_env("MAX_BACKOFF_SECONDS", 300, int)

# Nombre max d'instances traitées par cycle d'orchestration.
MAX_INSTANCES_PER_CYCLE = _get_env("MAX_INSTANCES_PER_CYCLE", 45, int)

# Capital minimum global (EUR) pour autoriser un spin-off.
SPIN_OFF_THRESHOLD = _get_env("SPIN_OFF_THRESHOLD", 1800, int)

# Profit Factor minimum sur 30 jours pour autoriser un spin-off.
MIN_PF_FOR_SPINOFF = _get_env("MIN_PF_FOR_SPINOFF", 1.2, float)

# Volatilité cible utilisée pour adapter la taille de position.
TARGET_VOLATILITY = _get_env("TARGET_VOLATILITY", 0.02, float)

# Nombre de flux websocket désirés (contrainte runtime).
WEBSOCKET_STREAMS = _get_env("WEBSOCKET_STREAMS", 1, int)

# Universe Manager (Lot 1)
ENABLE_UNIVERSE_MANAGER = _get_env("ENABLE_UNIVERSE_MANAGER", False, _parse_bool)
UNIVERSE_MAX_SUPPORTED = _get_env("UNIVERSE_MAX_SUPPORTED", 50, int)
UNIVERSE_MAX_ELIGIBLE = _get_env("UNIVERSE_MAX_ELIGIBLE", 30, int)
UNIVERSE_ENABLE_FOREX = _get_env("UNIVERSE_ENABLE_FOREX", False, _parse_bool)

# Pair Ranking Engine (Lot 2)
ENABLE_PAIR_RANKING_ENGINE = _get_env("ENABLE_PAIR_RANKING_ENGINE", False, _parse_bool)
RANKING_UPDATE_SECONDS = _get_env("RANKING_UPDATE_SECONDS", 300, int)
RANKING_MIN_SCORE_ACTIVATE = _get_env("RANKING_MIN_SCORE_ACTIVATE", 55.0, float)

# Scalability Guard (Lot 3)
ENABLE_SCALABILITY_GUARD = _get_env("ENABLE_SCALABILITY_GUARD", False, _parse_bool)
SCALING_GUARD_CPU_PCT_MAX = _get_env("SCALING_GUARD_CPU_PCT_MAX", 90.0, float)
SCALING_GUARD_MEMORY_PCT_MAX = _get_env("SCALING_GUARD_MEMORY_PCT_MAX", 90.0, float)
SCALING_GUARD_WS_STALE_SECONDS_MAX = _get_env("SCALING_GUARD_WS_STALE_SECONDS_MAX", 45.0, float)
SCALING_GUARD_WS_LAG_MAX = _get_env("SCALING_GUARD_WS_LAG_MAX", 10000, int)
SCALING_GUARD_EXEC_FAILURE_RATE_MAX = _get_env("SCALING_GUARD_EXEC_FAILURE_RATE_MAX", 0.35, float)
SCALING_GUARD_RECON_MISMATCH_MAX = _get_env("SCALING_GUARD_RECON_MISMATCH_MAX", 0.05, float)
SCALING_GUARD_PF_MIN = _get_env("SCALING_GUARD_PF_MIN", 1.0, float)
SCALING_GUARD_VALIDATION_FAIL_MAX = _get_env("SCALING_GUARD_VALIDATION_FAIL_MAX", 0.5, float)

# Instance Activation Manager (Lot 4)
ENABLE_INSTANCE_ACTIVATION_MANAGER = _get_env("ENABLE_INSTANCE_ACTIVATION_MANAGER", False, _parse_bool)
ACTIVATION_DEFAULT_TIER = _get_env("ACTIVATION_DEFAULT_TIER", 1, int)
ACTIVATION_PROMOTE_SCORE_MIN = _get_env("ACTIVATION_PROMOTE_SCORE_MIN", 70.0, float)
ACTIVATION_DEMOTE_SCORE_MAX = _get_env("ACTIVATION_DEMOTE_SCORE_MAX", 45.0, float)
ACTIVATION_PROMOTE_HEALTH_MIN = _get_env("ACTIVATION_PROMOTE_HEALTH_MIN", 70.0, float)
ACTIVATION_DEMOTE_HEALTH_MAX = _get_env("ACTIVATION_DEMOTE_HEALTH_MAX", 50.0, float)
ACTIVATION_HYSTERESIS_CYCLES = _get_env("ACTIVATION_HYSTERESIS_CYCLES", 2, int)
ACTIVATION_COOLDOWN_SECONDS = _get_env("ACTIVATION_COOLDOWN_SECONDS", 1800, int)

# Portfolio Allocator (Lot 5)
ENABLE_PORTFOLIO_ALLOCATOR = _get_env("ENABLE_PORTFOLIO_ALLOCATOR", False, _parse_bool)
PORTFOLIO_MAX_CAPITAL_PER_INSTANCE_RATIO = _get_env("PORTFOLIO_MAX_CAPITAL_PER_INSTANCE_RATIO", 0.10, float)
PORTFOLIO_MAX_CAPITAL_PER_CLUSTER_RATIO = _get_env("PORTFOLIO_MAX_CAPITAL_PER_CLUSTER_RATIO", 0.35, float)
PORTFOLIO_RESERVE_CASH_RATIO = _get_env("PORTFOLIO_RESERVE_CASH_RATIO", 0.20, float)
PORTFOLIO_MAX_TOTAL_ACTIVE_RISK_RATIO = _get_env("PORTFOLIO_MAX_TOTAL_ACTIVE_RISK_RATIO", 0.50, float)
PORTFOLIO_RISK_PER_CAPITAL_RATIO = _get_env("PORTFOLIO_RISK_PER_CAPITAL_RATIO", 0.02, float)

# Safety
SAFETY_DSR_TIMEOUT_MS = _get_env("SAFETY_DSR_TIMEOUT_MS", 50.0, float)
SAFETY_DSR_CACHE_S = _get_env("SAFETY_DSR_CACHE_S", 300, int)
SAFETY_WF_LEARNING_DAYS = _get_env("SAFETY_WF_LEARNING_DAYS", 7, int)
SAFETY_WF_MIN_TRADES_LEARNING = _get_env("SAFETY_WF_MIN_TRADES_LEARNING", 10, int)
SAFETY_MAX_BLOCK_RATIO = _get_env("SAFETY_MAX_BLOCK_RATIO", 0.8, float)
SAFETY_EMERGENCY_CYCLE_MS = _get_env("SAFETY_EMERGENCY_CYCLE_MS", 100.0, float)
SAFETY_EMERGENCY_CONSECUTIVE = _get_env("SAFETY_EMERGENCY_CONSECUTIVE", 3, int)


# Decision Journal (Lot 1 - analytics/observability)
ENABLE_DECISION_JOURNAL = _get_env("ENABLE_DECISION_JOURNAL", False, _parse_bool)
DECISION_JOURNAL_PATH = _get_env("DECISION_JOURNAL_PATH", "data/decision_journal.jsonl", str)
DECISION_JOURNAL_FLUSH_EVERY = _get_env("DECISION_JOURNAL_FLUSH_EVERY", 1, int)
DECISION_JOURNAL_MAX_SYMBOLS = _get_env("DECISION_JOURNAL_MAX_SYMBOLS", 10, int)


HEALTH_SCORE_THRESHOLD = _validate("HEALTH_SCORE_THRESHOLD", HEALTH_SCORE_THRESHOLD, 60, lambda v: 0 <= v <= 100, "must be in [0, 100]")
TRADE_ACTION_MIN_INTERVAL_S = _validate("TRADE_ACTION_MIN_INTERVAL_S", TRADE_ACTION_MIN_INTERVAL_S, 1.5, lambda v: v > 0, "must be > 0")
MAX_REPEATED_AUTO_ACTIONS = _validate("MAX_REPEATED_AUTO_ACTIONS", MAX_REPEATED_AUTO_ACTIONS, 3, lambda v: v >= 1, "must be >= 1")
MAX_BACKOFF_SECONDS = _validate("MAX_BACKOFF_SECONDS", MAX_BACKOFF_SECONDS, 300, lambda v: v >= 1, "must be >= 1")
MAX_INSTANCES_PER_CYCLE = _validate("MAX_INSTANCES_PER_CYCLE", MAX_INSTANCES_PER_CYCLE, 45, lambda v: v >= 1, "must be >= 1")
SPIN_OFF_THRESHOLD = _validate("SPIN_OFF_THRESHOLD", SPIN_OFF_THRESHOLD, 1800, lambda v: v >= 0, "must be >= 0")
MIN_PF_FOR_SPINOFF = _validate("MIN_PF_FOR_SPINOFF", MIN_PF_FOR_SPINOFF, 1.2, lambda v: v > 0, "must be > 0")
TARGET_VOLATILITY = _validate("TARGET_VOLATILITY", TARGET_VOLATILITY, 0.02, lambda v: v > 0, "must be > 0")
WEBSOCKET_STREAMS = _validate("WEBSOCKET_STREAMS", WEBSOCKET_STREAMS, 1, lambda v: v >= 1, "must be >= 1")

UNIVERSE_MAX_SUPPORTED = _validate("UNIVERSE_MAX_SUPPORTED", UNIVERSE_MAX_SUPPORTED, 50, lambda v: v >= 1, "must be >= 1")
UNIVERSE_MAX_ELIGIBLE = _validate("UNIVERSE_MAX_ELIGIBLE", UNIVERSE_MAX_ELIGIBLE, 30, lambda v: v >= 1, "must be >= 1")
UNIVERSE_MAX_ELIGIBLE, UNIVERSE_MAX_SUPPORTED = _validate_pair(
    "UNIVERSE_MAX_ELIGIBLE",
    UNIVERSE_MAX_ELIGIBLE,
    "UNIVERSE_MAX_SUPPORTED",
    UNIVERSE_MAX_SUPPORTED,
    lambda eligible, supported: eligible <= supported,
    lambda eligible, supported: (min(eligible, supported), supported),
    "UNIVERSE_MAX_ELIGIBLE must be <= UNIVERSE_MAX_SUPPORTED",
)

RANKING_UPDATE_SECONDS = _validate("RANKING_UPDATE_SECONDS", RANKING_UPDATE_SECONDS, 300, lambda v: v >= 1, "must be >= 1")
RANKING_MIN_SCORE_ACTIVATE = _validate(
    "RANKING_MIN_SCORE_ACTIVATE", RANKING_MIN_SCORE_ACTIVATE, 55.0, lambda v: 0.0 <= v <= 100.0, "must be in [0, 100]"
)

SCALING_GUARD_CPU_PCT_MAX = _validate("SCALING_GUARD_CPU_PCT_MAX", SCALING_GUARD_CPU_PCT_MAX, 90.0, lambda v: 0.0 <= v <= 100.0, "must be in [0, 100]")
SCALING_GUARD_MEMORY_PCT_MAX = _validate(
    "SCALING_GUARD_MEMORY_PCT_MAX", SCALING_GUARD_MEMORY_PCT_MAX, 90.0, lambda v: 0.0 <= v <= 100.0, "must be in [0, 100]"
)
SCALING_GUARD_WS_STALE_SECONDS_MAX = _validate(
    "SCALING_GUARD_WS_STALE_SECONDS_MAX", SCALING_GUARD_WS_STALE_SECONDS_MAX, 45.0, lambda v: v >= 1, "must be >= 1"
)
SCALING_GUARD_WS_LAG_MAX = _validate("SCALING_GUARD_WS_LAG_MAX", SCALING_GUARD_WS_LAG_MAX, 10000, lambda v: v >= 1, "must be >= 1")
SCALING_GUARD_EXEC_FAILURE_RATE_MAX = _validate(
    "SCALING_GUARD_EXEC_FAILURE_RATE_MAX",
    SCALING_GUARD_EXEC_FAILURE_RATE_MAX,
    0.35,
    lambda v: 0.0 <= v <= 1.0,
    "must be in [0, 1]",
)
SCALING_GUARD_RECON_MISMATCH_MAX = _validate(
    "SCALING_GUARD_RECON_MISMATCH_MAX",
    SCALING_GUARD_RECON_MISMATCH_MAX,
    0.05,
    lambda v: 0.0 <= v <= 1.0,
    "must be in [0, 1]",
)
SCALING_GUARD_PF_MIN = _validate("SCALING_GUARD_PF_MIN", SCALING_GUARD_PF_MIN, 1.0, lambda v: v > 0, "must be > 0")
SCALING_GUARD_VALIDATION_FAIL_MAX = _validate(
    "SCALING_GUARD_VALIDATION_FAIL_MAX",
    SCALING_GUARD_VALIDATION_FAIL_MAX,
    0.5,
    lambda v: 0.0 <= v <= 1.0,
    "must be in [0, 1]",
)

ACTIVATION_DEFAULT_TIER = _validate("ACTIVATION_DEFAULT_TIER", ACTIVATION_DEFAULT_TIER, 1, lambda v: v >= 1, "must be >= 1")
ACTIVATION_PROMOTE_SCORE_MIN = _validate(
    "ACTIVATION_PROMOTE_SCORE_MIN", ACTIVATION_PROMOTE_SCORE_MIN, 70.0, lambda v: 0.0 <= v <= 100.0, "must be in [0, 100]"
)
ACTIVATION_DEMOTE_SCORE_MAX = _validate(
    "ACTIVATION_DEMOTE_SCORE_MAX", ACTIVATION_DEMOTE_SCORE_MAX, 45.0, lambda v: 0.0 <= v <= 100.0, "must be in [0, 100]"
)
ACTIVATION_DEMOTE_SCORE_MAX, ACTIVATION_PROMOTE_SCORE_MIN = _validate_pair(
    "ACTIVATION_DEMOTE_SCORE_MAX",
    ACTIVATION_DEMOTE_SCORE_MAX,
    "ACTIVATION_PROMOTE_SCORE_MIN",
    ACTIVATION_PROMOTE_SCORE_MIN,
    lambda demote, promote: demote <= promote,
    lambda demote, promote: (min(demote, promote), promote),
    "ACTIVATION_DEMOTE_SCORE_MAX must be <= ACTIVATION_PROMOTE_SCORE_MIN",
)
ACTIVATION_PROMOTE_HEALTH_MIN = _validate(
    "ACTIVATION_PROMOTE_HEALTH_MIN", ACTIVATION_PROMOTE_HEALTH_MIN, 70.0, lambda v: 0.0 <= v <= 100.0, "must be in [0, 100]"
)
ACTIVATION_DEMOTE_HEALTH_MAX = _validate(
    "ACTIVATION_DEMOTE_HEALTH_MAX", ACTIVATION_DEMOTE_HEALTH_MAX, 50.0, lambda v: 0.0 <= v <= 100.0, "must be in [0, 100]"
)
ACTIVATION_DEMOTE_HEALTH_MAX, ACTIVATION_PROMOTE_HEALTH_MIN = _validate_pair(
    "ACTIVATION_DEMOTE_HEALTH_MAX",
    ACTIVATION_DEMOTE_HEALTH_MAX,
    "ACTIVATION_PROMOTE_HEALTH_MIN",
    ACTIVATION_PROMOTE_HEALTH_MIN,
    lambda demote, promote: demote <= promote,
    lambda demote, promote: (min(demote, promote), promote),
    "ACTIVATION_DEMOTE_HEALTH_MAX must be <= ACTIVATION_PROMOTE_HEALTH_MIN",
)
ACTIVATION_HYSTERESIS_CYCLES = _validate("ACTIVATION_HYSTERESIS_CYCLES", ACTIVATION_HYSTERESIS_CYCLES, 2, lambda v: v >= 1, "must be >= 1")
ACTIVATION_COOLDOWN_SECONDS = _validate("ACTIVATION_COOLDOWN_SECONDS", ACTIVATION_COOLDOWN_SECONDS, 1800, lambda v: v >= 1, "must be >= 1")

PORTFOLIO_MAX_CAPITAL_PER_INSTANCE_RATIO = _validate(
    "PORTFOLIO_MAX_CAPITAL_PER_INSTANCE_RATIO",
    PORTFOLIO_MAX_CAPITAL_PER_INSTANCE_RATIO,
    0.10,
    lambda v: 0.0 < v <= 1.0,
    "must be in (0, 1]",
)
PORTFOLIO_MAX_CAPITAL_PER_CLUSTER_RATIO = _validate(
    "PORTFOLIO_MAX_CAPITAL_PER_CLUSTER_RATIO",
    PORTFOLIO_MAX_CAPITAL_PER_CLUSTER_RATIO,
    0.35,
    lambda v: 0.0 < v <= 1.0,
    "must be in (0, 1]",
)
PORTFOLIO_RESERVE_CASH_RATIO = _validate(
    "PORTFOLIO_RESERVE_CASH_RATIO",
    PORTFOLIO_RESERVE_CASH_RATIO,
    0.20,
    lambda v: 0.0 <= v < 1.0,
    "must be in [0, 1)",
)
PORTFOLIO_MAX_TOTAL_ACTIVE_RISK_RATIO = _validate(
    "PORTFOLIO_MAX_TOTAL_ACTIVE_RISK_RATIO",
    PORTFOLIO_MAX_TOTAL_ACTIVE_RISK_RATIO,
    0.50,
    lambda v: 0.0 < v <= 1.0,
    "must be in (0, 1]",
)
PORTFOLIO_RISK_PER_CAPITAL_RATIO = _validate(
    "PORTFOLIO_RISK_PER_CAPITAL_RATIO",
    PORTFOLIO_RISK_PER_CAPITAL_RATIO,
    0.02,
    lambda v: 0.0 < v <= 1.0,
    "must be in (0, 1]",
)
PORTFOLIO_MAX_CAPITAL_PER_INSTANCE_RATIO, PORTFOLIO_MAX_CAPITAL_PER_CLUSTER_RATIO = _validate_pair(
    "PORTFOLIO_MAX_CAPITAL_PER_INSTANCE_RATIO",
    PORTFOLIO_MAX_CAPITAL_PER_INSTANCE_RATIO,
    "PORTFOLIO_MAX_CAPITAL_PER_CLUSTER_RATIO",
    PORTFOLIO_MAX_CAPITAL_PER_CLUSTER_RATIO,
    lambda instance_ratio, cluster_ratio: instance_ratio <= cluster_ratio,
    lambda instance_ratio, cluster_ratio: (min(instance_ratio, cluster_ratio), cluster_ratio),
    "PORTFOLIO_MAX_CAPITAL_PER_INSTANCE_RATIO must be <= PORTFOLIO_MAX_CAPITAL_PER_CLUSTER_RATIO",
)

DECISION_JOURNAL_PATH = _validate(
    "DECISION_JOURNAL_PATH", DECISION_JOURNAL_PATH, "data/decision_journal.jsonl", lambda v: bool(v.strip()), "must not be empty"
)
DECISION_JOURNAL_FLUSH_EVERY = _validate("DECISION_JOURNAL_FLUSH_EVERY", DECISION_JOURNAL_FLUSH_EVERY, 1, lambda v: v >= 1, "must be >= 1")
DECISION_JOURNAL_MAX_SYMBOLS = _validate("DECISION_JOURNAL_MAX_SYMBOLS", DECISION_JOURNAL_MAX_SYMBOLS, 10, lambda v: v >= 1, "must be >= 1")

SAFETY_DSR_TIMEOUT_MS = _validate("SAFETY_DSR_TIMEOUT_MS", SAFETY_DSR_TIMEOUT_MS, 50.0, lambda v: v > 0, "must be > 0")
SAFETY_DSR_CACHE_S = _validate("SAFETY_DSR_CACHE_S", SAFETY_DSR_CACHE_S, 300, lambda v: v >= 1, "must be >= 1")
SAFETY_WF_LEARNING_DAYS = _validate("SAFETY_WF_LEARNING_DAYS", SAFETY_WF_LEARNING_DAYS, 7, lambda v: v >= 0, "must be >= 0")
SAFETY_WF_MIN_TRADES_LEARNING = _validate(
    "SAFETY_WF_MIN_TRADES_LEARNING", SAFETY_WF_MIN_TRADES_LEARNING, 10, lambda v: v >= 1, "must be >= 1"
)
SAFETY_MAX_BLOCK_RATIO = _validate("SAFETY_MAX_BLOCK_RATIO", SAFETY_MAX_BLOCK_RATIO, 0.8, lambda v: 0.0 <= v <= 1.0, "must be in [0, 1]")
SAFETY_EMERGENCY_CYCLE_MS = _validate("SAFETY_EMERGENCY_CYCLE_MS", SAFETY_EMERGENCY_CYCLE_MS, 100.0, lambda v: v > 0, "must be > 0")
SAFETY_EMERGENCY_CONSECUTIVE = _validate(
    "SAFETY_EMERGENCY_CONSECUTIVE", SAFETY_EMERGENCY_CONSECUTIVE, 3, lambda v: v >= 1, "must be >= 1"
)
