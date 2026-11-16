"""Automated packaging validator auditing macOS GPU and display inventory telemetry."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent

from system_mind.macos.gpu_detector import MacGpuDetector
from system_mind.macos.gpu_models import (
    DisplayConnectionType,
    GpuBusType,
    MacDisplayInfo,
    MacGpuInfo,
    MacGpuReport,
)
from system_mind.platform.adapter import MockPlatformProfileFactory


@dataclass(frozen=True)
class MacOsGpuAuditResult:
    """Outcome of auditing macOS companion agent GPU telemetry engine and CLI tooling."""

    valid: bool
    issues: tuple[str, ...]
    models_valid: bool
    detector_valid: bool
    cli_valid: bool
    privacy_valid: bool


class MacOsGpuValidator:
    """Programmatic validator verifying macOS GPU and display data models, privacy rules, and CLI tools."""

    CLI_REL_PATH = Path("tools") / "detect_gpu.py"

    REQUIRED_REPORT_FIELDS = [
        "gpus",
        "total_gpu_count",
        "total_display_count",
        "primary_display_resolution",
        "has_builtin_display",
        "has_external_display",
        "collected_at_epoch_secs",
        "collection_method",
        "unavailable_telemetry",
        "warnings",
    ]

    REQUIRED_GPU_FIELDS = [
        "name",
        "vendor",
        "core_count",
        "bus_type",
        "metal_support",
        "device_type",
        "vram_bytes",
        "vram_text",
        "displays",
    ]

    REQUIRED_DISPLAY_FIELDS = [
        "name",
        "display_id",
        "vendor_id",
        "product_id",
        "anonymized_serial_hash",
        "native_pixels",
        "resolution",
        "ui_resolution",
        "refresh_rate_hz",
        "is_main",
        "is_builtin",
        "is_online",
        "is_mirror",
        "connection_type",
        "pixel_density_retina",
        "ambient_brightness",
    ]

    def __init__(self, root_dir: Optional[Path] = None) -> None:
        self.root_dir = root_dir or ROOT_DIR
        self.cli_path = self.root_dir / self.CLI_REL_PATH

    @classmethod
    def audit(cls, root_dir: Optional[Path] = None) -> MacOsGpuAuditResult:
        """Execute comprehensive audit over macOS GPU telemetry components."""
        instance = cls(root_dir)
        return instance._audit_internal()

    def _audit_internal(self) -> MacOsGpuAuditResult:
        issues: List[str] = []

        models_valid = self._audit_models(issues)
        detector_valid, privacy_valid = self._audit_detector(issues)
        cli_valid = self._audit_cli(issues)

        valid = models_valid and detector_valid and cli_valid and privacy_valid
        return MacOsGpuAuditResult(
            valid=valid,
            issues=tuple(issues),
            models_valid=models_valid,
            detector_valid=detector_valid,
            cli_valid=cli_valid,
            privacy_valid=privacy_valid,
        )

    def _audit_models(self, issues: List[str]) -> bool:
        passed = True
        try:
            display = MacDisplayInfo(
                name="Test Display",
                display_id="1",
                vendor_id="610",
                product_id="a045",
                anonymized_serial_hash="sha256:0123456789abcdef",
                native_pixels="2880 x 1800",
                resolution="1440 x 900 @ 60.00Hz",
                ui_resolution="1440 x 900",
                refresh_rate_hz=60.0,
                is_main=True,
                is_builtin=True,
                is_online=True,
                is_mirror=False,
                connection_type=DisplayConnectionType.INTERNAL,
                pixel_density_retina=True,
                ambient_brightness=True,
            )

            for field_name in self.REQUIRED_DISPLAY_FIELDS:
                if not hasattr(display, field_name):
                    issues.append(f"MacDisplayInfo missing required field: {field_name}")
                    passed = False

            gpu = MacGpuInfo(
                name="Apple M1",
                vendor="Apple",
                core_count=8,
                bus_type=GpuBusType.BUILTIN,
                metal_support="spdisplays_metal4",
                device_type="spdisplays_gpu",
                vram_text="Unified Memory",
                displays=[display],
            )

            for field_name in self.REQUIRED_GPU_FIELDS:
                if not hasattr(gpu, field_name):
                    issues.append(f"MacGpuInfo missing required field: {field_name}")
                    passed = False

            report = MacGpuReport(
                gpus=[gpu],
                total_gpu_count=1,
                total_display_count=1,
                primary_display_resolution="1440 x 900 @ 60.00Hz",
                has_builtin_display=True,
                has_external_display=False,
            )

            for field_name in self.REQUIRED_REPORT_FIELDS:
                if not hasattr(report, field_name):
                    issues.append(f"MacGpuReport missing required field: {field_name}")
                    passed = False

        except Exception as exc:
            issues.append(f"Model instantiation failure: {exc}")
            passed = False

        return passed

    def _audit_detector(self, issues: List[str]) -> tuple[bool, bool]:
        detector_passed = True
        privacy_passed = True

        try:
            detector = MacGpuDetector()
            mock = MockPlatformProfileFactory.create_macos_apple_silicon_mock()
            report = detector.detect(use_mock=True, mock_adapter=mock)

            if not report.gpus:
                issues.append("Mock GPU report returned zero GPUs")
                detector_passed = False

            if report.collection_method != "MOCK_PLATFORM_ADAPTER":
                issues.append(f"Unexpected collection method for mock: {report.collection_method}")
                detector_passed = False

            # Privacy audit: verify display serial anonymization (INV-GPU-02)
            for gpu in report.gpus:
                for display in gpu.displays:
                    serial_hash = display.anonymized_serial_hash
                    if serial_hash:
                        if not serial_hash.startswith("sha256:"):
                            issues.append(f"Display serial hash '{serial_hash}' missing sha256: prefix")
                            privacy_passed = False
                        hex_part = serial_hash[7:]
                        if len(hex_part) != 16 or not re.fullmatch(r"[0-9a-f]{16}", hex_part):
                            issues.append(f"Display serial hash '{serial_hash}' is not a valid 16-hex char digest")
                            privacy_passed = False

            # Test anonymize_serial directly
            sample_serial = "fd626d62"
            anon = detector.anonymize_serial(sample_serial)
            if not anon or not anon.startswith("sha256:") or len(anon) != 23:
                issues.append(f"anonymize_serial output '{anon}' does not meet INV-GPU-02 requirements")
                privacy_passed = False

        except Exception as exc:
            issues.append(f"Detector audit failure: {exc}")
            detector_passed = False
            privacy_passed = False

        return detector_passed, privacy_passed

    def _audit_cli(self, issues: List[str]) -> bool:
        if not self.cli_path.is_file():
            issues.append(f"CLI tool missing at expected location: {self.cli_path}")
            return False

        try:
            proc = subprocess.run(
                [sys.executable, str(self.cli_path), "--mock", "--json"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if proc.returncode != 0:
                issues.append(f"CLI exited with non-zero code {proc.returncode}: {proc.stderr}")
                return False

            data = json.loads(proc.stdout)
            for field_name in self.REQUIRED_REPORT_FIELDS:
                if field_name not in data:
                    issues.append(f"CLI JSON output missing key: {field_name}")
                    return False

            if not data.get("gpus"):
                issues.append("CLI JSON returned empty gpus list")
                return False

            return True

        except subprocess.TimeoutExpired:
            issues.append("CLI invocation timed out after 5s")
            return False
        except json.JSONDecodeError as exc:
            issues.append(f"CLI did not return valid JSON: {exc}")
            return False
        except Exception as exc:
            issues.append(f"CLI audit failure: {exc}")
            return False
