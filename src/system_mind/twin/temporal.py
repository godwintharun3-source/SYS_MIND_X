"""Temporal observations, cryptographic provenance metadata, and freshness lifecycle."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from typing import Any, Dict, List, Optional, Tuple

from system_mind.core.types import OperationRiskTier


class ObservationType(str, Enum):
    """Categorization of temporal observations."""

    STATE_SNAPSHOT = "STATE_SNAPSHOT"
    ATTRIBUTE_DELTA = "ATTRIBUTE_DELTA"
    LIFECYCLE_EVENT = "LIFECYCLE_EVENT"
    HEARTBEAT = "HEARTBEAT"
    SECURITY_ATTESTATION = "SECURITY_ATTESTATION"


class ProvenanceStatus(str, Enum):
    """Verification tiers for observation provenance."""

    VERIFIED_KERNEL = "VERIFIED_KERNEL"
    VERIFIED_BROKER = "VERIFIED_BROKER"
    UNVERIFIED_USER_SPACE = "UNVERIFIED_USER_SPACE"
    SYNTHETIC_TEST = "SYNTHETIC_TEST"


class FreshnessState(str, Enum):
    """Lifecycle freshness state of an observed entity."""

    FRESH = "FRESH"
    AGING = "AGING"
    STALE = "STALE"
    EXPIRED = "EXPIRED"
    TOMBSTONED = "TOMBSTONED"


def compute_payload_hash(payload: Dict[str, Any]) -> str:
    """Compute the deterministic SHA-256 digest of a state dictionary."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def parse_iso_timestamp(ts_str: str) -> datetime:
    """Parse an ISO 8601 timestamp string into a timezone-aware UTC datetime."""
    # Replace trailing 'Z' if present
    cleaned = ts_str.rstrip("Z")
    try:
        dt = datetime.fromisoformat(cleaned)
    except ValueError:
        # Fallback to basic format
        dt = datetime.strptime(cleaned, "%Y-%m-%dT%H:%M:%S")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


@dataclass(frozen=True)
class ProvenanceMetadata:
    """Cryptographic provenance and collector origin metadata."""

    source_engine: str
    collector_method: str
    payload_sha256: str
    verification_status: ProvenanceStatus
    parent_observation_id: Optional[str] = None


@dataclass(frozen=True)
class FreshnessMetadata:
    """Freshness bounds, decay score, and invalidation criteria."""

    ttl_seconds: float = 60.0
    max_acceptable_staleness_seconds: float = 300.0
    last_verified_at: str = ""
    freshness_state: FreshnessState = FreshnessState.FRESH
    staleness_score: float = 0.0  # 0.0 (fresh) to 1.0 (expired)
    invalidation_triggers: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class TemporalObservation:
    """Point-in-time discrete observation of an entity state with provenance and freshness."""

    observation_id: str
    entity_id: str
    observed_at: str
    observation_seq: int
    observation_type: ObservationType
    observed_state: Dict[str, Any]
    provenance: ProvenanceMetadata
    freshness: FreshnessMetadata
    confidence: float = 1.0


@dataclass(frozen=True)
class StateDelta:
    """Difference between two temporal observation points for an entity."""

    entity_id: str
    from_seq: int
    to_seq: int
    from_timestamp: str
    to_timestamp: str
    added_or_modified: Dict[str, Any]
    removed_keys: List[str]


class FreshnessEvaluator:
    """Evaluates observation decay and staleness states against temporal thresholds."""

    @classmethod
    def evaluate(
        cls,
        observation: TemporalObservation,
        current_timestamp: str,
    ) -> FreshnessMetadata:
        """Evaluate current freshness state and decay score for an observation."""
        obs_dt = parse_iso_timestamp(observation.observed_at)
        curr_dt = parse_iso_timestamp(current_timestamp)

        elapsed = max(0.0, (curr_dt - obs_dt).total_seconds())
        ttl = max(0.001, observation.freshness.ttl_seconds)
        max_stale = max(ttl, observation.freshness.max_acceptable_staleness_seconds)

        if elapsed <= (ttl / 2.0):
            state = FreshnessState.FRESH
            score = (elapsed / ttl) * 0.5
        elif elapsed <= ttl:
            state = FreshnessState.AGING
            half_window = ttl / 2.0
            score = 0.5 + 0.3 * ((elapsed - (ttl / 2.0)) / half_window)
        elif elapsed <= max_stale:
            state = FreshnessState.STALE
            stale_window = max(0.001, max_stale - ttl)
            score = 0.8 + 0.2 * ((elapsed - ttl) / stale_window)
        else:
            state = FreshnessState.EXPIRED
            score = 1.0

        return FreshnessMetadata(
            ttl_seconds=observation.freshness.ttl_seconds,
            max_acceptable_staleness_seconds=observation.freshness.max_acceptable_staleness_seconds,
            last_verified_at=current_timestamp,
            freshness_state=state,
            staleness_score=round(min(1.0, score), 4),
            invalidation_triggers=observation.freshness.invalidation_triggers,
        )


