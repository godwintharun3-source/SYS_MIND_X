"""Automated packaging validator auditing macOS network interfaces, routing, and connectivity telemetry."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent

from system_mind.macos.network_detector import MacNetworkDetector
from system_mind.macos.network_models import (
    InterfaceType,
    LinkState,
    MacIpAddress,
    MacNetworkInterface,
    MacNetworkReport,
    MacNetworkRoute,
)
from system_mind.platform.adapter import MockPlatformProfileFactory


@dataclass(frozen=True)
class MacOsNetworkAuditResult:
    """Outcome of auditing macOS companion agent network telemetry engine and CLI tooling."""

    valid: bool
    issues: tuple[str, ...]
    models_valid: bool
    detector_valid: bool
    cli_valid: bool
    privacy_valid: bool


class MacOsNetworkValidator:
    """Programmatic validator verifying macOS network data models, privacy rules, and CLI tools."""

    CLI_REL_PATH = Path("tools") / "detect_network.py"

    REQUIRED_REPORT_FIELDS = [
        "interfaces",
        "primary_interface_name",
        "is_online",
        "default_gateway",
        "dns_servers",
        "search_domains",
        "collected_at_epoch_secs",
        "collection_method",
        "unavailable_telemetry",
        "warnings",
    ]

    REQUIRED_INTERFACE_FIELDS = [
        "name",
        "hardware_port",
        "interface_type",
        "link_state",
        "mtu",
        "mac_address",
        "anonymized_mac_hash",
        "ip_addresses",
        "flags",
        "is_primary",
        "media",
    ]

    REQUIRED_IP_FIELDS = [
        "address",
        "family",
        "netmask",
        "broadcast",
        "prefixlen",
        "scope",
        "is_loopback",
    ]

    def __init__(self, root_dir: Optional[Path] = None) -> None:
        self.root_dir = root_dir or ROOT_DIR
        self.cli_path = self.root_dir / self.CLI_REL_PATH

    @classmethod
    def audit(cls, root_dir: Optional[Path] = None) -> MacOsNetworkAuditResult:
        """Execute comprehensive audit over macOS network telemetry components."""
        instance = cls(root_dir)
        return instance._audit_internal()

    def _audit_internal(self) -> MacOsNetworkAuditResult:
        issues: List[str] = []

        models_valid = self._audit_models(issues)
        detector_valid, privacy_valid = self._audit_detector(issues)
        cli_valid = self._audit_cli(issues)

        valid = models_valid and detector_valid and cli_valid and privacy_valid
        return MacOsNetworkAuditResult(
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
            if not hasattr(MacNetworkReport, "__dataclass_fields__") or (
                req_field not in MacNetworkReport.__dataclass_fields__
            ):
                issues.append(f"MacNetworkReport missing required field: {req_field}")
                valid = False

        for req_field in self.REQUIRED_INTERFACE_FIELDS:
            if not hasattr(MacNetworkInterface, "__dataclass_fields__") or (
                req_field not in MacNetworkInterface.__dataclass_fields__
            ):
                issues.append(f"MacNetworkInterface missing required field: {req_field}")
                valid = False

        for req_field in self.REQUIRED_IP_FIELDS:
            if not hasattr(MacIpAddress, "__dataclass_fields__") or (
                req_field not in MacIpAddress.__dataclass_fields__
            ):
                issues.append(f"MacIpAddress missing required field: {req_field}")
                valid = False

        return valid

    def _audit_detector(self, issues: List[str]) -> tuple[bool, bool]:
        """Verify detector runs under mock profile and enforces privacy rules."""
        det_valid = True
        privacy_valid = True

        try:
            detector = MacNetworkDetector()
            mock = MockPlatformProfileFactory.create_macos_apple_silicon_mock()
            report = detector.detect(use_mock=True, mock_adapter=mock)

            if not isinstance(report, MacNetworkReport):
                issues.append("MacNetworkDetector.detect(use_mock=True) did not return MacNetworkReport")
                det_valid = False

            if not report.interfaces:
                issues.append("Expected non-empty interfaces list under mock adapter")
                det_valid = False

            # Verify MAC anonymization
            wifi_found = False
            for iface in report.interfaces:
                if iface.interface_type == InterfaceType.WIFI:
                    wifi_found = True
                    mac_hash = iface.anonymized_mac_hash
                    if not mac_hash or not re.match(r"^sha256:[a-f0-9]{16}$", mac_hash):
                        issues.append(f"Wi-Fi MAC hash does not match sha256:16hex format: {mac_hash}")
                        privacy_valid = False

            if not wifi_found:
                issues.append("Expected Wi-Fi interface in mock report")
                det_valid = False

            # Direct test on anonymize_mac
            raw_test_mac = "ca:01:8c:90:8c:35"
            anon_digest = detector.anonymize_mac(raw_test_mac)
            if not anon_digest or not anon_digest.startswith("sha256:") or raw_test_mac in anon_digest:
                issues.append("anonymize_mac failed to safely hash raw MAC address")
                privacy_valid = False

        except Exception as exc:
            issues.append(f"Detector audit exception: {exc}")
            det_valid = False
            privacy_valid = False

        return det_valid, privacy_valid

    def _audit_cli(self, issues: List[str]) -> bool:
        """Verify CLI script exists, is executable, and produces valid output."""
        if not self.cli_path.exists():
            issues.append(f"Network CLI missing at path: {self.cli_path}")
            return False

        try:
            cmd = [sys.executable, str(self.cli_path), "--mock", "--json"]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5.0, check=False)
            if proc.returncode != 0:
                issues.append(f"Network CLI returned non-zero exit code {proc.returncode}: {proc.stderr}")
                return False

            data = json.loads(proc.stdout)
            if "interfaces" not in data or not isinstance(data["interfaces"], list):
                issues.append("Network CLI JSON missing expected interfaces list")
                return False
            if "primary_interface_name" not in data:
                issues.append("Network CLI JSON missing expected primary_interface_name key")
                return False

            return True
        except Exception as exc:
            issues.append(f"Failed to execute Network CLI: {exc}")
            return False
