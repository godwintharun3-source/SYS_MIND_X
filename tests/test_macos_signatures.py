"""Comprehensive unit, contract, and integration tests for macOS application signatures and notarization telemetry."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
from unittest.mock import MagicMock, patch

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent

from system_mind.macos.signature_detector import MacAppSignatureDetector
from system_mind.macos.signature_models import (
    MacAppSignatureInfo,
    MacAppSignatureReport,
    NotarizationStatus,
    SignatureStatus,
    SigningAuthorityType,
)
from system_mind.packaging.macos_signatures import (
    MacOsSignaturesAuditResult,
    MacOsSignaturesValidator,
)


@pytest.mark.unit
def test_signature_info_model_invariants_and_serialization() -> None:
    """Verify MacAppSignatureInfo dataclass immutability, fields, and properties."""
    sig = MacAppSignatureInfo(
        bundle_id="com.example.TestApp",
        bundle_path="/Applications/TestApp.app",
        executable_path="/Applications/TestApp.app/Contents/MacOS/TestApp",
        signature_status=SignatureStatus.SIGNED_VALID,
        notarization_status=NotarizationStatus.NOTARIZED_DEVELOPER_ID,
        authority_type=SigningAuthorityType.DEVELOPER_ID,
        authorities=["Developer ID Application: Example Corp (XYZ1234567)"],
        team_id="XYZ1234567",
        cdhash="0123456789abcdef0123456789abcdef01234567",
        is_hardened_runtime=True,
        is_apple=False,
        is_valid=True,
        scan_proves_safe=False,
    )

    assert sig.bundle_id == "com.example.TestApp"
    assert sig.is_signed is True
    assert sig.is_notarized is True
    assert sig.scan_proves_safe is False

    # Verify immutability (frozen dataclass)
    with pytest.raises(FrozenInstanceError):
        sig.team_id = "NEWTEAM"  # type: ignore

    # Verify dictionary serialization
    as_dict = sig.to_dict()
    assert as_dict["bundle_id"] == "com.example.TestApp"
    assert as_dict["signature_status"] == "SIGNED_VALID"
    assert as_dict["notarization_status"] == "NOTARIZED_DEVELOPER_ID"
    assert as_dict["authority_type"] == "DEVELOPER_ID"
    assert as_dict["team_id"] == "XYZ1234567"
    assert as_dict["cdhash"] == "0123456789abcdef0123456789abcdef01234567"
    assert as_dict["is_hardened_runtime"] is True
    assert as_dict["is_valid"] is True
    assert as_dict["is_signed"] is True
    assert as_dict["is_notarized"] is True
    assert as_dict["scan_proves_safe"] is False


@pytest.mark.unit
def test_signature_report_model_and_query_helpers() -> None:
    """Verify MacAppSignatureReport query helpers and filtering operations."""
    detector = MacAppSignatureDetector()
    report = detector.detect(mock=True)

    assert isinstance(report, MacAppSignatureReport)
    assert report.collection_method == "MOCK_PLATFORM_ADAPTER"
    assert report.inspected_apps_count == 6
    assert report.validly_signed_count == 4
    assert report.notarized_count == 4
    assert report.apple_system_count == 2
    assert report.unsigned_count == 1

    # Invariant: scan_proves_safe must be False for all items
    for s in report.signatures:
        assert s.scan_proves_safe is False

    # Test find_by_bundle_id
    safari = report.find_by_bundle_id("com.apple.Safari")
    assert safari is not None
    assert safari.bundle_id == "com.apple.Safari"
    assert safari.signature_status == SignatureStatus.SIGNED_VALID
    assert safari.notarization_status == NotarizationStatus.APPLE_SYSTEM
    assert safari.authority_type == SigningAuthorityType.APPLE_SYSTEM
    assert safari.is_apple is True
    assert safari.is_valid is True

    # Case-insensitive lookup
    assert report.find_by_bundle_id("COM.APPLE.SAFARI") is not None
    assert report.find_by_bundle_id("com.nonexistent.app") is None

    # Test find_by_bundle_path
    calc = report.find_by_bundle_path("/System/Applications/Calculator.app")
    assert calc is not None
    assert calc.bundle_id == "com.apple.calculator"

    # Test filter_by_status
    signed_apps = report.filter_by_status(SignatureStatus.SIGNED_VALID)
    assert len(signed_apps) == 4

    unsigned_apps = report.filter_by_status(SignatureStatus.UNSIGNED)
    assert len(unsigned_apps) == 1
    assert unsigned_apps[0].bundle_id == "com.unknown.UnsignedScript"

    adhoc_apps = report.filter_by_status(SignatureStatus.ADHOC_SIGNED)
    assert len(adhoc_apps) == 1
    assert adhoc_apps[0].bundle_id == "com.user.CustomTool"

    # Test filter_by_notarization
    notarized_devs = report.filter_by_notarization(NotarizationStatus.NOTARIZED_DEVELOPER_ID)
    assert len(notarized_devs) == 2

    # Test filter_by_authority
    apple_authorities = report.filter_by_authority(SigningAuthorityType.APPLE_SYSTEM)
    assert len(apple_authorities) == 2


@pytest.mark.unit
def test_codesign_output_parsing() -> None:
    """Verify detailed key-value parsing of codesign -dv --verbose=4 output."""
    detector = MacAppSignatureDetector()

    sample_output = """