class TemporalTimelineStore:
    """Append-only timeline store indexing historical observations and computing state diffs."""

    def __init__(self) -> None:
        self._timelines: Dict[str, List[TemporalObservation]] = {}

    def record_observation(self, observation: TemporalObservation) -> None:
        """Append an observation to the entity's timeline, enforcing invariants."""
        entity_id = observation.entity_id

        if not entity_id or not entity_id.strip():
            raise ValueError("Observation entity_id cannot be empty.")

        # Invariant 2: Verify payload hash matches canonical json
        expected_hash = compute_payload_hash(observation.observed_state)
        if observation.provenance.payload_sha256 != expected_hash:
            raise ValueError(
                f"Payload hash mismatch: provided '{observation.provenance.payload_sha256}' does not match expected '{expected_hash}'."
            )

        if entity_id not in self._timelines:
            self._timelines[entity_id] = []
        else:
            latest = self._timelines[entity_id][-1]

            # Invariant 1: Monotonic sequence enforcement
            if observation.observation_seq <= latest.observation_seq:
                raise ValueError(
                    f"Monotonic Sequence Violation: New seq {observation.observation_seq} is not greater than latest seq {latest.observation_seq}."
                )

            # Monotonic timestamp check
            latest_dt = parse_iso_timestamp(latest.observed_at)
            new_dt = parse_iso_timestamp(observation.observed_at)
            if new_dt < latest_dt:
                raise ValueError(
                    f"Timestamp Inversion: Observation time '{observation.observed_at}' is earlier than latest '{latest.observed_at}'."
                )

        self._timelines[entity_id].append(observation)

    def get_latest_observation(self, entity_id: str) -> Optional[TemporalObservation]:
        """Retrieve the latest observation for an entity."""
        history = self._timelines.get(entity_id, [])
        return history[-1] if history else None

    def get_timeline(self, entity_id: str) -> List[TemporalObservation]:
        """Retrieve all chronological observations for an entity."""
        return list(self._timelines.get(entity_id, []))

    def reconstruct_state_at(self, entity_id: str, target_timestamp: str) -> Dict[str, Any]:
        """Reconstruct state of an entity at a target historical timestamp."""
        history = self._timelines.get(entity_id, [])
        if not history:
            return {}

        target_dt = parse_iso_timestamp(target_timestamp)
        # Find observations <= target_timestamp
        relevant = [obs for obs in history if parse_iso_timestamp(obs.observed_at) <= target_dt]
        if not relevant:
            return {}

        # Replay from the most recent snapshot in relevant window
        reconstructed: Dict[str, Any] = {}
        for obs in relevant:
            if obs.observation_type == ObservationType.STATE_SNAPSHOT:
                reconstructed = dict(obs.observed_state)
            elif obs.observation_type == ObservationType.ATTRIBUTE_DELTA:
                reconstructed.update(obs.observed_state)
            elif obs.observation_type == ObservationType.LIFECYCLE_EVENT:
                reconstructed.update(obs.observed_state)

        return reconstructed

    def compute_state_diff(self, entity_id: str, from_seq: int, to_seq: int) -> StateDelta:
        """Compute the state difference between two sequential observation points."""
        history = self._timelines.get(entity_id, [])
        obs_map = {obs.observation_seq: obs for obs in history}

        if from_seq not in obs_map or to_seq not in obs_map:
            raise KeyError(f"Sequence points {from_seq} or {to_seq} not found for entity '{entity_id}'.")

        if from_seq > to_seq:
            raise ValueError(f"from_seq ({from_seq}) must be <= to_seq ({to_seq}).")

        state_from = self.reconstruct_state_at(entity_id, obs_map[from_seq].observed_at)
        state_to = self.reconstruct_state_at(entity_id, obs_map[to_seq].observed_at)

        added_or_modified: Dict[str, Any] = {}
        removed_keys: List[str] = []

        for k, v in state_to.items():
            if k not in state_from or state_from[k] != v:
                added_or_modified[k] = v

        for k in state_from:
            if k not in state_to:
                removed_keys.append(k)

        return StateDelta(
            entity_id=entity_id,
            from_seq=from_seq,
            to_seq=to_seq,
            from_timestamp=obs_map[from_seq].observed_at,
            to_timestamp=obs_map[to_seq].observed_at,
            added_or_modified=added_or_modified,
            removed_keys=removed_keys,
        )

    def validate_dispatch_freshness(
        self,
        entity_id: str,
        current_timestamp: str,
        risk_tier: OperationRiskTier,
    ) -> Tuple[bool, Optional[str]]:
        """Enforce Staleness Guard (Invariant 3) before consequential mutating dispatches."""
        latest = self.get_latest_observation(entity_id)
        if latest is None:
            return False, f"Freshness Violation: Entity '{entity_id}' has no recorded observations."

        freshness = FreshnessEvaluator.evaluate(latest, current_timestamp)

        # High-risk / critical operations require FRESH state
        if risk_tier in (OperationRiskTier.HIGH_IMPACT, OperationRiskTier.CRITICAL_PRIVILEGED):
            if freshness.freshness_state != FreshnessState.FRESH:
                return False, (
                    f"Staleness Rejection: Critical operation on '{entity_id}' requires FRESH state; "
                    f"found {freshness.freshness_state.value} (staleness score: {freshness.staleness_score})."
                )

        # Medium impact allows FRESH or AGING
        elif risk_tier == OperationRiskTier.MEDIUM_IMPACT:
            if freshness.freshness_state in (FreshnessState.STALE, FreshnessState.EXPIRED, FreshnessState.TOMBSTONED):
                return False, (
                    f"Staleness Rejection: Medium impact action on '{entity_id}' cannot execute against {freshness.freshness_state.value} state."
                )

        return True, None
