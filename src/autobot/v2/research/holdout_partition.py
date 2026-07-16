"""Physical, point-in-time holdout partitions for AUTOBOT research.

The experiment registry can remember that a holdout exists, but that alone
does not stop a runner from reading it while searching parameters.  This
module materializes separate optimization and final-review CSV roots from one
canonical snapshot, fingerprints every resulting file, and verifies the root
and contents again before a manifested experiment is allowed to use it.

It is deliberately research-only: it imports no strategy, order, router,
paper, or live component.
"""

from __future__ import annotations

import csv
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping, Sequence


PARTITION_SCHEMA_VERSION = 1
OPTIMIZATION_ROLE = "optimization"
HOLDOUT_REVIEW_ROLE = "holdout_review"
PARTITION_ROLES = frozenset({OPTIMIZATION_ROLE, HOLDOUT_REVIEW_ROLE})


class HoldoutPartitionError(ValueError):
    """Raised when a holdout partition is incomplete, altered, or misused."""


@dataclass(frozen=True)
class HoldoutPartitionConfig:
    run_id: str
    source_snapshot_manifest: Path
    holdout_start_at: datetime
    output_dir: Path = Path("data/research/partitions")
    holdout_end_at: datetime | None = None
    partition_id: str | None = None

    def __post_init__(self) -> None:
        if not str(self.run_id or "").strip():
            raise HoldoutPartitionError("run_id is required")
        for value, name in ((self.holdout_start_at, "holdout_start_at"), (self.holdout_end_at, "holdout_end_at")):
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise HoldoutPartitionError(f"{name} must be timezone-aware")
        if self.holdout_end_at is not None and self.holdout_end_at <= self.holdout_start_at:
            raise HoldoutPartitionError("holdout_end_at must be after holdout_start_at")


@dataclass(frozen=True)
class HoldoutPartitionReference:
    partition_id: str
    fingerprint: str
    source_snapshot_id: str
    source_snapshot_fingerprint: str
    holdout_start_at: str
    holdout_end_at: str | None
    optimization_data_dir: str
    holdout_data_dir: str
    optimization_fingerprint: str
    holdout_fingerprint: str
    optimization_snapshot_id: str
    optimization_snapshot_fingerprint: str
    optimization_snapshot_manifest: str
    holdout_snapshot_id: str
    holdout_snapshot_fingerprint: str
    holdout_snapshot_manifest: str
    optimization_row_count: int
    holdout_row_count: int
    unknown_ingestion_time_count: int
    manifest_path: str

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "schema_version": PARTITION_SCHEMA_VERSION,
            "research_only": True,
            "paper_capital_allowed": False,
            "live_allowed": False,
            "promotable": False,
        }

    def identity_dict(self) -> dict[str, Any]:
        """Return the portable, material identity without host-local paths."""

        payload = self.to_dict()
        for key in (
            "manifest_path",
            "optimization_data_dir",
            "holdout_data_dir",
            "optimization_snapshot_manifest",
            "holdout_snapshot_manifest",
        ):
            payload.pop(key, None)
        return payload


