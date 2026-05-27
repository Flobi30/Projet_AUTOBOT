"""Post-decision outcome labelling for AUTOBOT.

This module does not create trades and does not change risk thresholds.  It
turns accepted/rejected BUY decisions into labelled observations so AUTOBOT can
later measure whether a guard protected capital or blocked useful edge.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Optional


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float, minimum: float, maximum: float) -> float:
    raw = os.getenv(name)
    try:
        value = float(raw) if raw not in (None, "") else default
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    try:
        value = int(raw) if raw not in (None, "") else default
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _env_horizons(name: str, default: tuple[int, ...]) -> tuple[int, ...]:
    raw = os.getenv(name)
    if not raw:
        return default
    values: list[int] = []
    for part in raw.split(","):
        try:
            value = int(part.strip())
        except (TypeError, ValueError):
            continue
        if value > 0:
            values.append(value)
    return tuple(sorted(set(values))) or default


@dataclass(frozen=True)
class DecisionLearningConfig:
    enabled: bool = True
    horizons_minutes: tuple[int, ...] = (15, 60, 240)
    max_candidates_per_horizon: int = 300
    recent_limit: int = 50
    take_profit_bps: float = 35.0
    stop_loss_bps: float = 35.0
    price_sample_interval_seconds: int = 60
    price_retention_hours: int = 168
    min_path_samples: int = 2
    allow_proxy_fallback: bool = False

    @classmethod
    def from_env(cls) -> "DecisionLearningConfig":
        return cls(
            enabled=_env_bool("DECISION_LEARNING_ENABLED", True),
            horizons_minutes=_env_horizons("DECISION_LEARNING_HORIZONS_MIN", (15, 60, 240)),
            max_candidates_per_horizon=_env_int("DECISION_LEARNING_MAX_CANDIDATES", 300, 1, 10_000),
            recent_limit=_env_int("DECISION_LEARNING_RECENT_LIMIT", 50, 1, 500),
            take_profit_bps=_env_float("DECISION_LEARNING_TP_BPS", 35.0, 1.0, 1000.0),
            stop_loss_bps=_env_float("DECISION_LEARNING_SL_BPS", 35.0, 1.0, 1000.0),
            price_sample_interval_seconds=_env_int("DECISION_LEARNING_PRICE_SAMPLE_SECONDS", 60, 10, 3600),
            price_retention_hours=_env_int("DECISION_LEARNING_PRICE_RETENTION_HOURS", 168, 2, 24 * 60),
            min_path_samples=_env_int("DECISION_LEARNING_MIN_PATH_SAMPLES", 2, 1, 100),
            allow_proxy_fallback=_env_bool("DECISION_LEARNING_ALLOW_PROXY_FALLBACK", False),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "horizons_minutes": list(self.horizons_minutes),
            "max_candidates_per_horizon": self.max_candidates_per_horizon,
            "recent_limit": self.recent_limit,
            "take_profit_bps": self.take_profit_bps,
            "stop_loss_bps": self.stop_loss_bps,
            "price_sample_interval_seconds": self.price_sample_interval_seconds,
            "price_retention_hours": self.price_retention_hours,
            "min_path_samples": self.min_path_samples,
            "allow_proxy_fallback": self.allow_proxy_fallback,
        }


def _safe_float(value: Any) -> Optional[float]:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if result <= 0.0:
        return None
    return result


def _parse_dt(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _bucket_start(value: datetime, interval_seconds: int) -> datetime:
    interval = max(1, int(interval_seconds))
    epoch = int(value.timestamp())
    return datetime.fromtimestamp(epoch - (epoch % interval), tz=timezone.utc)


def _normalize_symbol(symbol: Any) -> str:
    text = str(symbol or "").upper().replace("/", "").replace("-", "").strip()
    return text


def _symbol_aliases(symbol: Any) -> set[str]:
    norm = _normalize_symbol(symbol)
    aliases = {norm}
    if norm.startswith("XXBT"):
        aliases.add("BTC" + norm[4:])
    if norm.startswith("BTC"):
        aliases.add("XXBT" + norm[3:])
    if norm.startswith("XETH"):
        aliases.add("ETH" + norm[4:])
    if norm.startswith("ETH"):
        aliases.add("XETH" + norm[3:])
    if norm.startswith("X") and len(norm) > 4:
        aliases.add(norm[1:])
    return {item for item in aliases if item}


def extract_market_price_samples(
    instances: Iterable[Mapping[str, Any]],
    *,
    interval_seconds: int,
) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)
    seen: set[tuple[str, str]] = set()

    def append_sample(symbol: Any, price: Any, observed_at: Any, source: str) -> None:
        price_value = _safe_float(price)
        if price_value is None:
            return
        ts = _parse_dt(observed_at) or now
        bucket = _bucket_start(ts, interval_seconds)
        for alias in _symbol_aliases(symbol):
            key = (alias, bucket.isoformat())
            if key in seen:
                continue
            seen.add(key)
            samples.append({
                "sample_id": f"px_{alias}_{bucket.isoformat()}",
                "symbol": alias,
                "price": float(price_value),
                "observed_at": ts.isoformat(),
                "bucket_start": bucket.isoformat(),
                "source": source,
            })

    for inst in instances or []:
        symbol = inst.get("symbol") or inst.get("pair") or inst.get("kraken_pair")
        tick = inst.get("last_market_tick")
        if isinstance(tick, Mapping):
            append_sample(symbol, tick.get("price"), tick.get("timestamp"), "runtime_last_market_tick")
        else:
            append_sample(symbol, inst.get("last_price") or inst.get("price"), None, "runtime_last_price")

        tail = inst.get("price_history_tail")
        if isinstance(tail, list):
            for item in tail:
                if isinstance(item, Mapping):
                    append_sample(symbol, item.get("price"), item.get("timestamp"), "runtime_price_history_tail")
                elif isinstance(item, (list, tuple)) and len(item) >= 2:
                    append_sample(symbol, item[-1], item[0], "runtime_price_history_tail")

    return samples


def build_price_map(instances: Iterable[Mapping[str, Any]]) -> dict[str, float]:
    prices: dict[str, float] = {}
    for inst in instances or []:
        symbol = inst.get("symbol") or inst.get("pair") or inst.get("kraken_pair")
        price = _safe_float(inst.get("last_price") or inst.get("price"))
        if price is None:
            tail = inst.get("price_history_tail")
            if isinstance(tail, list) and tail:
                last = tail[-1]
                if isinstance(last, Mapping):
                    price = _safe_float(last.get("price"))
                elif isinstance(last, (list, tuple)) and len(last) >= 2:
                    price = _safe_float(last[1])
        if price is None:
            continue
        for alias in _symbol_aliases(symbol):
            prices[alias] = float(price)
    return prices


def _payload(row: Mapping[str, Any]) -> Mapping[str, Any]:
    payload = row.get("payload")
    return payload if isinstance(payload, Mapping) else {}


def _decision_feature_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Keep non-secret decision context needed for later pattern learning."""
    scalar_keys = (
        "reason",
        "blocking_condition",
        "net_edge_bps",
        "gross_edge_bps",
        "cost_bps",
        "min_edge_bps",
        "spread_bps",
        "atr_pct",
        "signal_reason",
        "available_capital",
        "order_value",
        "volume",
    )
    nested_keys = ("edge_context", "opportunity", "opportunity_gate", "risk_params")
    result: dict[str, Any] = {key: payload.get(key) for key in scalar_keys if key in payload}
    for key in nested_keys:
        value = payload.get(key)
        if isinstance(value, Mapping):
            result[key] = dict(value)
    return result