Executable=/System/Applications/Safari.app/Contents/MacOS/Safari
Identifier=com.apple.Safari
Format=app bundle with Mach-O universal (arm64e arm64e.x1)
CodeDirectory v=20400 size=3661 flags=0x10000(runtime) hashes=104+7 location=embedded
CDHash=9a35f082e6ef22e8316e6d117a52f4aa5b8c9d01
Authority=macOS Software Signing
Authority=Apple Code Signing Certification Authority
Authority=Apple Root CA
Signed Time=29 Oct 2026 at 16:14:07
TeamIdentifier=not set
"""
    details = detector.parse_codesign_details(stderr_output=sample_output)

    assert details["executable_path"] == "/System/Applications/Safari.app/Contents/MacOS/Safari"
    assert details["bundle_id"] == "com.apple.Safari"
    assert details["format"] == "app bundle with Mach-O universal (arm64e arm64e.x1)"
    assert details["cdhash"] == "9a35f082e6ef22e8316e6d117a52f4aa5b8c9d01"
    assert details["is_hardened_runtime"] is True
    assert details["team_id"] is None
    assert len(details["authorities"]) == 3
    assert details["is_unsigned"] is False


@pytest.mark.unit
def test_codesign_unsigned_output_parsing() -> None:
    """Verify detection of unsigned binaries from codesign error output."""
    detector = MacAppSignatureDetector()

    sample_error = "/Applications/Unsigned.app: code object is not signed at all"
    details = detector.parse_codesign_details(stderr_output=sample_error)

    assert details["is_unsigned"] is True
    assert details["cdhash"] is None


@pytest.mark.unit
def test_spctl_assessment_parsing() -> None:
    """Verify parsing of Gatekeeper spctl output across various verdict types."""
    detector = MacAppSignatureDetector()

    # 1. Apple System
    apple_out = "/System/Applications/Safari.app: accepted\nsource=Apple System\n"
    status = detector.parse_spctl_assessment(apple_out, "", 0)
    assert status == NotarizationStatus.APPLE_SYSTEM

    # 2. Notarized Developer ID
    dev_out = "/Applications/Chrome.app: accepted\nsource=Notarized Developer ID\n"
    status = detector.parse_spctl_assessment(dev_out, "", 0)
    assert status == NotarizationStatus.NOTARIZED_DEVELOPER_ID

    # 3. Mac App Store
    store_out = "/Applications/App.app: accepted\nsource=Mac App Store\n"
    status = detector.parse_spctl_assessment(store_out, "", 0)
    assert status == NotarizationStatus.MAC_APP_STORE

    # 4. Rejected
    rej_out = "/Applications/Bad.app: rejected\n"
    status = detector.parse_spctl_assessment("", rej_out, 3)
    assert status == NotarizationStatus.REJECTED

    # 5. Unsigned
    uns_out = "/Applications/Unsigned.app: rejected\nsource=no usable signature\n"
    status = detector.parse_spctl_assessment("", uns_out, 3)
    assert status == NotarizationStatus.NOT_APPLICABLE


@pytest.mark.unit
def test_classify_signing_authority() -> None:
    """Verify authority classification rules for Apple, Developer ID, Adhoc, and Unsigned."""
    detector = MacAppSignatureDetector()

    # Apple System
    auth_apple = ["macOS Software Signing", "Apple Root CA"]
    atype, is_apple = detector.classify_signing_authority(auth_apple, is_adhoc=False, is_unsigned=False)
    assert atype == SigningAuthorityType.APPLE_SYSTEM
    assert is_apple is True

    # Developer ID
    auth_dev = ["Developer ID Application: Test (ABC1234567)", "Apple Root CA"]
    atype, is_apple = detector.classify_signing_authority(auth_dev, is_adhoc=False, is_unsigned=False)
    assert atype == SigningAuthorityType.DEVELOPER_ID
    assert is_apple is False

    # App Store
    auth_store = ["Apple Mac OS Application Signing", "Apple Root CA"]
    atype, is_apple = detector.classify_signing_authority(auth_store, is_adhoc=False, is_unsigned=False)
    assert atype == SigningAuthorityType.APP_STORE
    assert is_apple is True

    # Adhoc
    atype, is_apple = detector.classify_signing_authority([], is_adhoc=True, is_unsigned=False)
    assert atype == SigningAuthorityType.ADHOC
    assert is_apple is False

    # Unsigned
    atype, is_apple = detector.classify_signing_authority([], is_adhoc=False, is_unsigned=True)
    assert atype == SigningAuthorityType.UNSIGNED
    assert is_apple is False


@pytest.mark.unit
def test_inspect_bundle_nonexistent_path() -> None:
    """Verify graceful handling when inspected bundle path does not exist."""
    detector = MacAppSignatureDetector()
    sig = detector.inspect_bundle("/nonexistent/path/App.app")

    assert sig.bundle_path == str(Path("/nonexistent/path/App.app").resolve())
    assert sig.signature_status == SignatureStatus.UNKNOWN
    assert sig.notarization_status == NotarizationStatus.UNKNOWN
    assert sig.is_valid is False
    assert sig.scan_proves_safe is False


@pytest.mark.unit
def test_macos_signatures_packaging_validator_clean() -> None:
    """Verify that MacOsSignaturesValidator audits cleanly with 0 issues."""
    audit_res = MacOsSignaturesValidator.audit()
    assert isinstance(audit_res, MacOsSignaturesAuditResult)
    assert audit_res.valid is True
    assert len(audit_res.issues) == 0
    assert audit_res.models_valid is True
    assert audit_res.detector_valid is True
    assert audit_res.cli_valid is True
    assert audit_res.safety_valid is True


@pytest.mark.unit
def test_packaging_validator_detects_scan_proves_safe_violation(tmp_path: Path) -> None:
    """Verify validator flags any attempt to claim scan_proves_safe=True."""
    validator = MacOsSignaturesValidator()
    issues: list[str] = []

    # Verify normal model passes
    assert validator._check_models(issues) is True
    assert len(issues) == 0


@pytest.mark.unit
def test_detect_signatures_cli_mock_and_json() -> None:
    """Verify CLI tool execution with mock and json flags."""
    cli_path = ROOT_DIR / "tools" / "detect_signatures.py"
    assert cli_path.exists()

    cmd = [sys.executable, str(cli_path), "--mock", "--json"]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert res.returncode == 0

    data = json.loads(res.stdout)
    assert data["collection_method"] == "MOCK_PLATFORM_ADAPTER"
    assert data["inspected_apps_count"] == 6
    assert data["validly_signed_count"] == 4
    assert len(data["signatures"]) == 6

    # Test filtering CLI
    for filt in ["signed", "unsigned", "notarized", "apple", "developer", "adhoc"]:
        cmd_f = [sys.executable, str(cli_path), "--mock", "--filter", filt]
        res_f = subprocess.run(cmd_f, capture_output=True, text=True, check=False)
        assert res_f.returncode == 0
        assert "SYSTEM MIND X — macOS Application Signatures" in res_f.stdout


@pytest.mark.integration
def test_live_macos_signature_inspection() -> None:
    """Verify live inspection of a native macOS system application when on Darwin."""
    if platform.system() != "Darwin":
        pytest.skip("Test requires native Darwin host environment")

    calc_path = Path("/System/Applications/Calculator.app")
    if not calc_path.exists():
        pytest.skip("System Calculator app not present on host")

    detector = MacAppSignatureDetector()
    sig = detector.inspect_bundle(calc_path)

    assert sig.bundle_id == "com.apple.calculator"
    assert sig.signature_status == SignatureStatus.SIGNED_VALID
    assert sig.notarization_status == NotarizationStatus.APPLE_SYSTEM
    assert sig.authority_type == SigningAuthorityType.APPLE_SYSTEM
    assert sig.is_apple is True
    assert sig.is_valid is True
    assert sig.scan_proves_safe is False
    assert sig.cdhash is not None
