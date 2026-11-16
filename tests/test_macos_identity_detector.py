"""Comprehensive unit, contract, and integration tests for macOS Identity and Telemetry Detection."""

from __future__ import annotations

import json
from pathlib import Path
import platform
import re
import subprocess
import sys
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent

from system_mind.macos.detector import MacOSIdentityDetector
from system_mind.macos.models import (
    MacArchitecture,
    MacHostIdentity,
    MacOSVersionInfo,
    MacTelemetryReport,
)
from system_mind.packaging.macos_telemetry import (
    MacOsTelemetryAuditResult,
    MacOsTelemetryValidator,
)
from system_mind.platform.adapter import (
    MockPlatformAdapter,
    MockPlatformProfileFactory,
)
from system_mind.platform.matrix import PlatformTargetId


def test_marketing_name_resolution():
    """Verify marketing name resolution across historical, modern, and preview macOS releases."""
    assert MacOSIdentityDetector.resolve_marketing_name(15) == "Sequoia"
    assert MacOSIdentityDetector.resolve_marketing_name(14) == "Sonoma"
    assert MacOSIdentityDetector.resolve_marketing_name(13) == "Ventura"
    assert MacOSIdentityDetector.resolve_marketing_name(12) == "Monterey"
    assert MacOSIdentityDetector.resolve_marketing_name(11) == "Big Sur"
    assert MacOSIdentityDetector.resolve_marketing_name(10, 15) == "Catalina"
    assert MacOSIdentityDetector.resolve_marketing_name(10, 14) == "Mojave"
    assert "Darwin 27" in MacOSIdentityDetector.resolve_marketing_name(27, 0, darwin_release="27.3.0")
    assert MacOSIdentityDetector.resolve_marketing_name(16) == "macOS (Major 16)"


def test_macos_identity_detector_mock_mode():
    """Verify detection using MockPlatformAdapter generates consistent, deterministic telemetry."""
    mock = MockPlatformProfileFactory.create_macos_apple_silicon_mock()
    report = MacOSIdentityDetector.detect(mock_adapter=mock)

    assert isinstance(report, MacTelemetryReport)
    assert report.collection_method == "MOCK_PLATFORM_ADAPTER"
    assert report.version_info.product_name == "macOS"
    assert report.version_info.major_version == 15
    assert report.version_info.marketing_name == "Sequoia"
    assert report.version_info.build_version == "24B83"

    assert report.architecture.is_apple_silicon is True
    assert report.architecture.machine == "arm64"
    assert report.architecture.pointer_size_bits == 64
    assert report.architecture.is_rosetta_translated is False

    assert report.identity.platform_uuid is not None
    assert report.identity.anonymized_serial_hash is not None
    assert report.identity.anonymized_serial_hash.startswith("sha256:")
    assert len(report.unavailable_telemetry) == 0


def test_macos_identity_detector_live_on_darwin():
    """Verify live detection returns valid facts when executing on native Darwin macOS host."""
    if platform.system() != "Darwin":
        pytest.skip("Test requires native macOS Darwin host")

    report = MacOSIdentityDetector.detect()

    assert isinstance(report, MacTelemetryReport)
    assert report.collection_method == "NATIVE_DARWIN_SYSCTL"
    assert report.version_info.product_name == "macOS"
    assert report.version_info.product_version != ""
    assert report.version_info.major_version >= 11
    assert report.version_info.build_version != ""
    assert report.version_info.darwin_kernel_release != ""

    assert report.architecture.pointer_size_bits == 64
    assert report.architecture.byte_order == "little"
    assert isinstance(report.architecture.is_apple_silicon, bool)
    assert isinstance(report.architecture.is_rosetta_translated, bool)

    assert report.identity.hostname != ""
    assert report.identity.computer_name != ""
    assert report.identity.local_host_name != ""


def test_privacy_serial_anonymization_invariant():
    """Verify hardware serial numbers are cryptographically salted and anonymized, never plaintext."""
    mock = MockPlatformProfileFactory.create_macos_apple_silicon_mock()
    report = MacOSIdentityDetector.detect(mock_adapter=mock)

    serial_hash = report.identity.anonymized_serial_hash
    assert serial_hash is not None
    assert serial_hash.startswith("sha256:")
    # Ensure raw serial format (typically 10-12 alphanumeric characters) is NOT exposed
    assert not re.match(r"^[A-Z0-9]{10,12}$", serial_hash)


def test_non_darwin_fallback_behavior():
    """Verify non-Darwin fallback reports graceful partial capabilities with explicit missing telemetry."""
    fallback_report = MacOSIdentityDetector._detect_non_darwin_fallback()

    assert fallback_report.collection_method == "NON_DARWIN_FALLBACK"
    assert len(fallback_report.unavailable_telemetry) >= 3
    assert "native_darwin_sysctl" in fallback_report.unavailable_telemetry
    assert len(fallback_report.warnings) > 0


def test_macos_telemetry_validator_clean_audit():
    """Verify MacOsTelemetryValidator reports clean audit of models, detector, and CLI."""
    audit_result = MacOsTelemetryValidator.audit()
    assert audit_result.valid is True, f"Validation failed with issues: {audit_result.issues}"
    assert audit_result.models_valid is True
    assert audit_result.detector_valid is True
    assert audit_result.cli_valid is True
    assert audit_result.privacy_anonymization_valid is True
    assert len(audit_result.issues) == 0


def test_detect_macos_cli_execution():
    """Verify tools/detect_macos.py CLI executions in mock, strict, and JSON modes."""
    cli_path = ROOT_DIR / "tools" / "detect_macos.py"

    # Mock JSON mode
    proc = subprocess.run(
        [sys.executable, str(cli_path), "--mock", "--json"],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(proc.stdout)
    assert data["collection_method"] == "MOCK_PLATFORM_ADAPTER"
    assert data["version_info"]["marketing_name"] == "Sequoia"
    assert data["architecture"]["is_apple_silicon"] is True

    # Strict Apple Silicon flag on mock
    proc_strict = subprocess.run(
        [sys.executable, str(cli_path), "--mock", "--strict-apple-silicon"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "macOS Companion Agent" in proc_strict.stdout


def test_mock_non_darwin_profile_warnings():
    """Verify detector sets appropriate warnings when passed a non-Darwin mock adapter."""
    win_mock = MockPlatformProfileFactory.create_windows_11_mock()
    report = MacOSIdentityDetector.detect(mock_adapter=win_mock)

    assert report.collection_method == "MOCK_PLATFORM_ADAPTER"
    assert len(report.warnings) > 0
    assert "WINDOWS_11_X64" in report.warnings[0]
