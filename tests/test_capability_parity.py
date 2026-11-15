"""Unit and contract tests for cross-platform capability parity levels and evaluation."""

import pytest

from system_mind.platform import (
    CapabilityDomain,
    CapabilityParityEvaluator,
    CapabilityParityRegistry,
    ParityLevel,
    PlatformCapabilityUnsupportedError,
    PlatformTargetId,
)


def test_parity_matrix_completeness_and_dimensions():
    """Verify that all 4 platforms and 8 capability domains (32 specs) are cataloged."""
    specs = CapabilityParityRegistry.get_all_specs()
    assert len(specs) == 32

    for platform in PlatformTargetId:
        platform_specs = CapabilityParityRegistry.get_platform_specs(platform)
        assert len(platform_specs) == 8
        domains_present = {s.domain for s in platform_specs}
        assert domains_present == set(CapabilityDomain)


def test_parity_evaluator_audit_passes():
    """Verify that the parity evaluator audit reports 100% matrix completeness and invariant validity."""
    is_valid, violations = CapabilityParityEvaluator.audit_matrix_completeness()
    assert is_valid is True
    assert len(violations) == 0


def test_security_authority_enforcement_invariants():
    """Verify that SECURITY_AUTHORITY_ENFORCEMENT is LEVEL_1_FULL_PARITY on all supported platforms."""
    for platform in PlatformTargetId:
        spec = CapabilityParityRegistry.get_spec(platform, CapabilityDomain.SECURITY_AUTHORITY_ENFORCEMENT)
        assert spec.parity_level == ParityLevel.LEVEL_1_FULL_PARITY
        assert spec.is_security_critical is True
        assert spec.native_api.strip()


def test_registry_lookups_and_filtering():
    """Verify retrieval by platform, by domain, and single spec lookup."""
    # Lookup by platform
    macos_specs = CapabilityParityRegistry.get_platform_specs(PlatformTargetId.MACOS_APPLE_SILICON)
    assert len(macos_specs) == 8

    # Lookup by domain
    fs_specs = CapabilityParityRegistry.get_domain_specs(CapabilityDomain.FS_OBSERVATION)
    assert len(fs_specs) == 4

    # Single spec lookup
    spec = CapabilityParityRegistry.get_spec(
        PlatformTargetId.MACOS_APPLE_SILICON, CapabilityDomain.FS_OBSERVATION
    )
    assert spec.parity_level == ParityLevel.LEVEL_1_FULL_PARITY
    assert "FSEvents" in spec.native_api

    # Nonexistent target error
    with pytest.raises(KeyError):
        CapabilityParityRegistry.get_spec("INVALID_PLATFORM", CapabilityDomain.FS_OBSERVATION)  # type: ignore


def test_evaluator_dispatch_level_1_full_parity():
    """Verify evaluation dispatch for a LEVEL_1_FULL_PARITY capability."""
    res = CapabilityParityEvaluator.evaluate_dispatch(
        platform=PlatformTargetId.MACOS_APPLE_SILICON,
        domain=CapabilityDomain.FS_OBSERVATION,
        requires_full_parity=True,
    )
    assert res.permitted is True
    assert res.parity_level == ParityLevel.LEVEL_1_FULL_PARITY
    assert "FSEvents" in res.native_api
    assert res.active_fallback is None
    assert len(res.warnings) == 0


def test_evaluator_dispatch_equivalent_and_degraded_parity():
    """Verify evaluation dispatch and warning generation for equivalent and degraded capabilities."""
    # macOS Hardware Telemetry is DEGRADED (Level 3) due to SMC thermal keys
    res_degraded = CapabilityParityEvaluator.evaluate_dispatch(
        platform=PlatformTargetId.MACOS_APPLE_SILICON,
        domain=CapabilityDomain.HARDWARE_TELEMETRY,
        requires_full_parity=False,
    )
    assert res_degraded.permitted is True
    assert res_degraded.parity_level == ParityLevel.LEVEL_3_DEGRADED_PARITY
    assert res_degraded.active_fallback is not None
    assert any("Degraded Parity Warning" in w for w in res_degraded.warnings)

    # Windows FS Observation is EQUIVALENT (Level 2) via USN Journal
    res_equiv = CapabilityParityEvaluator.evaluate_dispatch(
        platform=PlatformTargetId.WINDOWS_11_X64,
        domain=CapabilityDomain.FS_OBSERVATION,
        requires_full_parity=False,
    )
    assert res_equiv.permitted is True
    assert res_equiv.parity_level == ParityLevel.LEVEL_2_EQUIVALENT_PARITY
    assert any("Equivalent Parity Note" in w for w in res_equiv.warnings)


def test_evaluator_blocks_when_full_parity_strictly_required():
    """Verify that requiring strict full parity rejects degraded or equivalent capabilities."""
    res = CapabilityParityEvaluator.evaluate_dispatch(
        platform=PlatformTargetId.MACOS_APPLE_SILICON,
        domain=CapabilityDomain.HARDWARE_TELEMETRY,
        requires_full_parity=True,
    )
    assert res.permitted is False
    assert res.parity_level == ParityLevel.LEVEL_3_DEGRADED_PARITY
    assert any("Strict Parity Rejection" in w for w in res.warnings)


def test_evaluator_raises_on_unsupported_capability():
    """Verify that requesting an unsupported capability raises PlatformCapabilityUnsupportedError."""
    # Verify that if an unsupported spec is present, it raises
    from unittest.mock import patch

    unsupported_spec = CapabilityParityRegistry.get_spec(
        PlatformTargetId.MACOS_APPLE_SILICON, CapabilityDomain.FS_OBSERVATION
    )
    # create a mock spec with LEVEL_5_UNSUPPORTED
    mock_unsupported = pytest.importorskip("dataclasses").replace(
        unsupported_spec, parity_level=ParityLevel.LEVEL_5_UNSUPPORTED
    )

    with patch.object(CapabilityParityRegistry, "get_spec", return_value=mock_unsupported):
        with pytest.raises(PlatformCapabilityUnsupportedError) as exc_info:
            CapabilityParityEvaluator.evaluate_dispatch(
                platform=PlatformTargetId.MACOS_APPLE_SILICON,
                domain=CapabilityDomain.FS_OBSERVATION,
            )
        assert "does not support capability domain" in str(exc_info.value)
