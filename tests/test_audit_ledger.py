"""Tests for Immutable Audit Ledger, Cryptographic Hash Chaining, Secret Redaction, and Data Retention."""

from __future__ import annotations

import datetime
import pytest

from system_mind.audit.ledger import ImmutableAuditLedger, SecretRedactor
from system_mind.audit.models import (
    AuditEventCategory,
    AuditEventSeverity,
    RetentionClass,
)
from system_mind.core.types import ComponentOwnership
from system_mind.governance.models import IdentityType


def test_secret_redactor_deep_nested_and_keys():
    """Verify that SecretRedactor sanitizes credentials, tokens, and private keys."""
    raw_payload = {
        "operation": "update_config",
        "api_key": "secret_live_1234567890",
        "user": {
            "name": "developer",
            "password": "SuperSecretPassword123!",
            "session_token": "token_abc_xyz",
        },
        "headers": [
            "Content-Type: application/json",
            "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
        ],
        "private_key": "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0...",
        "non_sensitive_field": "public_data",
    }

    redacted = SecretRedactor.redact(raw_payload)

    assert redacted["api_key"] == SecretRedactor.REDACTION_MARKER
    assert redacted["user"]["password"] == SecretRedactor.REDACTION_MARKER
    assert redacted["user"]["session_token"] == SecretRedactor.REDACTION_MARKER
    assert redacted["headers"][1] == SecretRedactor.REDACTION_MARKER
    assert redacted["private_key"] == SecretRedactor.REDACTION_MARKER
    assert redacted["non_sensitive_field"] == "public_data"


def test_audit_ledger_append_and_hash_chaining():
    """Verify strictly monotonic sequence numbers and SHA-256 chain linkage."""
    ledger = ImmutableAuditLedger()

    ev1 = ledger.append_event(
        event_id="audit-001",
        timestamp_iso="2026-11-15T12:00:00Z",
        event_category=AuditEventCategory.POLICY_EVALUATION,
        severity=AuditEventSeverity.INFO,
        retention_class=RetentionClass.POLICY_DECISION,
        actor_principal="system_mind_caretaker",
        identity_type=IdentityType.AI_COGNITIVE_PLANNER,
        target_component="entity-sys",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        capability_id="telemetry.read",
        payload={"query": "cpu_thermals"},
    )
    assert ev1.sequence_number == 1
    assert ev1.prev_event_hash == ImmutableAuditLedger.GENESIS_PREV_HASH
    assert len(ev1.event_hash) == 64

    ev2 = ledger.append_event(
        event_id="audit-002",
        timestamp_iso="2026-11-15T12:01:00Z",
        event_category=AuditEventCategory.BROKER_DISPATCH,
        severity=AuditEventSeverity.INFO,
        retention_class=RetentionClass.SYSTEM_MUTATION,
        actor_principal="developer",
        identity_type=IdentityType.LOCAL_CONSOLE_USER,
        target_component="/var/log/system.log",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        capability_id="broker.fs.cache_prune",
        payload={"bytes_freed": 1048576},
    )
    assert ev2.sequence_number == 2
    assert ev2.prev_event_hash == ev1.event_hash

    # Verification passes
    verification = ledger.verify_integrity()
    assert verification.is_valid is True
    assert verification.verified_event_count == 2
    assert len(verification.discrepancies) == 0


def test_audit_ledger_detects_tampered_payload():
    """Verify that modifying stored event payloads invalidates the ledger."""
    ledger = ImmutableAuditLedger()
    ledger.append_event(
        event_id="audit-001",
        timestamp_iso="2026-11-15T12:00:00Z",
        event_category=AuditEventCategory.STATE_MUTATION,
        severity=AuditEventSeverity.INFO,
        retention_class=RetentionClass.SYSTEM_MUTATION,
        actor_principal="admin",
        identity_type=IdentityType.LOCAL_CONSOLE_USER,
        target_component="sys-core",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        capability_id="broker.system.snapshot",
        payload={"status": "snapshot_created"},
    )

    # Tamper with the event payload directly
    ledger._events[0].payload["status"] = "tampered_value"

    verification = ledger.verify_integrity()
    assert verification.is_valid is False
    assert "audit-001" in verification.tampered_event_ids
    assert any("PayloadTampered" in d for d in verification.discrepancies)


