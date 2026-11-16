"""Tests for the supported first-release platform and hardware matrix."""

import os
import pytest

from system_mind.core.types import (
    CapabilityStatus,
    HostEnvironmentReport,
    PlatformTier,
)
from system_mind.host.inspector import HostEnvironmentInspector, MockHostAdapter
from system_mind.platform.matrix import (
    PlatformMatrixRegistry,
    PlatformTargetId,
)


def test_platform_registry_profile_invariants():
    """Verify registry invariants across all 4 first-release platforms."""
    profiles = PlatformMatrixRegistry.get_all_profiles()
    assert len(profiles) == 4

    dev_hosts = [p for p in profiles if p.is_development_host]
    assert len(dev_hosts) == 1
    assert dev_hosts[0].target_id == PlatformTargetId.MACOS_APPLE_SILICON

    for profile in profiles:
        assert profile.display_name != ""
        assert profile.kernel_family != ""
        assert profile.hardware_spec.min_ram_bytes >= 4 * 1024 * 1024 * 1024
        assert profile.hardware_spec.min_cpu_cores >= 2
        assert len(profile.capabilities) >= 5

    with pytest.raises(KeyError):
        PlatformMatrixRegistry.get_profile("UNSUPPORTED_SOLARIS")  # type: ignore


def test_platform_capability_completeness_and_limitations():
    """Verify that all capabilities have documented native APIs, limitations, and fallback strategies."""
    profiles = PlatformMatrixRegistry.get_all_profiles()

    for profile in profiles:
        for cap_id, cap in profile.capabilities.items():
            assert cap.capability_id == cap_id
            assert cap.native_api != ""
            assert cap.fallback_strategy != ""
            assert cap.status in (CapabilityStatus.SUPPORTED, CapabilityStatus.PARTIAL, CapabilityStatus.MOCK_ONLY)

            # Invariant: If a capability is PARTIAL, it MUST have documented limitations explaining why!
            if cap.status == CapabilityStatus.PARTIAL:
                assert len(cap.limitations) > 0, f"Partial capability '{cap_id}' on '{profile.target_id}' must document limitations"


def test_capability_status_queries():
    """Verify capability status lookups and fallback for unknown capabilities."""
    # macOS hardware sensors is partial due to private Apple Silicon SMC keys
    macos_sensor_status = PlatformMatrixRegistry.get_capability_status(
        PlatformTargetId.MACOS_APPLE_SILICON, "hardware_sensors"
    )
    assert macos_sensor_status == CapabilityStatus.PARTIAL

    # Windows sandboxing is partial (Windows Sandbox not on Home edition)
    win_sandbox_status = PlatformMatrixRegistry.get_capability_status(
        PlatformTargetId.WINDOWS_11_X64, "controlled_sandboxing"
    )
    assert win_sandbox_status == CapabilityStatus.PARTIAL

    # Digital twin events on Ubuntu is supported
    ubuntu_dt_status = PlatformMatrixRegistry.get_capability_status(
        PlatformTargetId.UBUNTU_LTS_X64, "digital_twin_events"
    )
    assert ubuntu_dt_status == CapabilityStatus.SUPPORTED

    # Unknown capability returns UNSUPPORTED
    unknown_status = PlatformMatrixRegistry.get_capability_status(
        PlatformTargetId.MACOS_APPLE_SILICON, "teleportation_quantum_entanglement"
    )
    assert unknown_status == CapabilityStatus.UNSUPPORTED


def test_live_host_compatibility_validation():
    """Verify live macOS host report passes compatibility validation as Tier 1 development host."""
    inspector = HostEnvironmentInspector()
    live_report = inspector.inspect()

    is_compatible, diagnostics = PlatformMatrixRegistry.validate_host_compatibility(live_report)
    if os.environ.get("CI") == "true" and not is_compatible:
        # In virtualized cloud CI runners (e.g. GitHub Actions macos-latest with 3 cores / 7GB RAM / SIP disabled),
        # verify that compatibility diagnostics accurately reflect the runner constraints.
        assert len(diagnostics) > 0
        assert any("Insufficient" in d or "SIP" in d or "Virtual" in d for d in diagnostics)
    else:
        assert is_compatible is True, f"Live host unexpectedly failed compatibility: {diagnostics}"
        assert len(diagnostics) == 0


def test_host_compatibility_insufficient_ram():
    """Verify validation detects and reports insufficient RAM."""
    insufficient_ram_report = HostEnvironmentReport(
        os_name="Darwin",
        os_version="27.0.1",
        kernel_version="27.0.0",
        architecture="arm64",
        cpu_brand="Apple M1",
        cpu_cores=8,
        memory_bytes=4 * 1024 * 1024 * 1024,  # 4 GB (requires 8 GB)
        sip_enabled=True,
        gatekeeper_enabled=True,
        platform_tier=PlatformTier.TIER_1_HOST_COMPANION,
    )
    is_compatible, diagnostics = PlatformMatrixRegistry.validate_host_compatibility(insufficient_ram_report)
    assert is_compatible is False
    assert any("Insufficient Memory" in d for d in diagnostics)


def test_host_compatibility_insufficient_cpu_cores():
    """Verify validation detects and reports insufficient CPU cores."""
    insufficient_cpu_report = HostEnvironmentReport(
        os_name="Darwin",
        os_version="27.0.1",
        kernel_version="27.0.0",
        architecture="arm64",
        cpu_brand="Apple M1",
        cpu_cores=2,  # 2 cores (requires 8 cores on macOS M1 target)
        memory_bytes=8 * 1024 * 1024 * 1024,
        sip_enabled=True,
        gatekeeper_enabled=True,
        platform_tier=PlatformTier.TIER_1_HOST_COMPANION,
    )
    is_compatible, diagnostics = PlatformMatrixRegistry.validate_host_compatibility(insufficient_cpu_report)
    assert is_compatible is False
    assert any("Insufficient CPU Cores" in d for d in diagnostics)


def test_host_compatibility_unsupported_platform():
    """Verify validation detects unsupported operating systems and architectures."""
    unsupported_report = HostEnvironmentReport(
        os_name="FreeBSD",
        os_version="14.0",
        kernel_version="14.0-RELEASE",
        architecture="sparc64",
        cpu_brand="SPARC-T5",
        cpu_cores=16,
        memory_bytes=32 * 1024 * 1024 * 1024,
        sip_enabled=None,
        gatekeeper_enabled=None,
        platform_tier=PlatformTier.UNSUPPORTED,
    )
    is_compatible, diagnostics = PlatformMatrixRegistry.validate_host_compatibility(unsupported_report)
    assert is_compatible is False
    assert any("outside the first-release support matrix" in d for d in diagnostics)