def materialize_holdout_partition(config: HoldoutPartitionConfig) -> HoldoutPartitionReference:
    """Create deterministic, disjoint optimization and final-review datasets.

    Only rows whose ``event_time``, ``available_time`` and ``ingestion_time``
    are all present and point-in-time valid are copied.  Unknown ingestion is
    counted and quarantined rather than silently treated as historical proof.
    """

    source_manifest = _load_source_snapshot_manifest(config.source_snapshot_manifest)
    source_snapshot_id = _required(source_manifest.get("snapshot_id"), "source snapshot_id")
    source_snapshot_fingerprint = _required(source_manifest.get("fingerprint"), "source snapshot fingerprint")
    source_files = _source_csv_paths(source_manifest, config.source_snapshot_manifest)
    partition_id = str(config.partition_id or _partition_id(source_snapshot_id, config)).strip()
    if not partition_id:
        raise HoldoutPartitionError("partition_id is required")

    root = Path(config.output_dir) / partition_id
    manifest_path = root / "partition_manifest.json"
    if manifest_path.exists():
        reference = load_holdout_partition_reference(manifest_path)
        expected = {
            "source_snapshot_id": source_snapshot_id,
            "source_snapshot_fingerprint": source_snapshot_fingerprint,
            "holdout_start_at": _time_text(config.holdout_start_at),
            "holdout_end_at": _time_text(config.holdout_end_at) if config.holdout_end_at else None,
        }
        actual = reference.to_dict()
        if any(actual[key] != value for key, value in expected.items()):
            raise HoldoutPartitionError("existing holdout partition does not match the requested immutable boundary")
        verify_holdout_partition(manifest_path, role=OPTIMIZATION_ROLE, data_paths=(Path(reference.optimization_data_dir),))
        verify_holdout_partition(manifest_path, role=HOLDOUT_REVIEW_ROLE, data_paths=(Path(reference.holdout_data_dir),))
        return reference
    if root.exists():
        raise HoldoutPartitionError("holdout partition directory exists without a manifest")

    optimization_dir = root / OPTIMIZATION_ROLE
    holdout_dir = root / HOLDOUT_REVIEW_ROLE
    optimization_rows = 0
    holdout_rows = 0
    unknown_ingestion = 0
    invalid_temporal = 0
    outside_requested_window = 0
    optimization_files: list[dict[str, Any]] = []
    holdout_files: list[dict[str, Any]] = []

    for index, source_path in enumerate(source_files, start=1):
        with source_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = tuple(reader.fieldnames or ())
            if not fieldnames:
                raise HoldoutPartitionError(f"source CSV has no header: {source_path}")
            optimization_payload: list[dict[str, str]] = []
            holdout_payload: list[dict[str, str]] = []
            for row in reader:
                event_time = _parse_time(row.get("event_time") or row.get("timestamp"))
                available_time = _parse_time(row.get("available_time"))
                ingestion_time = _parse_time(row.get("ingestion_time"))
                if ingestion_time is None:
                    unknown_ingestion += 1
                    continue
                if event_time is None or available_time is None or available_time < event_time or ingestion_time < available_time:
                    invalid_temporal += 1
                    continue
                if available_time < config.holdout_start_at:
                    optimization_payload.append(dict(row))
                elif config.holdout_end_at is None or available_time < config.holdout_end_at:
                    holdout_payload.append(dict(row))
                else:
                    outside_requested_window += 1
            stem = f"{index:03d}_{source_path.name}"
            if optimization_payload:
                destination = optimization_dir / stem
                _write_csv(destination, fieldnames, optimization_payload)
                optimization_files.append(_file_entry(destination, len(optimization_payload), root))
                optimization_rows += len(optimization_payload)
            if holdout_payload:
                destination = holdout_dir / stem
                _write_csv(destination, fieldnames, holdout_payload)
                holdout_files.append(_file_entry(destination, len(holdout_payload), root))
                holdout_rows += len(holdout_payload)

    if not optimization_rows:
        raise HoldoutPartitionError("holdout partition contains no point-in-time optimization rows")
    if not holdout_rows:
        raise HoldoutPartitionError("holdout partition contains no point-in-time holdout rows")

    optimization_fingerprint = _entries_fingerprint(optimization_files)
    holdout_fingerprint = _entries_fingerprint(holdout_files)
    optimization_snapshot_id = f"{partition_id}_{OPTIMIZATION_ROLE}"
    holdout_snapshot_id = f"{partition_id}_{HOLDOUT_REVIEW_ROLE}"
    identity = {
        "schema_version": PARTITION_SCHEMA_VERSION,
        "source_snapshot_id": source_snapshot_id,
        "source_snapshot_fingerprint": source_snapshot_fingerprint,
        "holdout_start_at": _time_text(config.holdout_start_at),
        "holdout_end_at": _time_text(config.holdout_end_at) if config.holdout_end_at else None,
        "optimization_fingerprint": optimization_fingerprint,
        "holdout_fingerprint": holdout_fingerprint,
        "optimization_snapshot_id": optimization_snapshot_id,
        "holdout_snapshot_id": holdout_snapshot_id,
    }
    fingerprint = _fingerprint(identity)
    optimization_snapshot_manifest = root / f"{OPTIMIZATION_ROLE}_canonical_snapshot.json"
    holdout_snapshot_manifest = root / f"{HOLDOUT_REVIEW_ROLE}_canonical_snapshot.json"
    _write_role_snapshot_manifest(
        path=optimization_snapshot_manifest,
        role=OPTIMIZATION_ROLE,
        snapshot_id=optimization_snapshot_id,
        snapshot_fingerprint=optimization_fingerprint,
        files=optimization_files,
        root=root,
        partition_id=partition_id,
        partition_fingerprint=fingerprint,
        source_snapshot_id=source_snapshot_id,
        source_snapshot_fingerprint=source_snapshot_fingerprint,
    )
    _write_role_snapshot_manifest(
        path=holdout_snapshot_manifest,
        role=HOLDOUT_REVIEW_ROLE,
        snapshot_id=holdout_snapshot_id,
        snapshot_fingerprint=holdout_fingerprint,
        files=holdout_files,
        root=root,
        partition_id=partition_id,
        partition_fingerprint=fingerprint,
        source_snapshot_id=source_snapshot_id,
        source_snapshot_fingerprint=source_snapshot_fingerprint,
    )
    payload = {
        **identity,
        "run_id": config.run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "partition_id": partition_id,
        "fingerprint": fingerprint,
        "optimization_data_dir": str(optimization_dir),
        "holdout_data_dir": str(holdout_dir),
        "optimization_row_count": optimization_rows,
        "holdout_row_count": holdout_rows,
        "optimization_snapshot_id": optimization_snapshot_id,
        "optimization_snapshot_fingerprint": optimization_fingerprint,
        "optimization_snapshot_manifest": str(optimization_snapshot_manifest),
        "holdout_snapshot_id": holdout_snapshot_id,
        "holdout_snapshot_fingerprint": holdout_fingerprint,
        "holdout_snapshot_manifest": str(holdout_snapshot_manifest),
        "unknown_ingestion_time_count": unknown_ingestion,
        "invalid_temporal_row_count": invalid_temporal,
        "outside_requested_window_row_count": outside_requested_window,
        "optimization_files": optimization_files,
        "holdout_files": holdout_files,
        "research_only": True,
        "paper_capital_allowed": False,
        "live_allowed": False,
        "promotable": False,
        "safety_notes": [
            "Rows with unknown ingestion time are excluded from both partitions.",
            "Optimization and holdout data use separate roots and are verified before use.",
            "The holdout is final-review evidence only and cannot be used for parameter optimization.",
        ],
    }
    root.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    _seal_read_only(
        [
            manifest_path,
            optimization_snapshot_manifest,
            holdout_snapshot_manifest,
            *(root / entry["path"] for entry in optimization_files),
            *(root / entry["path"] for entry in holdout_files),
        ]
    )
    return load_holdout_partition_reference(manifest_path)


