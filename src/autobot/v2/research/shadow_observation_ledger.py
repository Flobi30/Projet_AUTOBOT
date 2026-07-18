"""Append-only, research-only evidence for AUTOBOT shadow observations.

The ledger records a fully attributable shadow decision only after the
strategy artifact and its concrete feature vectors agree exactly.  It is not a
paper ledger, does not import an execution path and cannot create an order.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable, Sequence

from autobot.v2.contracts import VerifiedFeatureVector, contract_fingerprint, contract_to_dict

from .shadow_governance import ShadowGovernanceError, ShadowObservation, StrategyArtifact


DEFAULT_SHADOW_OBSERVATION_LEDGER_PATH = Path("data/research/shadow_observations.sqlite3")
_WRITABLE_ARTIFACT_STATUSES = frozenset({"SHADOW_ELIGIBLE", "SHADOW"})


class ShadowObservationLedgerError(ValueError):
    """Raised when an observation cannot prove its research/shadow inputs."""


@dataclass(frozen=True)
class RecordedShadowObservation:
    observation_id: str
    artifact_id: str
    artifact_fingerprint: str
    feature_vector_fingerprint: str
    recorded_at: datetime
    duplicate: bool = False
    research_only: bool = True
    paper_capital_allowed: bool = False
    live_allowed: bool = False


def verified_feature_vectors_fingerprint(vectors: Iterable[VerifiedFeatureVector]) -> str:
    """Return a stable identity for the exact complete feature inputs."""

    materialized = tuple(vectors)
    if not materialized or any(not isinstance(item, VerifiedFeatureVector) for item in materialized):
        raise ShadowObservationLedgerError("verified feature vectors are required")
    snapshot_ids = [item.feature_snapshot.feature_snapshot_id for item in materialized]
    if len(snapshot_ids) != len(set(snapshot_ids)):
        raise ShadowObservationLedgerError("verified feature vector snapshot ids must be unique")
    payload = [
        {
            "feature_snapshot_id": item.feature_snapshot.feature_snapshot_id,
            "fingerprint": item.fingerprint,
        }
        for item in sorted(materialized, key=lambda item: item.feature_snapshot.feature_snapshot_id)
    ]
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


class ShadowObservationLedger:
    """Persist exact shadow observations without any paper/live authority."""

    def __init__(self, path: str | Path = DEFAULT_SHADOW_OBSERVATION_LEDGER_PATH) -> None:
        self.path = Path(path)

    def record(
        self,
        *,
        artifact: StrategyArtifact,
        observation: ShadowObservation,
        feature_vectors: Sequence[VerifiedFeatureVector],
        recorded_at: datetime | None = None,
    ) -> RecordedShadowObservation:
        vectors = tuple(feature_vectors)
        if not vectors or any(not isinstance(item, VerifiedFeatureVector) for item in vectors):
            raise ShadowObservationLedgerError("verified feature vectors are required")
        vector_fingerprint = self._validate(artifact=artifact, observation=observation, vectors=vectors)
        timestamp = _utc(recorded_at or datetime.now(timezone.utc), "recorded_at")
        payload = {
            "artifact_id": artifact.artifact_id,
            "artifact_fingerprint": artifact.fingerprint,
            "observation": contract_to_dict(observation),
            "feature_vectors": [contract_to_dict(item) for item in vectors],
            "feature_vector_fingerprint": vector_fingerprint,
            "research_only": True,
            "paper_capital_allowed": False,
            "live_allowed": False,
        }
        observation_id = f"shadow_observation_{_fingerprint(payload)[:24]}"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            self._initialize(connection)
            inserted = connection.execute(
                """
                INSERT OR IGNORE INTO shadow_observations
                    (observation_id, artifact_id, artifact_fingerprint, observed_at,
                     data_available_at, source_snapshot_id, feature_fingerprint,
                     feature_vector_fingerprint, target_portfolio_fingerprint,
                     observation_json, feature_vectors_json, recorded_at,
                     research_only, paper_capital_allowed, live_allowed)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0, 0)
                """,
                (
                    observation_id,
                    artifact.artifact_id,
                    artifact.fingerprint,
                    observation.observed_at.isoformat(),
                    observation.data_available_at.isoformat(),
                    observation.source_snapshot_id,
                    observation.feature_fingerprint,
                    vector_fingerprint,
                    contract_fingerprint(observation.target_portfolio),
                    _canonical_json(contract_to_dict(observation)),
                    _canonical_json([contract_to_dict(item) for item in vectors]),
                    timestamp.isoformat(),
                ),
            )
            return RecordedShadowObservation(
                observation_id=observation_id,
                artifact_id=artifact.artifact_id,
                artifact_fingerprint=artifact.fingerprint,
                feature_vector_fingerprint=vector_fingerprint,
                recorded_at=timestamp,
                duplicate=inserted.rowcount == 0,
            )

    def count(self) -> int:
        if not self.path.exists():
            return 0
        with self._connect() as connection:
            self._initialize(connection)
            return int(connection.execute("SELECT COUNT(*) FROM shadow_observations").fetchone()[0])

    @staticmethod
    def _validate(
        *,
        artifact: StrategyArtifact,
        observation: ShadowObservation,
        vectors: tuple[VerifiedFeatureVector, ...],
    ) -> str:
        if not isinstance(artifact, StrategyArtifact):
            raise ShadowObservationLedgerError("strategy artifact is required")
        if not isinstance(observation, ShadowObservation):
            raise ShadowObservationLedgerError("shadow observation is required")
        if artifact.status not in _WRITABLE_ARTIFACT_STATUSES:
            raise ShadowObservationLedgerError("strategy artifact is not writable for shadow observation")
        if observation.artifact_id != artifact.artifact_id:
            raise ShadowObservationLedgerError("shadow observation artifact id does not match")
        if observation.source_snapshot_id != artifact.data_snapshot_id:
            raise ShadowObservationLedgerError("shadow observation source snapshot does not match")
        expected = {snapshot.feature_snapshot_id: snapshot for snapshot in artifact.feature_snapshots}
        supplied = {vector.feature_snapshot.feature_snapshot_id: vector for vector in vectors}
        if not expected or set(supplied) != set(expected):
            raise ShadowObservationLedgerError("shadow observation feature snapshot set does not match artifact")
        for snapshot_id, vector in supplied.items():
            if vector.feature_snapshot != expected[snapshot_id]:
                raise ShadowObservationLedgerError("shadow observation feature snapshot evidence does not match artifact")
            if vector.observed_at != observation.data_available_at:
                raise ShadowObservationLedgerError("shadow observation vector observed_at must equal data_available_at")
        vector_fingerprint = verified_feature_vectors_fingerprint(vectors)
        if observation.feature_fingerprint != vector_fingerprint:
            raise ShadowObservationLedgerError("shadow observation feature fingerprint does not match vectors")
        return vector_fingerprint

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30.0)
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    @staticmethod
    def _initialize(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS shadow_observations (
                observation_id TEXT PRIMARY KEY,
                artifact_id TEXT NOT NULL,
                artifact_fingerprint TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                data_available_at TEXT NOT NULL,
                source_snapshot_id TEXT NOT NULL,
                feature_fingerprint TEXT NOT NULL,
                feature_vector_fingerprint TEXT NOT NULL,
                target_portfolio_fingerprint TEXT NOT NULL,
                observation_json TEXT NOT NULL,
                feature_vectors_json TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                research_only INTEGER NOT NULL CHECK (research_only = 1),
                paper_capital_allowed INTEGER NOT NULL CHECK (paper_capital_allowed = 0),
                live_allowed INTEGER NOT NULL CHECK (live_allowed = 0)
            )
            """
        )
        for operation in ("UPDATE", "DELETE"):
            connection.execute(
                f"""
                CREATE TRIGGER IF NOT EXISTS shadow_observations_append_only_{operation.lower()}
                BEFORE {operation} ON shadow_observations
                BEGIN
                    SELECT RAISE(ABORT, 'shadow_observations is append-only');
                END
                """
            )


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _fingerprint(value: Any) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ShadowObservationLedgerError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)
