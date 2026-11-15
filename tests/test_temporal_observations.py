"""Unit and contract tests for temporal observations, provenance, and freshness metadata."""

import pytest

from system_mind.core.types import OperationRiskTier
from system_mind.twin import (
    FreshnessEvaluator,
    FreshnessMetadata,
    FreshnessState,
    ObservationType,
    ProvenanceMetadata,
    ProvenanceStatus,
    StateDelta,
    TemporalObservation,
    TemporalTimelineStore,
    compute_payload_hash,
)


def test_temporal_enums_and_payload_hashing():
    """Verify temporal enums and deterministic SHA-256 payload hashing."""
    assert len(ObservationType) == 5
    assert len(ProvenanceStatus) == 4
    assert len(FreshnessState) == 5

    payload_a = {"pid": 101, "name": "daemon", "active": True}
    payload_b = {"name": "daemon", "active": True, "pid": 101}  # Different key order

    hash_a = compute_payload_hash(payload_a)
    hash_b = compute_payload_hash(payload_b)
    assert hash_a == hash_b
    assert len(hash_a) == 64


def test_freshness_evaluator_decay_lifecycle():
    """Verify decay calculation and state transitions across elapsed time windows."""
    base_time = "2026-11-15T21:00:00Z"
    obs = TemporalObservation(
        observation_id="obs-001",
        entity_id="urn:twin:proc:100",
        observed_at=base_time,
        observation_seq=1,
        observation_type=ObservationType.STATE_SNAPSHOT,
        observed_state={"state": "active"},
        provenance=ProvenanceMetadata(
            source_engine="ENG-01:telemetry",
            collector_method="proc_pidinfo",
            payload_sha256=compute_payload_hash({"state": "active"}),
            verification_status=ProvenanceStatus.VERIFIED_KERNEL,
        ),
        freshness=FreshnessMetadata(ttl_seconds=10.0, max_acceptable_staleness_seconds=30.0),
    )

    # 1. At t=2s (<= ttl/2 = 5s) -> FRESH
    fresh_eval = FreshnessEvaluator.evaluate(obs, "2026-11-15T21:00:02Z")
    assert fresh_eval.freshness_state == FreshnessState.FRESH
    assert 0.0 <= fresh_eval.staleness_score <= 0.5

    # 2. At t=7s (5s < t <= 10s) -> AGING
    aging_eval = FreshnessEvaluator.evaluate(obs, "2026-11-15T21:00:07Z")
    assert aging_eval.freshness_state == FreshnessState.AGING
    assert 0.5 <= aging_eval.staleness_score <= 0.8

    # 3. At t=15s (10s < t <= 30s) -> STALE
    stale_eval = FreshnessEvaluator.evaluate(obs, "2026-11-15T21:00:15Z")
    assert stale_eval.freshness_state == FreshnessState.STALE
    assert 0.8 <= stale_eval.staleness_score <= 1.0

    # 4. At t=35s (> 30s) -> EXPIRED
    expired_eval = FreshnessEvaluator.evaluate(obs, "2026-11-15T21:00:35Z")
    assert expired_eval.freshness_state == FreshnessState.EXPIRED
    assert expired_eval.staleness_score == 1.0