def load_holdout_partition_reference(path: str | Path) -> HoldoutPartitionReference:
    manifest_path = Path(path)
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HoldoutPartitionError(f"invalid holdout partition manifest: {manifest_path}") from exc
    if not isinstance(payload, Mapping) or int(payload.get("schema_version") or 0) != PARTITION_SCHEMA_VERSION:
        raise HoldoutPartitionError("unsupported holdout partition manifest")
    if any(bool(payload.get(key)) for key in ("paper_capital_allowed", "live_allowed", "promotable")):
        raise HoldoutPartitionError("holdout partition must remain research-only")
    reference = HoldoutPartitionReference(
        partition_id=_required(payload.get("partition_id"), "partition_id"),
        fingerprint=_required(payload.get("fingerprint"), "fingerprint"),
        source_snapshot_id=_required(payload.get("source_snapshot_id"), "source_snapshot_id"),
        source_snapshot_fingerprint=_required(payload.get("source_snapshot_fingerprint"), "source_snapshot_fingerprint"),
        holdout_start_at=_required(payload.get("holdout_start_at"), "holdout_start_at"),
        holdout_end_at=str(payload["holdout_end_at"]) if payload.get("holdout_end_at") else None,
        optimization_data_dir=_required(payload.get("optimization_data_dir"), "optimization_data_dir"),
        holdout_data_dir=_required(payload.get("holdout_data_dir"), "holdout_data_dir"),
        optimization_fingerprint=_required(payload.get("optimization_fingerprint"), "optimization_fingerprint"),
        holdout_fingerprint=_required(payload.get("holdout_fingerprint"), "holdout_fingerprint"),
        optimization_snapshot_id=_required(payload.get("optimization_snapshot_id"), "optimization_snapshot_id"),
        optimization_snapshot_fingerprint=_required(
            payload.get("optimization_snapshot_fingerprint"), "optimization_snapshot_fingerprint"
        ),
        optimization_snapshot_manifest=_required(
            payload.get("optimization_snapshot_manifest"), "optimization_snapshot_manifest"
        ),
        holdout_snapshot_id=_required(payload.get("holdout_snapshot_id"), "holdout_snapshot_id"),
        holdout_snapshot_fingerprint=_required(
            payload.get("holdout_snapshot_fingerprint"), "holdout_snapshot_fingerprint"
        ),
        holdout_snapshot_manifest=_required(payload.get("holdout_snapshot_manifest"), "holdout_snapshot_manifest"),
        optimization_row_count=int(payload.get("optimization_row_count") or 0),
        holdout_row_count=int(payload.get("holdout_row_count") or 0),
        unknown_ingestion_time_count=max(0, int(payload.get("unknown_ingestion_time_count") or 0)),
        manifest_path=str(manifest_path),
    )
    expected = _fingerprint(
        {
            "schema_version": PARTITION_SCHEMA_VERSION,
            "source_snapshot_id": reference.source_snapshot_id,
            "source_snapshot_fingerprint": reference.source_snapshot_fingerprint,
            "holdout_start_at": reference.holdout_start_at,
            "holdout_end_at": reference.holdout_end_at,
            "optimization_fingerprint": reference.optimization_fingerprint,
            "holdout_fingerprint": reference.holdout_fingerprint,
            "optimization_snapshot_id": reference.optimization_snapshot_id,
            "holdout_snapshot_id": reference.holdout_snapshot_id,
        }
    )
    if reference.fingerprint != expected:
        raise HoldoutPartitionError("holdout partition manifest fingerprint does not match its immutable identity")
    if reference.optimization_row_count <= 0 or reference.holdout_row_count <= 0:
        raise HoldoutPartitionError("holdout partition requires non-empty optimization and holdout datasets")
    return reference


