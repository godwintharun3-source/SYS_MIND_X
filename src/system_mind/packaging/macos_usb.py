"""Automated packaging validator auditing macOS USB and peripheral inventory telemetry."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent

from system_mind.macos.usb_detector import MacUsbDetector
from system_mind.macos.usb_models import (
    MacUsbController,
    MacUsbDevice,
    MacUsbReport,
    UsbDeviceClass,
    UsbSpeed,
)
from system_mind.platform.adapter import MockPlatformProfileFactory


@dataclass(frozen=True)
class MacOsUsbAuditResult:
    """Outcome of auditing macOS companion agent USB telemetry engine and CLI tooling."""

    valid: bool
    issues: tuple[str, ...]
    models_valid: bool
    detector_valid: bool
    cli_valid: bool
    privacy_valid: bool


class MacOsUsbValidator:
    """Programmatic validator verifying macOS USB data models, privacy rules, and CLI tools."""

    CLI_REL_PATH = Path("tools") / "detect_usb.py"

    REQUIRED_REPORT_FIELDS = [
        "controllers",
        "total_controller_count",
        "total_device_count",
        "has_external_devices",
        "has_security_tokens",
        "has_mass_storage",
        "collected_at_epoch_secs",
        "collection_method",
        "unavailable_telemetry",
        "warnings",
    ]

    REQUIRED_CONTROLLER_FIELDS = [
        "name",
        "host_controller",
        "pci_device",
        "pci_vendor",
        "devices",
    ]

    REQUIRED_DEVICE_FIELDS = [
        "name",
        "vendor_id",
        "product_id",
        "manufacturer",
        "anonymized_serial_hash",
        "device_class",
        "speed",
        "speed_text",
        "location_id",
        "bus_power_ma",
        "current_used_ma",
        "extra_current_ma",
        "bcd_device",
        "is_builtin",
        "is_hub",
        "children",
    ]

    def __init__(self, root_dir: Optional[Path] = None) -> None:
        self.root_dir = root_dir or ROOT_DIR
        self.cli_path = self.root_dir / self.CLI_REL_PATH

    @classmethod
    def audit(cls, root_dir: Optional[Path] = None) -> MacOsUsbAuditResult:
        """Execute comprehensive audit over macOS USB telemetry components."""
        instance = cls(root_dir)
        return instance._audit_internal()

    def _audit_internal(self) -> MacOsUsbAuditResult:
        issues: List[str] = []

        models_valid = self._audit_models(issues)
        detector_valid, privacy_valid = self._audit_detector(issues)
        cli_valid = self._audit_cli(issues)

        valid = models_valid and detector_valid and cli_valid and privacy_valid
        return MacOsUsbAuditResult(
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
            device = MacUsbDevice(
                name="Test Peripheral",
                vendor_id="0x05ac",
                product_id="0x027c",
                manufacturer="Apple Inc.",
                anonymized_serial_hash="sha256:0123456789abcdef",
                device_class=UsbDeviceClass.HUMAN_INTERFACE,
                speed=UsbSpeed.FULL_SPEED_12_MBPS,
                speed_text="up_to_12_mbit_s",
                location_id="0x01100000 / 1",
                bus_power_ma=500,
                current_used_ma=40,
                extra_current_ma=0,
                bcd_device="1.00",
                is_builtin=True,
                is_hub=False,
                children=[],
            )

            for field_name in self.REQUIRED_DEVICE_FIELDS:
                if not hasattr(device, field_name):
                    issues.append(f"MacUsbDevice missing required field: {field_name}")
                    passed = False

            controller = MacUsbController(
                name="USB 3.1 Bus",
                host_controller="AppleSynopsysUSB40XHCI",
                pci_device="0x0000",
                pci_vendor="0x106b",
                devices=[device],
            )

            for field_name in self.REQUIRED_CONTROLLER_FIELDS:
                if not hasattr(controller, field_name):
                    issues.append(f"MacUsbController missing required field: {field_name}")
                    passed = False

            report = MacUsbReport(
                controllers=[controller],
                total_controller_count=1,
                total_device_count=1,
                has_external_devices=False,
                has_security_tokens=False,
                has_mass_storage=False,
            )

            for field_name in self.REQUIRED_REPORT_FIELDS:
                if not hasattr(report, field_name):
                    issues.append(f"MacUsbReport missing required field: {field_name}")
                    passed = False

        except Exception as exc:
            issues.append(f"Model instantiation failure: {exc}")
            passed = False

        return passed

    def _audit_detector(self, issues: List[str]) -> tuple[bool, bool]:
        detector_passed = True
        privacy_passed = True

        try:
            detector = MacUsbDetector()
            mock = MockPlatformProfileFactory.create_macos_apple_silicon_mock()
            report = detector.detect(use_mock=True, mock_adapter=mock)

            if not report.controllers:
                issues.append("Mock USB report returned zero controllers")
                detector_passed = False

            if report.collection_method != "MOCK_PLATFORM_ADAPTER":
                issues.append(f"Unexpected collection method for mock: {report.collection_method}")
                detector_passed = False

            # Privacy audit: verify peripheral serial anonymization (INV-USB-02)
            all_devices = []
            for ctrl in report.controllers:
                all_devices.extend(detector.flatten_devices(ctrl.devices))

            for dev in all_devices:
                serial_hash = dev.anonymized_serial_hash
                if serial_hash:
                    if not serial_hash.startswith("sha256:"):
                        issues.append(f"Peripheral serial hash '{serial_hash}' missing sha256: prefix")
                        privacy_passed = False
                    hex_part = serial_hash[7:]
                    if len(hex_part) != 16 or not re.fullmatch(r"[0-9a-f]{16}", hex_part):
                        issues.append(f"Peripheral serial hash '{serial_hash}' is not a valid 16-hex char digest")
                        privacy_passed = False

            # Test anonymize_serial directly
            sample_serial = "FE0123456789"
            anon = detector.anonymize_serial(sample_serial)
            if not anon or not anon.startswith("sha256:") or len(anon) != 23:
                issues.append(f"anonymize_serial output '{anon}' does not meet INV-USB-02 requirements")
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

            if not data.get("controllers"):
                issues.append("CLI JSON returned empty controllers list")
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