def test_timeline_store_append_and_invariants():
    """Verify chronological timeline appending, monotonic sequence, and payload validation."""
    store = TemporalTimelineStore()
    entity_id = "urn:twin:file:/etc/hosts"

    state1 = {"size": 120, "sha256": "abc123"}
    obs1 = TemporalObservation(
        observation_id="obs-seq-1",
        entity_id=entity_id,
        observed_at="2026-11-15T21:00:00Z",
        observation_seq=1,
        observation_type=ObservationType.STATE_SNAPSHOT,
        observed_state=state1,
        provenance=ProvenanceMetadata(
            source_engine="ENG-09:fsevents",
            collector_method="FSEvents",
            payload_sha256=compute_payload_hash(state1),
            verification_status=ProvenanceStatus.VERIFIED_KERNEL,
        ),
        freshness=FreshnessMetadata(),
    )
    store.record_observation(obs1)
    assert store.get_latest_observation(entity_id) == obs1

    # Invariant 2 Violation: Payload hash mismatch
    state_tampered = {"size": 240, "sha256": "def456"}
    obs_tampered = TemporalObservation(
        observation_id="obs-tampered",
        entity_id=entity_id,
        observed_at="2026-11-15T21:00:05Z",
        observation_seq=2,
        observation_type=ObservationType.ATTRIBUTE_DELTA,
        observed_state=state_tampered,
        provenance=ProvenanceMetadata(
            source_engine="ENG-09:fsevents",
            collector_method="FSEvents",
            payload_sha256="wrong_fake_hash",
            verification_status=ProvenanceStatus.UNVERIFIED_USER_SPACE,
        ),
        freshness=FreshnessMetadata(),
    )
    with pytest.raises(ValueError) as exc_hash:
        store.record_observation(obs_tampered)
    assert "Payload hash mismatch" in str(exc_hash.value)

    # Invariant 1 Violation: Monotonic sequence violation
    state2 = {"size": 130}
    obs_bad_seq = TemporalObservation(
        observation_id="obs-bad-seq",
        entity_id=entity_id,
        observed_at="2026-11-15T21:00:05Z",
        observation_seq=1,  # Duplicate seq
        observation_type=ObservationType.ATTRIBUTE_DELTA,
        observed_state=state2,
        provenance=ProvenanceMetadata(
            source_engine="ENG-09:fsevents",
            collector_method="FSEvents",
            payload_sha256=compute_payload_hash(state2),
            verification_status=ProvenanceStatus.VERIFIED_KERNEL,
        ),
        freshness=FreshnessMetadata(),
    )
    with pytest.raises(ValueError) as exc_seq:
        store.record_observation(obs_bad_seq)
    assert "Monotonic Sequence Violation" in str(exc_seq.value)


def test_point_in_time_state_reconstruction_and_diffing():
    """Verify point-in-time state reconstruction and state delta computation."""
    store = TemporalTimelineStore()
    eid = "urn:twin:proc:2048"

    # Seq 1: Snapshot at t=0s
    s1 = {"status": "starting", "cpu": 5.0, "memory": 1024}
    obs1 = TemporalObservation(
        observation_id="obs-2048-1",
        entity_id=eid,
        observed_at="2026-11-15T21:00:00Z",
        observation_seq=1,
        observation_type=ObservationType.STATE_SNAPSHOT,
        observed_state=s1,
        provenance=ProvenanceMetadata(
            source_engine="ENG-01:telemetry",
            collector_method="proc_pidinfo",
            payload_sha256=compute_payload_hash(s1),
            verification_status=ProvenanceStatus.VERIFIED_KERNEL,
        ),
        freshness=FreshnessMetadata(),
    )
    store.record_observation(obs1)

    # Seq 2: Delta at t=5s
    s2 = {"status": "running", "cpu": 25.0}
    obs2 = TemporalObservation(
        observation_id="obs-2048-2",
        entity_id=eid,
        observed_at="2026-11-15T21:00:05Z",
        observation_seq=2,
        observation_type=ObservationType.ATTRIBUTE_DELTA,
        observed_state=s2,
        provenance=ProvenanceMetadata(
            source_engine="ENG-01:telemetry",
            collector_method="proc_pidinfo",
            payload_sha256=compute_payload_hash(s2),
            verification_status=ProvenanceStatus.VERIFIED_KERNEL,
        ),
        freshness=FreshnessMetadata(),
    )
    store.record_observation(obs2)

    # Seq 3: Delta at t=10s
    s3 = {"status": "idle", "cpu": 1.5, "connections": 3}
    obs3 = TemporalObservation(
        observation_id="obs-2048-3",
        entity_id=eid,
        observed_at="2026-11-15T21:00:10Z",
        observation_seq=3,
        observation_type=ObservationType.ATTRIBUTE_DELTA,
        observed_state=s3,
        provenance=ProvenanceMetadata(
            source_engine="ENG-01:telemetry",
            collector_method="proc_pidinfo",
            payload_sha256=compute_payload_hash(s3),
            verification_status=ProvenanceStatus.VERIFIED_KERNEL,
        ),
        freshness=FreshnessMetadata(),
    )
    store.record_observation(obs3)

    # Reconstruct state at t=6s (between seq 2 and seq 3)
    state_at_t6 = store.reconstruct_state_at(eid, "2026-11-15T21:00:06Z")
    assert state_at_t6 == {"status": "running", "cpu": 25.0, "memory": 1024}

    # Reconstruct state at t=12s (after seq 3)
    state_at_t12 = store.reconstruct_state_at(eid, "2026-11-15T21:00:12Z")
    assert state_at_t12 == {"status": "idle", "cpu": 1.5, "memory": 1024, "connections": 3}

    # Compute StateDelta between seq 1 and seq 3
    delta = store.compute_state_diff(eid, from_seq=1, to_seq=3)
    assert delta.from_seq == 1
    assert delta.to_seq == 3
    assert delta.added_or_modified == {"status": "idle", "cpu": 1.5, "connections": 3}


