"""Bounded forward public microstructure collection for research.

This job deliberately lives outside AUTOBOT's runtime.  It records one or a
few public Kraken top-of-book samples, canonicalizes them immediately, and
writes only under the research-data boundary.  The result is evidence for
cost/capacity research, never an execution signal or permission.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .canonical_microstructure_store import (
    CanonicalMicrostructureConfig,
    CanonicalMicrostructureSnapshot,
    build_canonical_microstructure_snapshot,
)
from .kraken_symbol_mapping import AssetPairsFetcher
from .spread_depth_recorder import DepthFetcher, SpreadDepthRecorderConfig, SpreadDepthRecorderResult, record_spread_depth


@dataclass(frozen=True)
class ForwardMicrostructureCollectionConfig:
    run_id: str
    symbols: tuple[str, ...]
    raw_output_dir: Path = Path("data/research/forward/microstructure")
    canonical_output_dir: Path = Path("data/research/canonical/microstructure")
    manifest_dir: Path = Path("data/research/manifests")
    report_dir: Path = Path("data/research/reports/microstructure")
    depth_count: int = 10
    samples: int = 1
    sample_interval_seconds: float = 0.0
    max_runtime_seconds: float = 300.0

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id must not be empty")
        if not self.symbols:
            raise ValueError("symbols must not be empty")
        if self.depth_count <= 0 or self.samples <= 0:
            raise ValueError("depth_count and samples must be positive")
        if self.sample_interval_seconds < 0.0:
            raise ValueError("sample_interval_seconds cannot be negative")
        if self.max_runtime_seconds <= 0.0:
            raise ValueError("max_runtime_seconds must be positive")


@dataclass(frozen=True)
class ForwardMicrostructureCollectionResult:
    run_id: str
    generated_at: str
    recorder: SpreadDepthRecorderResult
    canonical_snapshot: CanonicalMicrostructureSnapshot | None
    status: str
    manifest_path: str | None = None
    markdown_report_path: str | None = None
    safety_notes: tuple[str, ...] = (
        "Forward microstructure collection is research-only.",
        "Public Kraken depth endpoint only.",
        "No secret, runtime state database, paper/live order, or promotion is used.",
        "Canonical REST observations do not prove runtime-feed parity.",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "recorder": self.recorder.to_dict(),
            "canonical_snapshot": self.canonical_snapshot.to_dict() if self.canonical_snapshot else None,
            "status": self.status,
            "manifest_path": self.manifest_path,
            "markdown_report_path": self.markdown_report_path,
            "safety_notes": list(self.safety_notes),
        }


def collect_forward_microstructure(
    config: ForwardMicrostructureCollectionConfig,
    *,
    fetcher: DepthFetcher | None = None,
    asset_pairs_fetcher: AssetPairsFetcher | None = None,
) -> ForwardMicrostructureCollectionResult:
    recorder = record_spread_depth(
        SpreadDepthRecorderConfig(
            run_id=config.run_id,
            symbols=config.symbols,
            output_dir=config.raw_output_dir / config.run_id,
            depth_count=config.depth_count,
            samples=config.samples,
            sleep_seconds=config.sample_interval_seconds,
            max_runtime_seconds=config.max_runtime_seconds,
            export_csv=True,
            continue_on_error=True,
        ),
        fetcher=fetcher,
        asset_pairs_fetcher=asset_pairs_fetcher,
    )
    snapshot = None
    if recorder.csv_path:
        snapshot = build_canonical_microstructure_snapshot(
            CanonicalMicrostructureConfig(
                run_id=config.run_id,
                raw_paths=(Path(recorder.csv_path),),
                output_dir=config.canonical_output_dir,
                manifest_dir=config.manifest_dir,
                report_dir=config.report_dir,
            )
        )
    status = "ok" if snapshot and snapshot.canonical_row_count and not recorder.errors else "partial"
    result = ForwardMicrostructureCollectionResult(
        run_id=config.run_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        recorder=recorder,
        canonical_snapshot=snapshot,
        status=status,
    )
    return write_forward_microstructure_collection_report(result, config.report_dir)


def write_forward_microstructure_collection_report(
    result: ForwardMicrostructureCollectionResult,
    output_dir: str | Path,
) -> ForwardMicrostructureCollectionResult:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    manifest_path = output_path / f"{result.run_id}_forward_microstructure.json"
    markdown_path = output_path / f"{result.run_id}_forward_microstructure.md"
    completed = ForwardMicrostructureCollectionResult(
        **{
            **result.__dict__,
            "manifest_path": str(manifest_path),
            "markdown_report_path": str(markdown_path),
        }
    )
    manifest_path.write_text(json.dumps(completed.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(render_forward_microstructure_collection_report(completed), encoding="utf-8")
    return completed


def render_forward_microstructure_collection_report(result: ForwardMicrostructureCollectionResult) -> str:
    snapshot = result.canonical_snapshot
    lines = [
        f"# Forward Microstructure Collection - {result.run_id}",
        "",
        f"Status: `{result.status}`",
        f"Captured snapshots: `{len(result.recorder.snapshots)}`",
        f"Capture errors: `{len(result.recorder.errors)}`",
        f"Canonical rows: `{snapshot.canonical_row_count if snapshot else 0}`",
        f"Canonical snapshot: `{snapshot.snapshot_id if snapshot else 'none'}`",
        f"Runtime parity proven: `false`",
        "",
        "## Safety",
        "",
        *[f"- {note}" for note in result.safety_notes],
        "",
    ]
    return "\n".join(lines)
