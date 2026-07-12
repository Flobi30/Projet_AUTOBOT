"""Bind AUTOBOT research experiments to verified feature-snapshot evidence.

This module is intentionally research-only. It validates a materialized
feature manifest and builds an ``ExperimentSpec`` carrying the exact source
snapshot and feature versions. It does not run a strategy or import execution
code.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .experiment_registry import ExperimentSpec


class ManifestedExperimentError(ValueError):
    """Raised when feature provenance is missing or unsuitable for research."""


@dataclass(frozen=True)
class FeatureSnapshotProvenance:
    manifest_path: str
    feature_snapshot_id: str
    feature_snapshot_fingerprint: str
    source_snapshot_id: str
    source_snapshot_fingerprint: str
    feature_registry_fingerprint: str
    feature_versions: Mapping[str, str]
    feature_count: int
    parity_ok: bool
    ingestion_time_unknown_count: int

    @property
    def runtime_parity_proven(self) -> bool:
        return self.parity_ok and self.ingestion_time_unknown_count == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest_path": self.manifest_path,
            "feature_snapshot_id": self.feature_snapshot_id,
            "feature_snapshot_fingerprint": self.feature_snapshot_fingerprint,
            "source_snapshot_id": self.source_snapshot_id,
            "source_snapshot_fingerprint": self.source_snapshot_fingerprint,
            "feature_registry_fingerprint": self.feature_registry_fingerprint,
            "feature_versions": dict(self.feature_versions),
            "feature_count": self.feature_count,
            "parity_ok": self.parity_ok,
            "ingestion_time_unknown_count": self.ingestion_time_unknown_count,
            "runtime_parity_proven": self.runtime_parity_proven,
            "research_only": True,
            "paper_capital_allowed": False,
            "live_allowed": False,
            "promotable": False,
        }


def load_feature_snapshot_provenance(path: str | Path) -> FeatureSnapshotProvenance:
    manifest_path = Path(path)
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestedExperimentError(f"invalid feature snapshot manifest: {manifest_path}") from exc
    if not isinstance(payload, Mapping):
        raise ManifestedExperimentError("feature snapshot manifest must be an object")
    if str(payload.get("status") or "").upper() != "READY":
        raise ManifestedExperimentError("feature snapshot status must be READY")
    if payload.get("parity_ok") is not True:
        raise ManifestedExperimentError("feature snapshot parity must be true")
    feature_count = int(payload.get("feature_count") or 0)
    if feature_count <= 0:
        raise ManifestedExperimentError("feature snapshot must contain feature values")
    versions = payload.get("feature_versions")
    if not isinstance(versions, Mapping) or not versions:
        raise ManifestedExperimentError("feature snapshot feature_versions are required")
    normalized_versions = {str(key).strip(): str(value).strip() for key, value in versions.items()}
    if not all(normalized_versions) or not all(normalized_versions.values()):
        raise ManifestedExperimentError("feature snapshot feature_versions are invalid")
    return FeatureSnapshotProvenance(
        manifest_path=str(manifest_path),
        feature_snapshot_id=_required(payload.get("feature_snapshot_id"), "feature_snapshot_id"),
        feature_snapshot_fingerprint=_required(payload.get("fingerprint"), "feature snapshot fingerprint"),
        source_snapshot_id=_required(payload.get("source_snapshot_id"), "source_snapshot_id"),
        source_snapshot_fingerprint=_required(payload.get("source_snapshot_fingerprint"), "source snapshot fingerprint"),
        feature_registry_fingerprint=_required(payload.get("feature_registry_fingerprint"), "feature registry fingerprint"),
        feature_versions=normalized_versions,
        feature_count=feature_count,
        parity_ok=True,
        ingestion_time_unknown_count=max(0, int(payload.get("ingestion_time_unknown_count") or 0)),
    )


def build_manifested_experiment_spec(
    *,
    hypothesis_id: str,
    template_id: str,
    thesis: str,
    code_commit: str,
    feature_snapshot_manifest: str | Path,
    parameters: Mapping[str, Any],
    seed: int,
    cost_model: Mapping[str, Any],
    environment: Mapping[str, Any] | None = None,
) -> tuple[ExperimentSpec, FeatureSnapshotProvenance]:
    """Build a reproducible research spec from one verified feature bundle."""

    provenance = load_feature_snapshot_provenance(feature_snapshot_manifest)
    supplied_environment = dict(environment or {})
    if any(bool(supplied_environment.get(key)) for key in ("paper_capital_allowed", "live_allowed", "promotable")):
        raise ManifestedExperimentError("manifested experiment cannot enable paper capital, live or promotion")
    resolved_environment = {
        **supplied_environment,
        "feature_snapshot": provenance.to_dict(),
        "runtime_parity_proven": provenance.runtime_parity_proven,
        "research_only": True,
        "paper_capital_allowed": False,
        "live_allowed": False,
        "promotable": False,
    }
    return (
        ExperimentSpec(
            hypothesis_id=hypothesis_id,
            template_id=template_id,
            thesis=thesis,
            code_commit=code_commit,
            data_snapshot_id=provenance.source_snapshot_id,
            feature_versions=provenance.feature_versions,
            parameters=dict(parameters),
            seed=seed,
            cost_model=dict(cost_model),
            environment=resolved_environment,
        ),
        provenance,
    )


def _required(value: Any, name: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise ManifestedExperimentError(f"{name} is required")
    return result