def _nested_float(payload: Mapping[str, Any], *path: str) -> Optional[float]:
    current: Any = payload
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return _safe_float(current)


def _extract_side(row: Mapping[str, Any]) -> str:
    payload = _payload(row)
    side = payload.get("side")
    if side:
        return str(side).lower()
    status = str(row.get("event_status") or "")
    if status.startswith("buy_"):
        return "buy"
    if status.startswith("sell_"):
        return "sell"
    return "unknown"


def _extract_reference_price(row: Mapping[str, Any]) -> Optional[float]:
    payload = _payload(row)
    for key in ("signal_price", "price", "expected_price", "reference_price"):
        value = _safe_float(payload.get(key))
        if value is not None:
            return value
    return None


def _extract_cost_bps(row: Mapping[str, Any]) -> float:
    payload = _payload(row)
    for path in (
        ("cost_bps",),
        ("total_cost_bps",),
        ("edge_context", "total_cost_bps"),
        ("opportunity", "cost_bps"),
    ):
        value = _nested_float(payload, *path)
        if value is not None:
            return max(0.0, float(value))
    return 0.0


def _is_rejected(status: str) -> bool:
    lowered = status.lower()
    return "reject" in lowered or "ignored" in lowered or "blocked" in lowered


def _classify(status: str, net_return_bps: float, config: DecisionLearningConfig) -> str:
    rejected = _is_rejected(status)
    if rejected and net_return_bps >= config.take_profit_bps:
        return "missed_profit"
    if rejected and net_return_bps <= -config.stop_loss_bps:
        return "saved_loss"
    if rejected and net_return_bps > 0.0:
        return "rejected_positive"
    if rejected and net_return_bps < 0.0:
        return "rejected_negative"
    if not rejected and net_return_bps >= config.take_profit_bps:
        return "accepted_positive"
    if not rejected and net_return_bps <= -config.stop_loss_bps:
        return "accepted_negative"
    if not rejected and net_return_bps != 0.0:
        return "accepted_flat"
    return "flat"


