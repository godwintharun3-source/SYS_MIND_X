"""Automated packaging validator auditing macOS telemetry models and detection engine."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
from typing import List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent

from system_mind.macos.detector import MacOSIdentityDetector
from system_mind.macos.models import (
    MacArchitecture,
    MacHostIdentity,
    MacOSVersionInfo,
    MacTelemetryReport,
)
from system_mind.platform.adapter import MockPlatformProfileFactory


@dataclass(frozen=True)
class MacOsTelemetryAuditResult:
    """Outcome of auditing macOS companion agent telemetry engine and CLI tooling."""

    valid: bool
    issues: tuple[str, ...]
    models_valid: bool
    detector_valid: bool
    cli_valid: bool
    privacy_anonymization_valid: bool


class MacOsTelemetryValidator:
    """Programmatic validator verifying macOS telemetry data models, privacy hashing, and CLI tools."""

    CLI_REL_PATH = Path("tools") / "detect_macos.py"

    REQUIRED_VERSION_FIELDS = [
        "product_name",
        "product_version",
        "major_version",
        "minor_version",
        "patch_version",
        "build_version",
        "darwin_kernel_release",
        "marketing_name",
    ]

    REQUIRED_ARCH_FIELDS = [
        "machine",
        "is_apple_silicon",
        "byte_order",
        "pointer_size_bits",
        "is_rosetta_translated",
    ]

    REQUIRED_IDENTITY_FIELDS = [
        "hostname",
        "computer_name",
        "local_host_name",
        "platform_uuid",
        "anonymized_serial_hash",
        "is_virtual_machine",
    ]

    @classmethod
    def audit(cls, root_dir: Optional[Path] = None) -> MacOsTelemetryAuditResult:
        """Executes full audit across data models, detection logic, privacy protection, and CLI."""
        base_dir = root_dir or ROOT_DIR
        issues: List[str] = []
        models_ok = True
        detector_ok = True
        cli_ok = True
        privacy_ok = True

        # 1. Audit Data Model Fields
        for f in cls.REQUIRED_VERSION_FIELDS:
            if f not in MacOSVersionInfo.__annotations__:
                issues.append(f"MacOSVersionInfo missing required annotation: {f}")
                models_ok = False
        for f in cls.REQUIRED_ARCH_FIELDS:
            if f not in MacArchitecture.__annotations__:
                issues.append(f"MacArchitecture missing required annotation: {f}")
                models_ok = False
        for f in cls.REQUIRED_IDENTITY_FIELDS:
            if f not in MacHostIdentity.__annotations__:
                issues.append(f"MacHostIdentity missing required annotation: {f}")
                models_ok = False

        # 2. Audit Marketing Name Resolution
        test_mappings = [
            (15, 0, "Sequoia"),
            (14, 0, "Sonoma"),
            (13, 0, "Ventura"),
            (12, 0, "Monterey"),
            (11, 0, "Big Sur"),
        ]
        for maj, min_v, expected in test_mappings:
            resolved = MacOSIdentityDetector.resolve_marketing_name(maj, min_v)
            if resolved != expected:
                issues.append(
                    f"Marketing name resolution drift: version {maj}.{min_v} returned '{resolved}', expected '{expected}'"
                )
                detector_ok = False

        # 3. Audit Mock Detection & Privacy Anonymization
        try:
            mock = MockPlatformProfileFactory.create_macos_apple_silicon_mock()
            report = MacOSIdentityDetector.detect(mock_adapter=mock)

            if not isinstance(report, MacTelemetryReport):
                issues.append("Detector did not return MacTelemetryReport")
                detector_ok = False

            if not report.architecture.is_apple_silicon:
                issues.append("Mock Apple Silicon profile failed is_apple_silicon check")
                detector_ok = False

            serial_hash = report.identity.anonymized_serial_hash
            if not serial_hash or not serial_hash.startswith("sha256:"):
                issues.append(f"Privacy invariant violation: invalid anonymized_serial_hash: {serial_hash}")
                privacy_ok = False
        except Exception as exc:
            issues.append(f"Error during mock macOS detection: {exc}")
            detector_ok = False

        # 4. Audit CLI Tool
        cli_path = base_dir / cls.CLI_REL_PATH
        if not cli_path.exists():
            issues.append(f"Missing developer CLI tool: {cls.CLI_REL_PATH}")
            cli_ok = False
        else:
            try:
                proc = subprocess.run(
                    [sys.executable, str(cli_path), "--mock", "--json"],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=20,
                    cwd=str(base_dir),
                )
                if proc.returncode != 0:
                    issues.append(f"detect_macos.py failed with code {proc.returncode}: {proc.stderr}")
                    cli_ok = False
                else:
                    data = json.loads(proc.stdout)
                    if "version_info" not in data or "architecture" not in data:
                        issues.append("detect_macos.py output missing required telemetry keys")
                        cli_ok = False
            except Exception as exc:
                issues.append(f"Failed running detect_macos.py: {exc}")
                cli_ok = False

        overall_valid = models_ok and detector_ok and cli_ok and privacy_ok and (len(issues) == 0)
        return MacOsTelemetryAuditResult(
            valid=overall_valid,
            issues=tuple(issues),
            models_valid=models_ok,
            detector_valid=detector_ok,
            cli_valid=cli_ok,
            privacy_anonymization_valid=privacy_ok,
        )
