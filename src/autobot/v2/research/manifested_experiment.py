"""Bind AUTOBOT research experiments to verified feature-snapshot evidence.

This module is intentionally research-only. It validates a materialized
feature manifest and builds an ``ExperimentSpec`` carrying the exact source
snapshot and feature versions. It does not run a strategy or import execution
code.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
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
    snapshot_kind: str
    source_snapshot_id: str
    source_snapshot_fingerprint: str
    feature_registry_fingerprint: str
    feature_versions: Mapping[str, str]
    feature_count: int
    parity_ok: bool
    ingestion_time_unknown_count: int
    material_verified: bool = False
    bundle_content_fingerprint: str | None = None
    runtime_parity_verified: bool | None = None
    holdout_partition: Mapping[str, Any] | None = None
    holdout_partition_role: str | None = None

    @property
    def runtime_parity_proven(self) -> bool:
        if not self.material_verified:
            return False
        if self.runtime_parity_verified is not None:
            return self.parity_ok and self.runtime_parity_verified
        return self.parity_ok and self.ingestion_time_unknown_count == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_snapshot_id": self.feature_snapshot_id,
            "feature_snapshot_fingerprint": self.feature_snapshot_fingerprint,
            "snapshot_kind": self.snapshot_kind,
            "source_snapshot_id": self.source_snapshot_id,
            "source_snapshot_fingerprint": self.source_snapshot_fingerprint,
            "feature_registry_fingerprint": self.feature_registry_fingerprint,
            "feature_versions": dict(self.feature_versions),
            "feature_count": self.feature_count,
            "parity_ok": self.parity_ok,
            "ingestion_time_unknown_count": self.ingestion_time_unknown_count,
            "material_verified": self.material_verified,
            "bundle_content_fingerprint": self.bundle_content_fingerprint,
            "runtime_parity_proven": self.runtime_parity_proven,
            "holdout_partition": dict(self.holdout_partition) if self.holdout_partition else None,
            "holdout_partition_role": self.holdout_partition_role,
            "research_only": True,
            "paper_capital_allowed": False,
            "live_allowed": False,
            "promotable": False,
        }

    def reference_dict(self) -> dict[str, Any]:
        """Non-material display reference; excluded from experiment identity."""

        return {"manifest_path": self.manifest_path}


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
    raw_holdout_partition = payload.get("holdout_partition")
    if raw_holdout_partition is not None and not isinstance(raw_holdout_partition, Mapping):
        raise ManifestedExperimentError("feature snapshot holdout_partition must be an object")
    holdout_partition_role = str(payload.get("holdout_partition_role") or "").strip() or None
    if raw_holdout_partition is not None and not holdout_partition_role:
        raise ManifestedExperimentError("feature snapshot holdout partition role is required")
    snapshot_kind = str(payload.get("snapshot_kind") or "FEATURE_SNAPSHOT")
    material_verified = False
    bundle_content_fingerprint = None
    if snapshot_kind == "CANONICAL_FEATURE_SNAPSHOT":
        try:
            from .canonical_feature_snapshot import verify_canonical_feature_snapshot_manifest

            verification = verify_canonical_feature_snapshot_manifest(manifest_path)
        except (OSError, ValueError) as exc:
            raise ManifestedExperimentError(f"feature snapshot material verification failed: {exc}") from exc
        material_verified = True
        bundle_content_fingerprint = verification.bundle_content_fingerprint
    elif snapshot_kind == "DERIVATIVES_POINT_IN_TIME":
        try:
            from .derivatives_feature_snapshot import inspect_derivatives_feature_snapshot_manifest

            availability = inspect_derivatives_feature_snapshot_manifest(manifest_path)
        except (OSError, ValueError) as exc:
            raise ManifestedExperimentError(f"feature snapshot material verification failed: {exc}") from exc
        material_verified = availability.material_verified
        bundle_content_fingerprint = availability.bundle_content_fingerprint
    return FeatureSnapshotProvenance(
        manifest_path=str(manifest_path),
        feature_snapshot_id=_required(payload.get("feature_snapshot_id"), "feature_snapshot_id"),
        feature_snapshot_fingerprint=_required(payload.get("fingerprint"), "feature snapshot fingerprint"),
        snapshot_kind=snapshot_kind,
        source_snapshot_id=_required(payload.get("source_snapshot_id"), "source_snapshot_id"),
        source_snapshot_fingerprint=_required(payload.get("source_snapshot_fingerprint"), "source snapshot fingerprint"),
        feature_registry_fingerprint=_required(payload.get("feature_registry_fingerprint"), "feature registry fingerprint"),
        feature_versions=normalized_versions,
        feature_count=feature_count,
        parity_ok=True,
        ingestion_time_unknown_count=max(0, int(payload.get("ingestion_time_unknown_count") or 0)),
        material_verified=material_verified,
        bundle_content_fingerprint=bundle_content_fingerprint,
        runtime_parity_verified=(
            bool(payload.get("runtime_parity_proven"))
            if "runtime_parity_proven" in payload
            else None
        ),
        holdout_partition=(dict(raw_holdout_partition) if isinstance(raw_holdout_partition, Mapping) else None),
        holdout_partition_role=holdout_partition_role,
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
    image_ref: str | None = None,
    environment: Mapping[str, Any] | None = None,
    derivatives_snapshot_manifest: str | Path | None = None,
    holdout_id: str | None = None,
    holdout_partition_manifest: str | Path | None = None,
) -> tuple[ExperimentSpec, FeatureSnapshotProvenance]:
    """Build a reproducible research spec from one verified feature bundle."""

    resolved_image_ref = _required(image_ref, "image_ref")
    provenance = load_feature_snapshot_provenance(feature_snapshot_manifest)
    derivatives_provenance = (
        load_feature_snapshot_provenance(derivatives_snapshot_manifest)
        if derivatives_snapshot_manifest is not None
        else None
    )
    if derivatives_provenance is not None and derivatives_provenance.snapshot_kind != "DERIVATIVES_POINT_IN_TIME":
        raise ManifestedExperimentError("derivatives snapshot manifest must be DERIVATIVES_POINT_IN_TIME")
    normalized_holdout_id = str(holdout_id or "").strip() or None
    if normalized_holdout_id is None and holdout_partition_manifest is not None:
        raise ManifestedExperimentError("holdout partition requires a holdout_id")
    if normalized_holdout_id is not None and holdout_partition_manifest is None:
        raise ManifestedExperimentError("holdout_id requires a physical holdout partition manifest")
    holdout_partition = None
    if holdout_partition_manifest is not None:
        from .holdout_partition import HoldoutPartitionError, load_holdout_partition_reference

        try:
            holdout_partition = load_holdout_partition_reference(holdout_partition_manifest)
        except HoldoutPartitionError as exc:
            raise ManifestedExperimentError(f"invalid physical holdout partition: {exc}") from exc
        if normalized_holdout_id != holdout_partition.partition_id:
            raise ManifestedExperimentError("holdout_id must match the physical holdout partition_id")
        if (
            provenance.holdout_partition != holdout_partition.identity_dict()
            or provenance.holdout_partition_role != "optimization"
        ):
            raise ManifestedExperimentError(
                "feature snapshot must be materialized from the sealed optimization partition"
            )
        if derivatives_provenance is not None:
            raise ManifestedExperimentError(
                "derivatives feature snapshots require a separate physical holdout partition before final review"
            )
        if (
            holdout_partition.optimization_snapshot_id != provenance.source_snapshot_id
            or holdout_partition.optimization_snapshot_fingerprint != provenance.source_snapshot_fingerprint
        ):
            raise ManifestedExperimentError(
                "holdout partition optimization snapshot does not match the feature snapshot provenance"
            )
    supplied_environment = dict(environment or {})
    if any(bool(supplied_environment.get(key)) for key in ("paper_capital_allowed", "live_allowed", "promotable")):
        raise ManifestedExperimentError("manifested experiment cannot enable paper capital, live or promotion")
    feature_versions = dict(provenance.feature_versions)
    data_snapshot_id = provenance.source_snapshot_id
    if derivatives_provenance is not None:
        overlapping = set(feature_versions).intersection(derivatives_provenance.feature_versions)
        if overlapping:
            raise ManifestedExperimentError(f"spot and derivatives feature versions overlap: {', '.join(sorted(overlapping))}")
        feature_versions.update(derivatives_provenance.feature_versions)
        data_snapshot_id = "combined_" + sha256(
            json.dumps(
                {
                    "spot": provenance.source_snapshot_id,
                    "derivatives": derivatives_provenance.source_snapshot_id,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()[:16]
    resolved_environment = {
        **supplied_environment,
        "feature_snapshot": provenance.to_dict(),
        "runtime_parity_proven": provenance.runtime_parity_proven and (
            derivatives_provenance.runtime_parity_proven if derivatives_provenance else True
        ),
        "research_only": True,
        "paper_capital_allowed": False,
        "live_allowed": False,
        "promotable": False,
    }
    if derivatives_provenance is not None:
        resolved_environment["derivatives_snapshot"] = derivatives_provenance.to_dict()
    if holdout_partition is not None:
        # The local manifest path is intentionally excluded from the material
        # experiment identity.  The partition fingerprint captures the sealed
        # contents and lets the same research run reproduce on another host.
        resolved_environment["holdout_partition"] = holdout_partition.identity_dict()
    return (
        ExperimentSpec(
            hypothesis_id=hypothesis_id,
            template_id=template_id,
            thesis=thesis,
            code_commit=code_commit,
            image_ref=resolved_image_ref,
            data_snapshot_id=data_snapshot_id,
            feature_versions=feature_versions,
            parameters=dict(parameters),
            seed=seed,
            cost_model=dict(cost_model),
            environment=resolved_environment,
            holdout_id=normalized_holdout_id,
        ),
        provenance,
    )


def _required(value: Any, name: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise ManifestedExperimentError(f"{name} is required")
    return result