def _samples_after_decision(
    row: Mapping[str, Any],
    price_samples: Iterable[Mapping[str, Any]],
    *,
    horizon_minutes: int,
) -> tuple[list[dict[str, Any]], Optional[str]]:
    created = _parse_dt(row.get("created_at"))
    if created is None:
        return [], "missing_decision_timestamp"
    end = created + timedelta(minutes=max(1, int(horizon_minutes)))
    selected: list[dict[str, Any]] = []
    for sample in price_samples or []:
        ts = _parse_dt(sample.get("observed_at"))
        price = _safe_float(sample.get("price"))
        if ts is None or price is None:
            continue
        if created <= ts <= end:
            selected.append({"timestamp": ts, "price": float(price)})
    selected.sort(key=lambda item: item["timestamp"])
    return selected, None


def _evaluate_triple_barrier(
    row: Mapping[str, Any],
    *,
    price_samples: Iterable[Mapping[str, Any]],
    horizon_minutes: int,
    config: DecisionLearningConfig,
) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    side = _extract_side(row)
    if side != "buy":
        return None, "unsupported_side"
    reference_price = _extract_reference_price(row)
    if reference_price is None:
        return None, "missing_reference_price"
    selected, reason = _samples_after_decision(row, price_samples, horizon_minutes=horizon_minutes)
    if reason is not None:
        return None, reason
    if len(selected) < config.min_path_samples:
        return None, "insufficient_path_samples"

    estimated_cost_bps = _extract_cost_bps(row)
    status = str(row.get("event_status") or "unknown")
    barrier_touched = "vertical_expiry"
    barrier_touched_at = selected[-1]["timestamp"]
    evaluation_price = float(selected[-1]["price"])
    gross_return_bps = ((evaluation_price / reference_price) - 1.0) * 10_000.0
    net_return_bps = gross_return_bps - estimated_cost_bps
    max_net_return_bps = net_return_bps
    min_net_return_bps = net_return_bps

    for sample in selected:
        sample_price = float(sample["price"])
        sample_gross_bps = ((sample_price / reference_price) - 1.0) * 10_000.0
        sample_net_bps = sample_gross_bps - estimated_cost_bps
        max_net_return_bps = max(max_net_return_bps, sample_net_bps)
        min_net_return_bps = min(min_net_return_bps, sample_net_bps)
        if sample_net_bps >= config.take_profit_bps:
            barrier_touched = "take_profit"
            barrier_touched_at = sample["timestamp"]
            evaluation_price = sample_price
            gross_return_bps = sample_gross_bps
            net_return_bps = sample_net_bps
            break
        if sample_net_bps <= -config.stop_loss_bps:
            barrier_touched = "stop_loss"
            barrier_touched_at = sample["timestamp"]
            evaluation_price = sample_price
            gross_return_bps = sample_gross_bps
            net_return_bps = sample_net_bps
            break

    outcome_label = _classify(status, net_return_bps, config)
    now = datetime.now(timezone.utc).isoformat()
    payload = _payload(row)
    return {
        "outcome_id": f"out_{uuid.uuid4().hex}",
        "decision_ledger_id": int(row.get("id")),
        "decision_event_id": row.get("event_id"),
        "decision_id": row.get("decision_id"),
        "signal_id": row.get("signal_id"),
        "instance_id": row.get("instance_id"),
        "symbol": str(row.get("symbol") or "UNKNOWN"),
        "strategy": row.get("strategy"),
        "engine": row.get("engine"),
        "side": side,
        "original_status": status,
        "rejection_reason": row.get("reason"),
        "reference_price": float(reference_price),
        "evaluation_price": float(evaluation_price),
        "gross_return_bps": float(gross_return_bps),
        "estimated_cost_bps": float(estimated_cost_bps),
        "net_return_bps": float(net_return_bps),
        "horizon_minutes": int(horizon_minutes),
        "outcome_label": outcome_label,
        "source": "decision_learning_triple_barrier",
        "payload": {
            "method": "triple_barrier",
            "barrier_touched": barrier_touched,
            "barrier_touched_at": barrier_touched_at.isoformat(),
            "sample_count": len(selected),
            "max_net_return_bps": round(float(max_net_return_bps), 6),
            "min_net_return_bps": round(float(min_net_return_bps), 6),
            "decision_payload": _decision_feature_payload(payload),
        },
        "decision_created_at": row.get("created_at"),
        "evaluated_at": now,
        "created_at": now,
    }, None