def test_audit_ledger_detects_broken_chain_link():
    """Verify that tampering with prev_event_hash is caught during verification."""
    ledger = ImmutableAuditLedger()
    ledger.append_event(
        event_id="audit-001",
        timestamp_iso="2026-11-15T12:00:00Z",
        event_category=AuditEventCategory.POLICY_EVALUATION,
        severity=AuditEventSeverity.INFO,
        retention_class=RetentionClass.POLICY_DECISION,
        actor_principal="agent",
        identity_type=IdentityType.AI_COGNITIVE_PLANNER,
        target_component="target-1",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        capability_id="twin.query",
        payload={"field": "data1"},
    )
    ledger.append_event(
        event_id="audit-002",
        timestamp_iso="2026-11-15T12:01:00Z",
        event_category=AuditEventCategory.BROKER_DISPATCH,
        severity=AuditEventSeverity.INFO,
        retention_class=RetentionClass.SYSTEM_MUTATION,
        actor_principal="agent",
        identity_type=IdentityType.AI_COGNITIVE_PLANNER,
        target_component="target-2",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        capability_id="broker.fs.write",
        payload={"field": "data2"},
    )

    # Tamper with chain link
    ledger._events[1].prev_event_hash = "f" * 64

    verification = ledger.verify_integrity()
    assert verification.is_valid is False
    assert "audit-002" in verification.tampered_event_ids
    assert any("ChainBroken" in d for d in verification.discrepancies)


def test_retention_pruning_creates_checkpoint_anchor():
    """Verify that expired events are pruned and anchor checkpoint is created."""
    ledger = ImmutableAuditLedger()
    t0 = datetime.datetime(2026, 11, 1, 0, 0, 0, tzinfo=datetime.timezone.utc)

    # 1. Ephemeral event (2 days TTL)
    ledger.append_event(
        event_id="audit-ephemeral",
        timestamp_iso=t0.isoformat(),
        event_category=AuditEventCategory.STATE_MUTATION,
        severity=AuditEventSeverity.INFO,
        retention_class=RetentionClass.EPHEMERAL_TRACE,
        actor_principal="sandbox",
        identity_type=IdentityType.SANDBOXED_PEER_AGENT,
        target_component="micro_vm",
        target_ownership=ComponentOwnership.USER_MANAGED,
        capability_id="sandbox.detonate",
        payload={"trace": "syscall_log"},
    )

    # 2. Recent mutation event (90 days TTL)
    ledger.append_event(
        event_id="audit-recent",
        timestamp_iso=(t0 + datetime.timedelta(days=1)).isoformat(),
        event_category=AuditEventCategory.STATE_MUTATION,
        severity=AuditEventSeverity.INFO,
        retention_class=RetentionClass.SYSTEM_MUTATION,
        actor_principal="admin",
        identity_type=IdentityType.LOCAL_CONSOLE_USER,
        target_component="os-patch",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        capability_id="broker.update.apply",
        payload={"patch": "kb001"},
    )

    assert ledger.event_count == 2

    # Prune as of 5 days later (ephemeral event is 5 days old > 2 days TTL)
    t_prune = (t0 + datetime.timedelta(days=5)).isoformat()
    checkpoint = ledger.prune_expired_events(current_time_iso=t_prune)

    assert checkpoint is not None
    assert checkpoint.pruned_up_to_sequence == 1
    assert ledger.event_count == 1
    assert ledger.latest_event.event_id == "audit-recent"
    assert len(ledger.checkpoints) == 1


def test_critical_security_records_immutable_never_pruned():
    """Verify that CRITICAL_SECURITY records are NEVER pruned even after TTL expiration."""
    ledger = ImmutableAuditLedger()
    t_ancient = (datetime.datetime(2020, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc)).isoformat()

    # Ancient critical security event (over 6 years old!)
    ledger.append_event(
        event_id="audit-sec-breach",
        timestamp_iso=t_ancient,
        event_category=AuditEventCategory.SECURITY_ALERT,
        severity=AuditEventSeverity.CRITICAL_SECURITY,
        retention_class=RetentionClass.CRITICAL_SECURITY,
        actor_principal="intruder",
        identity_type=IdentityType.SANDBOXED_PEER_AGENT,
        target_component="sip_framework",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        capability_id="broker.security.disable_sip",
        payload={"alert": "Unauthorized SIP disable attempt blocked"},
    )

    # Prune as of 2026-11-15
    cp = ledger.prune_expired_events(current_time_iso="2026-11-15T12:00:00Z")
    assert cp is None  # Nothing pruned
    assert ledger.event_count == 1
    assert ledger.latest_event.event_id == "audit-sec-breach"