def verify_holdout_partition(
    manifest_path: str | Path,
    *,
    role: str,
    data_paths: Sequence[Path],
) -> HoldoutPartitionReference:
    """Verify a sealed partition before a runner may read one of its roots."""

    if role not in PARTITION_ROLES:
        raise HoldoutPartitionError(f"unsupported partition role: {role}")
    reference = load_holdout_partition_reference(manifest_path)
    expected_dir = Path(
        reference.optimization_data_dir if role == OPTIMIZATION_ROLE else reference.holdout_data_dir
    ).resolve()
    actual_dirs = tuple(sorted({Path(path).resolve() for path in data_paths}, key=str))
    if actual_dirs != (expected_dir,):
        raise HoldoutPartitionError(f"{role} runner must use exactly its sealed data root")
    expected_fingerprint = (
        reference.optimization_fingerprint if role == OPTIMIZATION_ROLE else reference.holdout_fingerprint
    )
    actual_entries = _entries_for_directory(expected_dir, Path(reference.manifest_path).parent)
    if _entries_fingerprint(actual_entries) != expected_fingerprint:
        raise HoldoutPartitionError(f"{role} partition contents do not match the manifest fingerprint")
    _verify_role_snapshot_manifest(reference, role=role, entries=actual_entries)
    return reference