def build_outcome_for_decision(
    row: Mapping[str, Any],
    *,
    price_by_symbol: Mapping[str, float],
    price_samples: Iterable[Mapping[str, Any]] = (),
    horizon_minutes: int,
    config: DecisionLearningConfig,
) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    path_outcome, path_reason = _evaluate_triple_barrier(
        row,
        price_samples=price_samples,
        horizon_minutes=horizon_minutes,
        config=config,
    )
    if path_outcome is not None:
        return path_outcome, None
    if not config.allow_proxy_fallback:
        return None, path_reason

    side = _extract_side(row)
    if side != "buy":
        return None, "unsupported_side"
    symbol = str(row.get("symbol") or "UNKNOWN")
    reference_price = _extract_reference_price(row)
    if reference_price is None:
        return None, "missing_reference_price"
    evaluation_price = None
    for alias in _symbol_aliases(symbol):
        evaluation_price = _safe_float(price_by_symbol.get(alias))
        if evaluation_price is not None:
            break
    if evaluation_price is None:
        return None, "missing_evaluation_price"

    gross_return_bps = ((evaluation_price / reference_price) - 1.0) * 10_000.0
    estimated_cost_bps = _extract_cost_bps(row)
    net_return_bps = gross_return_bps - estimated_cost_bps
    status = str(row.get("event_status") or "unknown")
    outcome_label = _classify(status, net_return_bps, config)
    now = datetime.now(timezone.utc).isoformat()
    payload = _payload(row)

    return {
        "outcome_id": f"out_{uuid.uuid4().hex}",
        "decision_ledger_id": int(row.get("id")),
        "decision_event_id": row.get("event_id"),
        "decision_id": row.get("decision_id"),
        "signal_id": row.get("signal_id"),
        "instance_id": row.get("instance_id"),
        "symbol": symbol,
        "strategy": row.get("strategy"),
        "engine": row.get("engine"),
        "side": side,
        "original_status": status,
        "rejection_reason": row.get("reason"),
        "reference_price": float(reference_price),
        "evaluation_price": float(evaluation_price),
        "gross_return_bps": float(gross_return_bps),
        "estimated_cost_bps": float(estimated_cost_bps),
        "net_return_bps": float(net_return_bps),
        "horizon_minutes": int(horizon_minutes),
        "outcome_label": outcome_label,
        "source": "decision_learning_current_price_proxy",
        "payload": {
            "method": "point_in_time_proxy",
            "note": "Uses latest runtime price after horizon; not a path-sensitive triple-barrier label.",
            "decision_payload": _decision_feature_payload(payload),
        },
        "decision_created_at": row.get("created_at"),
        "evaluated_at": now,
        "created_at": now,
    }, None


