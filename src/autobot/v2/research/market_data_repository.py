"""Historical market-data loading and validation for AUTOBOT research."""

from __future__ import annotations

import csv
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


REQUIRED_OHLCV_COLUMNS = {"timestamp", "open", "high", "low", "close", "volume"}


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), timezone.utc)
    text = str(value).strip()
    if not text:
        raise ValueError("timestamp is required")
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _safe_float(value: Any, *, field_name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"{field_name} must be finite")
    return result


@dataclass(frozen=True)
class MarketBar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    symbol: str
    timeframe: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(
        cls,
        row: Mapping[str, Any],
        *,
        default_symbol: str = "UNKNOWN",
        default_timeframe: str = "unknown",
    ) -> "MarketBar":
        missing = REQUIRED_OHLCV_COLUMNS - set(row.keys())
        if missing:
            raise ValueError(f"missing OHLCV columns: {sorted(missing)}")
        bar = cls(
            timestamp=_parse_timestamp(row["timestamp"]),
            open=_safe_float(row["open"], field_name="open"),
            high=_safe_float(row["high"], field_name="high"),
            low=_safe_float(row["low"], field_name="low"),
            close=_safe_float(row["close"], field_name="close"),
            volume=_safe_float(row["volume"], field_name="volume"),
            symbol=str(row.get("symbol") or default_symbol).upper(),
            timeframe=str(row.get("timeframe") or default_timeframe),
            metadata={
                key: value
                for key, value in row.items()
                if key not in REQUIRED_OHLCV_COLUMNS | {"symbol", "timeframe"}
            },
        )
        bar.validate()
        return bar

    def validate(self) -> None:
        if self.open <= 0.0 or self.high <= 0.0 or self.low <= 0.0 or self.close <= 0.0:
            raise ValueError("OHLC prices must be positive")
        if self.volume < 0.0:
            raise ValueError("volume cannot be negative")
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("high must be at least open/close/low")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("low must be at most open/close/high")
        if not self.symbol:
            raise ValueError("symbol is required")
        if not self.timeframe:
            raise ValueError("timeframe is required")

    def key(self) -> tuple[str, str, datetime]:
        return (self.symbol, self.timeframe, self.timestamp)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        return data


