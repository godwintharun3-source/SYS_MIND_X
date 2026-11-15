"""Unit and contract tests for SYSTEM MIND X Architecture Baseline v1.0 freeze."""

import pytest
from system_mind.architecture.baseline import (
    ArchitectureBaselineAudit,
    ArchitectureBaselineManifest,
    ArchitectureBaselineRegistry,
    ArchitectureBaselineVerifier,
    ArchitectureComponentSpec,
    BaselineComponentId,
    FreezeStatus,
)


def test_baseline_registry_completeness():
    """Verify all 14 Milestone 2 subsystems are registered with frozen specifications."""
    components = ArchitectureBaselineRegistry.get_all()
    assert len(components) == 14

    for cid in BaselineComponentId:
        assert cid in components
        spec = components[cid]
        assert spec.component_id == cid
        assert spec.name.strip() != ""
        assert 11 <= spec.milestone_day <= 24
        assert spec.adr_reference.startswith("ADR-")
        assert len(spec.core_invariants) >= 3
        assert spec.status == FreezeStatus.FROZEN_APPROVED
        assert len(spec.specification_hash) == 64


def test_specification_hash_determinism_and_sensitivity():
    """Verify that component specification hashes are deterministic and tamper-sensitive."""
    spec = ArchitectureBaselineRegistry.get(BaselineComponentId.ENGINE_CONTRACTS)
    h1 = spec.specification_hash
    h2 = spec.specification_hash
    assert h1 == h2
    assert len(h1) == 64

    # Altering an invariant modifies the specification hash
    mutated_spec = ArchitectureComponentSpec(
        component_id=spec.component_id,
        name=spec.name,
        milestone_day=spec.milestone_day,
        layer_id=spec.layer_id,
        adr_reference=spec.adr_reference,
        core_invariants=spec.core_invariants + ["An unauthorized fourth invariant."],
        implementation_module=spec.implementation_module,
        status=spec.status,
    )
    assert mutated_spec.specification_hash != h1


def test_baseline_manifest_and_fingerprint_generation():
    """Verify construction of immutable baseline manifest and deterministic fingerprint."""
    manifest = ArchitectureBaselineVerifier.build_manifest()
    assert manifest.baseline_version == "1.0.0"
    assert manifest.frozen_date == "2026-11-15"
    assert manifest.total_components == 14
    assert len(manifest.baseline_fingerprint) == 64

    # Recalculating with unchanged components yields identical fingerprint
    fp2 = ArchitectureBaselineVerifier.compute_fingerprint(manifest.components)
    assert fp2 == manifest.baseline_fingerprint


def test_baseline_audit_all_passed():
    """Verify that default baseline manifest audits cleanly with zero issues."""
    audit = ArchitectureBaselineVerifier.audit_baseline()
    assert audit.is_frozen is True
    assert audit.baseline_version == "1.0.0"
    assert audit.verified_components_count == 14
    assert audit.total_invariants_count >= 42  # 14 components * 3 minimum invariants
    assert len(audit.unfrozen_components) == 0
    assert len(audit.issues) == 0


def test_baseline_audit_detects_unfrozen_component():
    """Verify audit fails when any component specification is not frozen."""
    base_components = ArchitectureBaselineRegistry.get_all()
    # Mark ENGINE_CONTRACTS as provisional
    mutated = dict(base_components)
    orig = mutated[BaselineComponentId.ENGINE_CONTRACTS]
    mutated[BaselineComponentId.ENGINE_CONTRACTS] = ArchitectureComponentSpec(
        component_id=orig.component_id,
        name=orig.name,
        milestone_day=orig.milestone_day,
        layer_id=orig.layer_id,
        adr_reference=orig.adr_reference,
        core_invariants=orig.core_invariants,
        implementation_module=orig.implementation_module,
        status=FreezeStatus.PROVISIONAL_REVIEW,
    )

    fp = ArchitectureBaselineVerifier.compute_fingerprint(mutated)
    manifest = ArchitectureBaselineManifest(
        baseline_version="1.0.0",
        frozen_date="2026-11-15",
        total_components=14,
        components=mutated,
        baseline_fingerprint=fp,
    )

    audit = ArchitectureBaselineVerifier.audit_baseline(manifest)
    assert audit.is_frozen is False
    assert BaselineComponentId.ENGINE_CONTRACTS in audit.unfrozen_components
    assert any("is not frozen" in issue for issue in audit.issues)


def test_baseline_audit_detects_missing_component():
    """Verify audit fails when a required subsystem component is omitted."""
    base_components = ArchitectureBaselineRegistry.get_all()
    mutated = dict(base_components)
    del mutated[BaselineComponentId.API_CONVENTIONS]

    fp = ArchitectureBaselineVerifier.compute_fingerprint(mutated)
    manifest = ArchitectureBaselineManifest(
        baseline_version="1.0.0",
        frozen_date="2026-11-15",
        total_components=len(mutated),
        components=mutated,
        baseline_fingerprint=fp,
    )

    audit = ArchitectureBaselineVerifier.audit_baseline(manifest)
    assert audit.is_frozen is False
    assert any("Missing required baseline components" in issue for issue in audit.issues)


def test_baseline_audit_detects_fingerprint_tampering():
    """Verify audit fails when manifest fingerprint does not match computed digest."""
    manifest = ArchitectureBaselineVerifier.build_manifest()
    tampered_manifest = ArchitectureBaselineManifest(
        baseline_version=manifest.baseline_version,
        frozen_date=manifest.frozen_date,
        total_components=manifest.total_components,
        components=manifest.components,
        baseline_fingerprint="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    )

    audit = ArchitectureBaselineVerifier.audit_baseline(tampered_manifest)
    assert audit.is_frozen is False
    assert any("Baseline fingerprint mismatch" in issue for issue in audit.issues)


def test_baseline_audit_detects_insufficient_invariants():
    """Verify audit fails when a component defines fewer than 3 core invariants."""
    base_components = ArchitectureBaselineRegistry.get_all()
    mutated = dict(base_components)
    orig = mutated[BaselineComponentId.FILE_TRUST_POLICY]
    mutated[BaselineComponentId.FILE_TRUST_POLICY] = ArchitectureComponentSpec(
        component_id=orig.component_id,
        name=orig.name,
        milestone_day=orig.milestone_day,
        layer_id=orig.layer_id,
        adr_reference=orig.adr_reference,
        core_invariants=["Only one invariant."],
        implementation_module=orig.implementation_module,
        status=orig.status,
    )

    fp = ArchitectureBaselineVerifier.compute_fingerprint(mutated)
    manifest = ArchitectureBaselineManifest(
        baseline_version="1.0.0",
        frozen_date="2026-11-15",
        total_components=14,
        components=mutated,
        baseline_fingerprint=fp,
    )

    audit = ArchitectureBaselineVerifier.audit_baseline(manifest)
    assert audit.is_frozen is False
    assert any("insufficient core invariants" in issue for issue in audit.issues)


def test_milestone_2_full_day_coverage():
    """Verify every day of Milestone 2 (Days 11-24) maps to a frozen subsystem."""
    components = ArchitectureBaselineRegistry.get_all()
    covered_days = {spec.milestone_day for spec in components.values()}
    for day in range(11, 25):
        assert day in covered_days, f"Day {day} must be covered in architecture baseline."
