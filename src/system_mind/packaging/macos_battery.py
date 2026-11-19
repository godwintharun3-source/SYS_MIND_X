"""Automated packaging validator auditing macOS battery state, power sources, and health telemetry."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent

from system_mind.macos.battery_detector import MacBatteryDetector
from system_mind.macos.battery_models import (
    BatteryChargingState,
    BatteryHealthCondition,
    MacBatteryHealthInfo,
    MacBatteryTelemetryReport,
    PowerSource,
)
from system_mind.platform.adapter import MockPlatformProfileFactory


@dataclass(frozen=True)
class MacOsBatteryAuditResult:
    """Outcome of auditing macOS companion agent battery telemetry engine and CLI tooling."""

    valid: bool
    issues: tuple[str, ...]
    models_valid: bool
    detector_valid: bool
    cli_valid: bool
    privacy_valid: bool


class MacOsBatteryValidator:
    """Programmatic validator verifying macOS battery data models, privacy rules, and CLI tools."""

    CLI_REL_PATH = Path("tools") / "detect_battery.py"

    REQUIRED_REPORT_FIELDS = [
        "is_battery_present",
        "current_power_source",
        "state_of_charge_percent",
        "charging_state",
        "is_charging",
        "is_fully_charged",
        "is_ac_connected",
        "time_remaining_minutes",
        "is_below_warning_level",
        "is_low_power_mode_active",
        "health",
        "collected_at_epoch_secs",
        "collection_method",
        "unavailable_telemetry",
        "warnings",
    ]

    REQUIRED_HEALTH_FIELDS = [
        "cycle_count",
        "condition",
        "maximum_capacity_percent",
        "device_name",
        "manufacturer",
        "anonymized_serial_hash",
        "firmware_version",
    ]

    def __init__(self, root_dir: Optional[Path] = None) -> None:
        self.root_dir = root_dir or ROOT_DIR
        self.cli_path = self.root_dir / self.CLI_REL_PATH

    @classmethod
    def audit(cls, root_dir: Optional[Path] = None) -> MacOsBatteryAuditResult:
        """Execute comprehensive audit over macOS battery telemetry components."""
        instance = cls(root_dir)
        return instance._audit_internal()

    def _audit_internal(self) -> MacOsBatteryAuditResult:
        issues: List[str] = []

        models_valid = self._audit_models(issues)
        detector_valid, privacy_valid = self._audit_detector(issues)
        cli_valid = self._audit_cli(issues)

        valid = models_valid and detector_valid and cli_valid and privacy_valid
        return MacOsBatteryAuditResult(
            valid=valid,
            issues=tuple(issues),
            models_valid=models_valid,
            detector_valid=detector_valid,
            cli_valid=cli_valid,
            privacy_valid=privacy_valid,
        )

    def _audit_models(self, issues: List[str]) -> bool:
        """Verify dataclasses and required fields are defined with proper typing."""
        valid = True

        for req_field in self.REQUIRED_REPORT_FIELDS:
            if not hasattr(MacBatteryTelemetryReport, "__dataclass_fields__") or (
                req_field not in MacBatteryTelemetryReport.__dataclass_fields__
            ):
                issues.append(f"MacBatteryTelemetryReport missing required field: {req_field}")
                valid = False

        for req_field in self.REQUIRED_HEALTH_FIELDS:
            if not hasattr(MacBatteryHealthInfo, "__dataclass_fields__") or (
                req_field not in MacBatteryHealthInfo.__dataclass_fields__
            ):
                issues.append(f"MacBatteryHealthInfo missing required field: {req_field}")
                valid = False

        return valid

    def _audit_detector(self, issues: List[str]) -> tuple[bool, bool]:
        """Verify detector runs under mock profile and enforces privacy rules."""
        det_valid = True
        privacy_valid = True

        try:
            detector = MacBatteryDetector()
            mock = MockPlatformProfileFactory.create_macos_apple_silicon_mock()
            report = detector.detect(use_mock=True, mock_adapter=mock)

            if not isinstance(report, MacBatteryTelemetryReport):
                issues.append("MacBatteryDetector.detect(use_mock=True) did not return MacBatteryTelemetryReport")
                det_valid = False

            if not report.is_battery_present:
                issues.append("Expected is_battery_present=True under Apple Silicon mock")
                det_valid = False

            if report.health is None:
                issues.append("Expected non-None health object under Apple Silicon mock")
                det_valid = False
            else:
                serial_hash = report.health.anonymized_serial_hash
                if not serial_hash or not re.match(r"^sha256:[a-f0-9]{16}$", serial_hash):
                    issues.append(f"Battery serial hash does not match sha256:16hex format: {serial_hash}")
                    privacy_valid = False

            # Test serial anonymization directly
            raw_test_serial = "F5D348718UYPJYVAL"
            anon_digest = detector.anonymize_serial(raw_test_serial)
            if raw_test_serial in str(anon_digest) or not str(anon_digest).startswith("sha256:"):
                issues.append("anonymize_serial failed to safely scrub raw serial number")
                privacy_valid = False

        except Exception as exc:
            issues.append(f"Detector audit exception: {exc}")
            det_valid = False
            privacy_valid = False

        return det_valid, privacy_valid

    def _audit_cli(self, issues: List[str]) -> bool:
        """Verify CLI script exists, is executable, and produces valid output."""
        if not self.cli_path.exists():
            issues.append(f"Battery CLI missing at path: {self.cli_path}")
            return False

        try:
            cmd = [sys.executable, str(self.cli_path), "--mock", "--json"]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15.0, check=False)
            if proc.returncode != 0:
                issues.append(f"Battery CLI returned non-zero exit code {proc.returncode}: {proc.stderr}")
                return False

            data = json.loads(proc.stdout)
            if not data.get("is_battery_present", False):
                issues.append("Battery CLI JSON missing expected is_battery_present=True")
                return False
            if "health" not in data or data["health"] is None:
                issues.append("Battery CLI JSON missing expected health dictionary")
                return False

            return True
        except Exception as exc:
            issues.append(f"Failed to execute Battery CLI: {exc}")
            return False
