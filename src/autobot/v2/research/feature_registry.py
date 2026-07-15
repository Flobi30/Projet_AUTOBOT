"""Versioned, point-in-time research features for AUTOBOT.

This module deliberately has no dependency on the runtime order, paper, or
execution paths.  The same deterministic functions are used by historical
research and shadow replays so feature definitions cannot silently diverge.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Sequence

from autobot.v2.contracts import FeatureValue, MarketIdentity


READY = "READY"
DATA_MISSING = "DATA_MISSING"
WAITING_FOR_MORE_DATA = "WAITING_FOR_MORE_DATA"

SUPPORTED_FEATURE_KINDS = {
    "return_bps",
    "momentum_bps",
    "volatility_bps",
    "atr_bps",
    "spread_bps",
    "funding_rate_relative",
    "basis_bps",
    "open_interest_change_pct",
}


@dataclass(frozen=True)
class FeatureDefinition:
    """An immutable feature contract with point-in-time availability rules."""

    feature_id: str
    version: str
    source_dataset: str
    kind: str
    lookback: int = 1
    availability_delay_seconds: int = 0
    missing_value_policy: str = DATA_MISSING

    def __post_init__(self) -> None:
        if not self.feature_id.strip() or not self.version.strip() or not self.source_dataset.strip():
            raise ValueError("feature_id, version and source_dataset are required")
        if self.kind not in SUPPORTED_FEATURE_KINDS:
            raise ValueError(f"unsupported feature kind: {self.kind}")
        if self.lookback <= 0:
            raise ValueError("lookback must be positive")
        if self.availability_delay_seconds < 0:
            raise ValueError("availability_delay_seconds must be non-negative")
        if self.missing_value_policy not in {DATA_MISSING, WAITING_FOR_MORE_DATA}:
            raise ValueError("missing_value_policy must be DATA_MISSING or WAITING_FOR_MORE_DATA")

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class FeatureParityResult:
    snapshot_id: str
    registry_fingerprint: str
    feature_count: int
    parity_ok: bool
    differences: tuple[str, ...] = ()


class FeatureRegistry:
    """A small explicit registry shared by research and shadow replay code."""

    def __init__(self, definitions: Iterable[FeatureDefinition] = ()) -> None:
        self._definitions: dict[str, FeatureDefinition] = {}
        for definition in definitions:
            self.register(definition)

    def register(self, definition: FeatureDefinition) -> None:
        existing = self._definitions.get(definition.feature_id)
        if existing and existing != definition:
            raise ValueError(f"feature_id already registered with a different definition: {definition.feature_id}")
        self._definitions[definition.feature_id] = definition

    def get(self, feature_id: str) -> FeatureDefinition:
        try:
            return self._definitions[feature_id]
        except KeyError as exc:
            raise KeyError(f"unknown feature: {feature_id}") from exc

    def definitions(self) -> tuple[FeatureDefinition, ...]:
        return tuple(self._definitions[key] for key in sorted(self._definitions))

    @property
    def fingerprint(self) -> str:
        payload = [asdict(item) for item in self.definitions()]
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    def compute_series(
        self,
        *,
        rows: Sequence[Mapping[str, Any]],
        market: MarketIdentity,
        timeframe: str,
        source_snapshot_id: str,
        feature_ids: Sequence[str] | None = None,
        as_of_time: datetime | None = None,
    ) -> tuple[FeatureValue, ...]:
        """Return the materialized feature series for callers that need it."""

        return tuple(
            self.iter_series(
                rows=rows,
                market=market,
                timeframe=timeframe,
                source_snapshot_id=source_snapshot_id,
                feature_ids=feature_ids,
                as_of_time=as_of_time,
            )
        )

    def iter_series(
        self,
        *,
        rows: Sequence[Mapping[str, Any]],
        market: MarketIdentity,
        timeframe: str,
        source_snapshot_id: str,
        feature_ids: Sequence[str] | None = None,
        as_of_time: datetime | None = None,
    ) -> Iterable[FeatureValue]:
        """Compute features using only rows available at each target bar.

        Rows are sorted by ``available_time`` and every target history is
        bounded by both its event time and availability time.  This guards
        against future-bar leakage even when delayed data arrives out of order.
        The iterator keeps batch materialization bounded instead of retaining
        every feature value in memory.
        """

        definitions = tuple(self.get(item) for item in (feature_ids or tuple(self._definitions)))
        cutoff = _utc(as_of_time) if as_of_time else None
        normalized = _normalize_rows(rows)
        # Canonical OHLCV is ordered by both event and availability time.  In
        # that ordinary case a target can only observe a bounded prefix, so
        # retain only the largest required feature window.  The fallback keeps
        # the stricter general rule for delayed/out-of-order data rather than
        # silently assuming temporal monotonicity.
        monotonic_event_time = _event_times_are_monotonic(normalized)
        max_lookback = max((definition.lookback for definition in definitions), default=1)
        for index, target in enumerate(normalized):
            if cutoff and target["available_time"] > cutoff:
                continue
            if monotonic_event_time:
                observed = normalized[max(0, index - max_lookback) : index + 1]
            else:
                observed = [
                    row
                    for row in normalized
                    if row["event_time"] <= target["event_time"] and row["available_time"] <= target["available_time"]
                ]
            for definition in definitions:
                yield _compute_feature(
                    definition,
                    observed=observed,
                    target=target,
                    market=market,
                    timeframe=timeframe,
                    source_snapshot_id=source_snapshot_id,
                )


def default_feature_registry() -> FeatureRegistry:
    """Return the bounded first feature library for research-only use."""

    return FeatureRegistry(
        (
            FeatureDefinition("return_1_bps", "1.0.0", "canonical_ohlcv", "return_bps", lookback=1),
            FeatureDefinition("momentum_3_bps", "1.0.0", "canonical_ohlcv", "momentum_bps", lookback=3),
            FeatureDefinition("volatility_20_bps", "1.0.0", "canonical_ohlcv", "volatility_bps", lookback=20),
            FeatureDefinition("atr_14_bps", "1.0.0", "canonical_ohlcv", "atr_bps", lookback=14),
            FeatureDefinition("spread_bps", "1.0.0", "ticker_snapshots", "spread_bps"),
            FeatureDefinition("funding_rate_relative", "1.0.0", "funding_rates", "funding_rate_relative"),
            FeatureDefinition("basis_bps", "1.0.0", "basis", "basis_bps"),
            FeatureDefinition("open_interest_change_24_pct", "1.0.0", "ticker_snapshots", "open_interest_change_pct", lookback=24),
        )
    )


def validate_historical_shadow_parity(
    *,
    rows: Sequence[Mapping[str, Any]],
    market: MarketIdentity,
    timeframe: str,
    source_snapshot_id: str,
    registry: FeatureRegistry | None = None,
    feature_ids: Sequence[str] | None = None,
) -> FeatureParityResult:
    """Prove batch and shadow replay use identical deterministic features."""

    active_registry = registry or default_feature_registry()
    historical = active_registry.compute_series(
        rows=rows,
        market=market,
        timeframe=timeframe,
        source_snapshot_id=source_snapshot_id,
        feature_ids=feature_ids,
    )
    shadow = active_registry.compute_series(
        rows=tuple(reversed(tuple(rows))),
        market=market,
        timeframe=timeframe,
        source_snapshot_id=source_snapshot_id,
        feature_ids=feature_ids,
    )
    historical_payload = [_feature_payload(item) for item in historical]
    shadow_payload = [_feature_payload(item) for item in shadow]
    differences = () if historical_payload == shadow_payload else ("historical_shadow_feature_payload_mismatch",)
    return FeatureParityResult(
        snapshot_id=source_snapshot_id,
        registry_fingerprint=active_registry.fingerprint,
        feature_count=len(historical),
        parity_ok=not differences,
        differences=differences,
    )


def _compute_feature(
    definition: FeatureDefinition,
    *,
    observed: Sequence[Mapping[str, Any]],
    target: Mapping[str, Any],
    market: MarketIdentity,
    timeframe: str,
    source_snapshot_id: str,
) -> FeatureValue:
    available_time = target["available_time"] + timedelta(seconds=definition.availability_delay_seconds)
    status, value, metadata = _feature_value(definition, observed, target)
    return FeatureValue(
        feature_id=definition.feature_id,
        feature_version=definition.version,
        market=market,
        timeframe=timeframe,
        event_time=target["event_time"],
        available_time=available_time,
        source_snapshot_id=source_snapshot_id,
        value=value,
        status=status,
        metadata={
            "definition_fingerprint": definition.fingerprint,
            "source_dataset": definition.source_dataset,
            "lookback": definition.lookback,
            **metadata,
        },
    )


def _feature_value(
    definition: FeatureDefinition,
    observed: Sequence[Mapping[str, Any]],
    target: Mapping[str, Any],
) -> tuple[str, float | None, dict[str, Any]]:
    kind = definition.kind
    if kind in {"return_bps", "momentum_bps", "volatility_bps", "atr_bps"}:
        return _ohlcv_feature_value(definition, observed)
    if kind == "spread_bps":
        bid = _number(target.get("bid"))
        ask = _number(target.get("ask"))
        if bid is None or ask is None or bid <= 0 or ask < bid:
            return DATA_MISSING, None, {"reason": "bid_ask_missing_or_invalid"}
        return READY, ((ask - bid) / ((ask + bid) / 2.0)) * 10_000.0, {}
    if kind == "funding_rate_relative":
        funding = _number(target.get("funding_rate_relative") or target.get("current_funding_rate"))
        if funding is None:
            return DATA_MISSING, None, {"reason": "funding_rate_missing"}
        return READY, funding, {}
    if kind == "basis_bps":
        confidence = str(target.get("confidence_status") or "")
        basis = _number(target.get("basis_bps"))
        if confidence != "MARK_INDEX_SAME_QUOTE":
            return DATA_MISSING, None, {"reason": "basis_reference_unverified"}
        if basis is None:
            return DATA_MISSING, None, {"reason": "basis_missing"}
        return READY, basis, {}
    if kind == "open_interest_change_pct":
        if len(observed) <= definition.lookback:
            return WAITING_FOR_MORE_DATA, None, {"reason": "open_interest_lookback_not_met"}
        current = _number(observed[-1].get("open_interest"))
        previous = _number(observed[-1 - definition.lookback].get("open_interest"))
        if current is None or previous is None or previous <= 0:
            return DATA_MISSING, None, {"reason": "open_interest_missing_or_invalid"}
        return READY, ((current / previous) - 1.0) * 100.0, {}
    return DATA_MISSING, None, {"reason": "unsupported_feature_kind"}


def _ohlcv_feature_value(
    definition: FeatureDefinition,
    observed: Sequence[Mapping[str, Any]],
) -> tuple[str, float | None, dict[str, Any]]:
    closes = [_number(row.get("close")) for row in observed]
    if any(value is None or value <= 0 for value in closes):
        return DATA_MISSING, None, {"reason": "ohlcv_close_missing_or_invalid"}
    lookback = definition.lookback
    if definition.kind in {"return_bps", "momentum_bps"}:
        if len(closes) <= lookback:
            return WAITING_FOR_MORE_DATA, None, {"reason": "close_lookback_not_met"}
        return READY, ((float(closes[-1]) / float(closes[-1 - lookback])) - 1.0) * 10_000.0, {}
    if definition.kind == "volatility_bps":
        if len(closes) <= lookback:
            return WAITING_FOR_MORE_DATA, None, {"reason": "volatility_lookback_not_met"}
        window = [float(value) for value in closes[-(lookback + 1) :]]
        returns = [math.log(current / previous) * 10_000.0 for previous, current in zip(window, window[1:])]
        mean = sum(returns) / len(returns)
        variance = sum((item - mean) ** 2 for item in returns) / len(returns)
        return READY, math.sqrt(variance), {}
    if definition.kind == "atr_bps":
        if len(observed) <= lookback:
            return WAITING_FOR_MORE_DATA, None, {"reason": "atr_lookback_not_met"}
        true_ranges: list[float] = []
        rows = observed[-(lookback + 1) :]
        for previous, current in zip(rows, rows[1:]):
            prev_close = _number(previous.get("close"))
            high = _number(current.get("high"))
            low = _number(current.get("low"))
            if prev_close is None or high is None or low is None or prev_close <= 0 or high <= 0 or low <= 0:
                return DATA_MISSING, None, {"reason": "atr_ohlcv_missing_or_invalid"}
            true_ranges.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
        current_close = float(closes[-1])
        return READY, (sum(true_ranges) / len(true_ranges) / current_close) * 10_000.0, {}
    return DATA_MISSING, None, {"reason": "unsupported_ohlcv_feature"}


def _normalize_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        event_time = _row_time(row, "event_time", fallback="open_timestamp")
        available_time = _row_time(row, "available_time", fallback="bar_close_time")
        if event_time is None or available_time is None:
            raise ValueError("feature rows require timezone-aware event_time and available_time")
        if available_time < event_time:
            raise ValueError("feature row available_time cannot precede event_time")
        normalized.append({**dict(row), "event_time": event_time, "available_time": available_time})
    return sorted(normalized, key=lambda item: (item["available_time"], item["event_time"], json.dumps(item, default=str, sort_keys=True)))


def _event_times_are_monotonic(rows: Sequence[Mapping[str, Any]]) -> bool:
    return all(
        rows[index - 1]["event_time"] <= rows[index]["event_time"]
        for index in range(1, len(rows))
    )


def _row_time(row: Mapping[str, Any], key: str, *, fallback: str) -> datetime | None:
    value = row.get(key) or row.get(fallback) or row.get("timestamp")
    if not value:
        return None
    if isinstance(value, datetime):
        return _utc(value)
    text = str(value).replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    return _utc(parsed)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc).replace(microsecond=0)


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def _feature_payload(value: FeatureValue) -> dict[str, Any]:
    return {
        "feature_id": value.feature_id,
        "feature_version": value.feature_version,
        "event_time": value.event_time.isoformat(),
        "available_time": value.available_time.isoformat(),
        "value": value.value,
        "status": value.status,
        "metadata": dict(value.metadata),
    }