def summarize_outcomes(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    by_label: dict[str, int] = {}
    by_symbol: dict[str, dict[str, Any]] = {}
    by_reason: dict[str, int] = {}
    by_source: dict[str, int] = {}
    total_net_bps = 0.0
    count = 0
    for row in rows or []:
        count += 1
        label = str(row.get("outcome_label") or "unknown")
        symbol = str(row.get("symbol") or "UNKNOWN")
        reason = str(row.get("rejection_reason") or "accepted")
        source = str(row.get("source") or "unknown")
        net = float(row.get("net_return_bps") or 0.0)
        total_net_bps += net
        by_label[label] = by_label.get(label, 0) + 1
        by_reason[reason] = by_reason.get(reason, 0) + 1
        by_source[source] = by_source.get(source, 0) + 1
        bucket = by_symbol.setdefault(symbol, {"count": 0, "avg_net_return_bps": 0.0, "labels": {}})
        bucket["count"] += 1
        bucket["avg_net_return_bps"] += net
        bucket["labels"][label] = bucket["labels"].get(label, 0) + 1
    for bucket in by_symbol.values():
        bucket["avg_net_return_bps"] = round(bucket["avg_net_return_bps"] / max(1, int(bucket["count"])), 3)
    return {
        "evaluated": count,
        "avg_net_return_bps": round(total_net_bps / max(1, count), 3) if count else 0.0,
        "by_label": dict(sorted(by_label.items(), key=lambda kv: kv[1], reverse=True)),
        "by_reason": dict(sorted(by_reason.items(), key=lambda kv: kv[1], reverse=True)),
        "by_source": dict(sorted(by_source.items(), key=lambda kv: kv[1], reverse=True)),
        "by_symbol": dict(sorted(by_symbol.items(), key=lambda kv: kv[1]["count"], reverse=True)),
    }


class DecisionLearningEngine:
    def __init__(self, config: Optional[DecisionLearningConfig] = None) -> None:
        self.config = config or DecisionLearningConfig.from_env()

    async def refresh(self, *, persistence: Any, instances: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
        instances_list = list(instances or [])
        if not self.config.enabled:
            recent = await persistence.get_signal_outcomes(limit=self.config.recent_limit)
            return {
                "enabled": False,
                "config": self.config.to_dict(),
                "refreshed": 0,
                "price_samples_recorded": 0,
                "price_samples_purged": 0,
                "skipped": {},
                "summary": summarize_outcomes(recent),
                "recent": recent,
            }

        extracted_samples = extract_market_price_samples(
            instances_list,
            interval_seconds=self.config.price_sample_interval_seconds,
        )
        samples_recorded = 0
        samples_purged = 0
        if hasattr(persistence, "append_market_price_samples"):
            samples_recorded = await persistence.append_market_price_samples(extracted_samples)
        if hasattr(persistence, "purge_market_price_samples"):
            samples_purged = await persistence.purge_market_price_samples(
                older_than_hours=self.config.price_retention_hours,
            )

        price_by_symbol = build_price_map(instances_list)
        refreshed = 0
        skipped: dict[str, int] = {}
        for horizon in self.config.horizons_minutes:
            candidates = await persistence.get_decision_outcome_candidates(
                horizon_minutes=horizon,
                limit=self.config.max_candidates_per_horizon,
            )
            for row in candidates:
                price_samples = []
                created = _parse_dt(row.get("created_at"))
                if created is not None and hasattr(persistence, "get_market_price_samples"):
                    end = created + timedelta(minutes=max(1, int(horizon)))
                    price_samples = await persistence.get_market_price_samples(
                        symbols=sorted(_symbol_aliases(row.get("symbol"))),
                        start_at=created.isoformat(),
                        end_at=end.isoformat(),
                        limit=10_000,
                    )
                outcome, reason = build_outcome_for_decision(
                    row,
                    price_by_symbol=price_by_symbol,
                    price_samples=price_samples,
                    horizon_minutes=horizon,
                    config=self.config,
                )
                if outcome is None:
                    skipped[str(reason or "unknown")] = skipped.get(str(reason or "unknown"), 0) + 1
                    continue
                written = await persistence.upsert_signal_outcome(**outcome)
                if written:
                    refreshed += 1

        recent = await persistence.get_signal_outcomes(limit=self.config.recent_limit)
        return {
            "enabled": True,
            "config": self.config.to_dict(),
            "refreshed": refreshed,
            "price_samples_recorded": samples_recorded,
            "price_samples_purged": samples_purged,
            "skipped": skipped,
            "summary": summarize_outcomes(recent),
            "recent": recent,
        }

    async def snapshot(self, *, persistence: Any) -> dict[str, Any]:
        recent = await persistence.get_signal_outcomes(limit=self.config.recent_limit)
        return {
            "enabled": self.config.enabled,
            "config": self.config.to_dict(),
            "refreshed": 0,
            "price_samples_recorded": 0,
            "price_samples_purged": 0,
            "skipped": {},
            "summary": summarize_outcomes(recent),
            "recent": recent,
        }