@dataclass(frozen=True)
class MarketDataQualityReport:
    row_count: int
    symbols: tuple[str, ...]
    timeframes: tuple[str, ...]
    start_at: datetime | None
    end_at: datetime | None
    duplicate_count: int
    is_chronological: bool
    gap_count: int
    max_gap_seconds: float
    invalid_ohlc_count: int = 0
    warnings: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return (
            self.row_count > 0
            and self.duplicate_count == 0
            and self.is_chronological
            and self.invalid_ohlc_count == 0
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["start_at"] = self.start_at.isoformat() if self.start_at else None
        data["end_at"] = self.end_at.isoformat() if self.end_at else None
        return data


class MarketDataRepository:
    """Load, normalize and validate OHLCV market data."""

    def load_csv(
        self,
        path: str | Path,
        *,
        default_symbol: str = "UNKNOWN",
        default_timeframe: str = "unknown",
        sort: bool = True,
    ) -> list[MarketBar]:
        with Path(path).open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise ValueError("CSV file has no header")
            missing = REQUIRED_OHLCV_COLUMNS - set(reader.fieldnames)
            if missing:
                raise ValueError(f"missing OHLCV columns: {sorted(missing)}")
            bars = [
                MarketBar.from_mapping(
                    row,
                    default_symbol=default_symbol,
                    default_timeframe=default_timeframe,
                )
                for row in reader
            ]
        return self.normalize(bars) if sort else bars

    def load_parquet(
        self,
        path: str | Path,
        *,
        default_symbol: str = "UNKNOWN",
        default_timeframe: str = "unknown",
    ) -> list[MarketBar]:
        try:
            import pandas as pd  # type: ignore
        except Exception as exc:
            raise ImportError("pandas with parquet support is required to load parquet data") from exc
        frame = pd.read_parquet(path)
        return self.normalize(
            MarketBar.from_mapping(
                row,
                default_symbol=default_symbol,
                default_timeframe=default_timeframe,
            )
            for row in frame.to_dict(orient="records")
        )

    def save_parquet(self, bars: Sequence[MarketBar], path: str | Path) -> Path:
        try:
            import pandas as pd  # type: ignore
        except Exception as exc:
            raise ImportError("pandas with parquet support is required to save parquet data") from exc
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame([bar.to_dict() for bar in bars]).to_parquet(output, index=False)
        return output

    def save_csv(self, bars: Sequence[MarketBar], path: str | Path) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        rows = [bar.to_dict() for bar in bars]
        with output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["timestamp", "symbol", "timeframe", "open", "high", "low", "close", "volume", "metadata"],
            )
            writer.writeheader()
            writer.writerows(rows)
        return output

    @staticmethod
    def normalize(bars: Iterable[MarketBar]) -> list[MarketBar]:
        return sorted(list(bars), key=lambda bar: (bar.symbol, bar.timeframe, bar.timestamp))

    def validate(
        self,
        bars: Sequence[MarketBar],
        *,
        expected_interval_seconds: float | None = None,
    ) -> MarketDataQualityReport:
        if not bars:
            return MarketDataQualityReport(
                row_count=0,
                symbols=(),
                timeframes=(),
                start_at=None,
                end_at=None,
                duplicate_count=0,
                is_chronological=True,
                gap_count=0,
                max_gap_seconds=0.0,
                warnings=("empty_dataset",),
            )
        invalid = 0
        for bar in bars:
            try:
                bar.validate()
            except ValueError:
                invalid += 1
        keys = [bar.key() for bar in bars]
        duplicate_count = len(keys) - len(set(keys))
        chronological = all(
            bars[index - 1].timestamp <= bars[index].timestamp
            for index in range(1, len(bars))
            if bars[index - 1].symbol == bars[index].symbol
            and bars[index - 1].timeframe == bars[index].timeframe
        )
        gap_count = 0
        max_gap = 0.0
        for group in self._group_by_symbol_timeframe(bars).values():
            sorted_group = sorted(group, key=lambda bar: bar.timestamp)
            deltas = [
                (sorted_group[index].timestamp - sorted_group[index - 1].timestamp).total_seconds()
                for index in range(1, len(sorted_group))
            ]
            if not deltas:
                continue
            threshold = expected_interval_seconds
            if threshold is None and len(deltas) >= 3:
                median = sorted(deltas)[len(deltas) // 2]
                threshold = median * 3.0
            if threshold:
                gap_count += sum(1 for delta in deltas if delta > threshold * 1.5)
            max_gap = max(max_gap, max(deltas))
        warnings: list[str] = []
        if duplicate_count:
            warnings.append("duplicate_bars")
        if not chronological:
            warnings.append("not_chronological")
        if gap_count:
            warnings.append("data_gaps_detected")
        if invalid:
            warnings.append("invalid_ohlc_detected")
        return MarketDataQualityReport(
            row_count=len(bars),
            symbols=tuple(sorted({bar.symbol for bar in bars})),
            timeframes=tuple(sorted({bar.timeframe for bar in bars})),
            start_at=min(bar.timestamp for bar in bars),
            end_at=max(bar.timestamp for bar in bars),
            duplicate_count=duplicate_count,
            is_chronological=chronological,
            gap_count=gap_count,
            max_gap_seconds=max_gap,
            invalid_ohlc_count=invalid,
            warnings=tuple(warnings),
        )

    @staticmethod
    def _group_by_symbol_timeframe(bars: Sequence[MarketBar]) -> dict[tuple[str, str], list[MarketBar]]:
        groups: dict[tuple[str, str], list[MarketBar]] = {}
        for bar in bars:
            groups.setdefault((bar.symbol, bar.timeframe), []).append(bar)
        return groups