def _load_source_snapshot_manifest(path: Path) -> Mapping[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HoldoutPartitionError(f"invalid canonical snapshot manifest: {path}") from exc
    if not isinstance(payload, Mapping):
        raise HoldoutPartitionError("canonical snapshot manifest must be an object")
    if str(payload.get("market_type") or "").lower() != "spot":
        raise HoldoutPartitionError("holdout partitions accept only canonical spot snapshots")
    return payload


def _source_csv_paths(payload: Mapping[str, Any], manifest_path: Path) -> tuple[Path, ...]:
    files = payload.get("files")
    if not isinstance(files, Sequence) or isinstance(files, (str, bytes)):
        raise HoldoutPartitionError("canonical snapshot manifest files are required")
    paths: list[Path] = []
    for entry in files:
        if not isinstance(entry, Mapping):
            continue
        raw_path = str(entry.get("csv_path") or "").strip()
        if not raw_path:
            continue
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = (manifest_path.parent / candidate).resolve()
            if not candidate.exists():
                candidate = (Path.cwd() / raw_path).resolve()
        if not candidate.is_file():
            raise HoldoutPartitionError(f"canonical source file is missing: {raw_path}")
        paths.append(candidate)
    if not paths:
        raise HoldoutPartitionError("canonical snapshot manifest contains no readable CSV files")
    return tuple(sorted(set(paths), key=str))


def _write_csv(path: Path, fieldnames: Sequence[str], rows: Sequence[Mapping[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def _file_entry(path: Path, row_count: int, root: Path) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(root)),
        "row_count": row_count,
        "sha256": _file_fingerprint(path),
    }


def _entries_for_directory(directory: Path, root: Path) -> list[dict[str, Any]]:
    if not directory.is_dir():
        raise HoldoutPartitionError(f"sealed partition directory is missing: {directory}")
    if directory.is_symlink():
        raise HoldoutPartitionError(f"sealed partition directory cannot be a symlink: {directory}")
    entries: list[dict[str, Any]] = []
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise HoldoutPartitionError(f"sealed partition cannot contain symlinks: {path}")
        if not path.is_file():
            continue
        if path.suffix.lower() != ".csv":
            raise HoldoutPartitionError(f"sealed partition contains an unexpected non-CSV file: {path}")
        with path.open("r", encoding="utf-8", newline="") as handle:
            row_count = sum(1 for _ in csv.DictReader(handle))
        entries.append(_file_entry(path, row_count, root))
    return entries


def _write_role_snapshot_manifest(
    *,
    path: Path,
    role: str,
    snapshot_id: str,
    snapshot_fingerprint: str,
    files: Sequence[Mapping[str, Any]],
    root: Path,
    partition_id: str,
    partition_fingerprint: str,
    source_snapshot_id: str,
    source_snapshot_fingerprint: str,
) -> None:
    """Write one canonical-source manifest scoped to exactly one partition role."""

    payload = {
        "schema_version": 2,
        "snapshot_id": snapshot_id,
        "fingerprint": snapshot_fingerprint,
        "market_type": "spot",
        "files": [
            {
                "csv_path": str((root / str(item["path"])).resolve()),
                "row_count": int(item["row_count"]),
                "sha256": str(item["sha256"]),
            }
            for item in files
        ],
        "holdout_partition": {
            "partition_id": partition_id,
            "partition_fingerprint": partition_fingerprint,
            "role": role,
            "source_snapshot_id": source_snapshot_id,
            "source_snapshot_fingerprint": source_snapshot_fingerprint,
        },
        "research_only": True,
        "paper_capital_allowed": False,
        "live_allowed": False,
        "promotable": False,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _verify_role_snapshot_manifest(
    reference: HoldoutPartitionReference,
    *,
    role: str,
    entries: Sequence[Mapping[str, Any]],
) -> None:
    """Verify the role-scoped source manifest against the sealed CSV entries."""

    root = Path(reference.manifest_path).parent.resolve()
    expected_path = root / f"{role}_canonical_snapshot.json"
    reported_path = Path(
        reference.optimization_snapshot_manifest if role == OPTIMIZATION_ROLE else reference.holdout_snapshot_manifest
    ).resolve()
    if reported_path != expected_path:
        raise HoldoutPartitionError(f"{role} snapshot manifest path is not the sealed partition manifest")
    try:
        payload = json.loads(expected_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HoldoutPartitionError(f"invalid sealed {role} snapshot manifest") from exc
    snapshot_id = reference.optimization_snapshot_id if role == OPTIMIZATION_ROLE else reference.holdout_snapshot_id
    snapshot_fingerprint = (
        reference.optimization_snapshot_fingerprint
        if role == OPTIMIZATION_ROLE
        else reference.holdout_snapshot_fingerprint
    )
    expected_payload = {
        "schema_version": 2,
        "snapshot_id": snapshot_id,
        "fingerprint": snapshot_fingerprint,
        "market_type": "spot",
        "files": [
            {
                "csv_path": str((root / str(item["path"])).resolve()),
                "row_count": int(item["row_count"]),
                "sha256": str(item["sha256"]),
            }
            for item in entries
        ],
        "holdout_partition": {
            "partition_id": reference.partition_id,
            "partition_fingerprint": reference.fingerprint,
            "role": role,
            "source_snapshot_id": reference.source_snapshot_id,
            "source_snapshot_fingerprint": reference.source_snapshot_fingerprint,
        },
        "research_only": True,
        "paper_capital_allowed": False,
        "live_allowed": False,
        "promotable": False,
    }
    if payload != expected_payload:
        raise HoldoutPartitionError(f"sealed {role} snapshot manifest does not match the partition data")


def _entries_fingerprint(entries: Sequence[Mapping[str, Any]]) -> str:
    return _fingerprint(sorted((dict(entry) for entry in entries), key=lambda item: str(item.get("path"))))


def _file_fingerprint(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _seal_read_only(paths: Sequence[Path]) -> None:
    for path in paths:
        try:
            os.chmod(path, 0o444)
        except OSError:
            # Fingerprint verification remains the authoritative protection on
            # platforms that cannot preserve Unix-style read-only modes.
            pass


def _partition_id(source_snapshot_id: str, config: HoldoutPartitionConfig) -> str:
    boundary = _fingerprint(
        {
            "source_snapshot_id": source_snapshot_id,
            "holdout_start_at": _time_text(config.holdout_start_at),
            "holdout_end_at": _time_text(config.holdout_end_at) if config.holdout_end_at else None,
        }
    )[:16]
    return f"holdout_{boundary}"


def _parse_time(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _time_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _required(value: Any, name: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise HoldoutPartitionError(f"{name} is required")
    return result


def _fingerprint(value: Any) -> str:
    return sha256(json.dumps(value, default=str, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