def test_staleness_guard_enforces_execution_freshness():
    """Verify that Staleness Guard (Invariant 3) blocks consequential actions on stale state."""
    store = TemporalTimelineStore()
    eid = "urn:twin:config:daemon"

    s1 = {"max_workers": 4}
    obs = TemporalObservation(
        observation_id="obs-cfg-1",
        entity_id=eid,
        observed_at="2026-11-15T21:00:00Z",
        observation_seq=1,
        observation_type=ObservationType.STATE_SNAPSHOT,
        observed_state=s1,
        provenance=ProvenanceMetadata(
            source_engine="ENG-01:telemetry",
            collector_method="sysctl",
            payload_sha256=compute_payload_hash(s1),
            verification_status=ProvenanceStatus.VERIFIED_KERNEL,
        ),
        freshness=FreshnessMetadata(ttl_seconds=10.0, max_acceptable_staleness_seconds=30.0),
    )
    store.record_observation(obs)

    # Case 1: Fresh state (t=2s) allows CRITICAL_PRIVILEGED operation
    allowed_fresh, msg_fresh = store.validate_dispatch_freshness(
        eid, "2026-11-15T21:00:02Z", OperationRiskTier.CRITICAL_PRIVILEGED
    )
    assert allowed_fresh is True
    assert msg_fresh is None

    # Case 2: Aging state (t=7s) rejects CRITICAL_PRIVILEGED but allows MEDIUM_IMPACT
    allowed_aging_crit, msg_crit = store.validate_dispatch_freshness(
        eid, "2026-11-15T21:00:07Z", OperationRiskTier.CRITICAL_PRIVILEGED
    )
    assert allowed_aging_crit is False
    assert "requires FRESH state" in msg_crit

    allowed_aging_med, msg_med = store.validate_dispatch_freshness(
        eid, "2026-11-15T21:00:07Z", OperationRiskTier.MEDIUM_IMPACT
    )
    assert allowed_aging_med is True

    # Case 3: Stale state (t=15s) rejects MEDIUM_IMPACT
    allowed_stale_med, msg_stale = store.validate_dispatch_freshness(
        eid, "2026-11-15T21:00:15Z", OperationRiskTier.MEDIUM_IMPACT
    )
    assert allowed_stale_med is False
    assert "cannot execute against STALE state" in msg_stale

    # Case 4: Nonexistent entity rejected
    allowed_missing, msg_missing = store.validate_dispatch_freshness(
        "urn:twin:nonexistent", "2026-11-15T21:00:02Z", OperationRiskTier.LOW_IMPACT
    )
    assert allowed_missing is False
    assert "has no recorded observations" in msg_missing
