"""Tests for read-only host environment inspection and platform tier classification."""

from system_mind.core.types import PlatformTier
from system_mind.host.inspector import HostEnvironmentInspector, MockHostAdapter


def test_live_host_inspection_macos():
    """Verify live inspection runs non-destructively and identifies host environment."""
    inspector = HostEnvironmentInspector()
    report = inspector.inspect()

    assert report.os_name in ("Darwin", "Linux", "Windows")
    assert report.architecture != ""
    assert report.cpu_cores >= 1
    assert isinstance(report.installed_tools, dict)
    assert "python3" in report.installed_tools

    if report.os_name == "Darwin" and report.architecture == "arm64":
        assert report.platform_tier == PlatformTier.TIER_1_HOST_COMPANION
        assert report.is_supported_host is True
        assert report.sip_enabled in (True, False)
        assert report.gatekeeper_enabled in (True, False)


def test_mock_windows_host_inspection():
    """Verify Windows 11 platform classification via mock adapter."""
    mock = MockHostAdapter(
        os_name="Windows",
        os_version="10.0.22631",
        kernel_version="10.0.22631",
        architecture="x86_64",
        cpu_brand="AMD Ryzen 9 7950X",
        cpu_cores=16,
        memory_bytes=34359738368,
        sip_enabled=None,
        gatekeeper_enabled=None,
    )
    inspector = HostEnvironmentInspector(mock_adapter=mock)
    report = inspector.inspect()

    assert report.os_name == "Windows"
    assert report.platform_tier == PlatformTier.TIER_2_WINDOWS
    assert report.is_supported_host is True
    assert report.sip_enabled is None


def test_mock_ubuntu_host_inspection():
    """Verify Ubuntu LTS x86_64 classification via mock adapter."""
    mock = MockHostAdapter(
        os_name="Linux",
        os_version="24.04",
        kernel_version="6.8.0-40-generic",
        architecture="x86_64",
        cpu_brand="Intel Xeon Platinum 8480+",
        cpu_cores=32,
        memory_bytes=68719476736,
        sip_enabled=None,
        gatekeeper_enabled=None,
    )
    inspector = HostEnvironmentInspector(mock_adapter=mock)
    report = inspector.inspect()

    assert report.os_name == "Linux"
    assert report.platform_tier == PlatformTier.TIER_2_UBUNTU
    assert report.is_supported_host is True


def test_mock_unsupported_host_inspection():
    """Verify unsupported platforms are flagged clearly."""
    mock = MockHostAdapter(
        os_name="FreeBSD",
        os_version="14.1-RELEASE",
        kernel_version="14.1",
        architecture="sparc64",
        cpu_brand="SPARC-T5",
        cpu_cores=16,
        memory_bytes=17179869184,
        sip_enabled=None,
        gatekeeper_enabled=None,
    )
    inspector = HostEnvironmentInspector(mock_adapter=mock)
    report = inspector.inspect()

    assert report.platform_tier == PlatformTier.UNSUPPORTED
    assert report.is_supported_host is False
