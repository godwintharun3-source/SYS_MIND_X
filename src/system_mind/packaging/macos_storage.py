"""Automated packaging validator auditing macOS storage volumes, APFS, and filesystem telemetry."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
from typing import List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent

from system_mind.macos.storage_detector import MacStorageDetector
from system_mind.macos.storage_models import (
    FilesystemType,
    MacStorageReport,
    MacVolumeInfo,
    VolumeRole,
)
from system_mind.platform.adapter import MockPlatformProfileFactory


@dataclass(frozen=True)
class MacOsStorageAuditResult:
    """Outcome of auditing macOS companion agent storage telemetry engine and CLI tooling."""

    valid: bool
    issues: tuple[str, ...]
    models_valid: bool
    detector_valid: bool
    cli_valid: bool
    apfs_ssv_valid: bool


class MacOsStorageValidator:
    """Programmatic validator verifying macOS storage data models, APFS rules, and CLI tools."""

    CLI_REL_PATH = Path("tools") / "detect_storage.py"

    REQUIRED_VOLUME_FIELDS = [
        "device_node",
        "device_identifier",
        "mount_point",
        "volume_name",
        "filesystem_type",
        "volume_role",
        "total_capacity_bytes",
        "used_bytes",
        "available_bytes",
        "used_percent",
        "is_read_only",
        "is_sealed_system_volume",
        "is_filevault_encrypted",
        "is_internal",
        "is_solid_state",
        "volume_uuid",
        "apfs_container_id",
        "mount_flags",
    ]

    REQUIRED_REPORT_FIELDS = [
        "volumes",
        "primary_system_volume",
        "primary_data_volume",
        "total_internal_capacity_bytes",
        "total_internal_available_bytes",
        "has_filevault_active",
        "has_sealed_system_volume",
        "collected_at_epoch_secs",
        "collection_method",
        "unavailable_telemetry",
        "warnings",
    ]

    @classmethod
    def audit(cls, root_dir: Optional[Path] = None) -> MacOsStorageAuditResult:
        """Executes full audit across storage models, APFS SSV rules, and CLI."""
        base_dir = root_dir or ROOT_DIR
        issues: List[str] = []
        models_ok = True
        detector_ok = True
        cli_ok = True
        ssv_ok = True

        # 1. Audit Data Model Fields
        for f in cls.REQUIRED_VOLUME_FIELDS:
            if f not in MacVolumeInfo.__dataclass_fields__:
                issues.append(f"MacVolumeInfo missing required field: '{f}'")
                models_ok = False

        for f in cls.REQUIRED_REPORT_FIELDS:
            if f not in MacStorageReport.__dataclass_fields__:
                issues.append(f"MacStorageReport missing required field: '{f}'")
                models_ok = False

        # 2. Audit Mock Platform Detection & APFS SSV Rules
        try:
            mock = MockPlatformProfileFactory.create_macos_apple_silicon_mock()
            report = MacStorageDetector.detect(mock_adapter=mock)

            if not isinstance(report, MacStorageReport):
                issues.append("MacStorageDetector.detect() did not return a MacStorageReport instance")
                detector_ok = False

            if report.collection_method != "MOCK_PLATFORM_ADAPTER":
                issues.append(f"Unexpected collection method in mock mode: '{report.collection_method}'")
                detector_ok = False

            if not report.primary_system_volume:
                issues.append("Primary system volume missing in mock mode")
                ssv_ok = False
            else:
                sys_vol = report.primary_system_volume
                if not sys_vol.is_read_only:
                    issues.append("APFS System Volume must be mounted read-only (SSV invariant)")
                    ssv_ok = False
                if not sys_vol.is_sealed_system_volume:
                    issues.append("APFS System Volume must be sealed (SSV invariant)")
                    ssv_ok = False

            if not report.primary_data_volume:
                issues.append("Primary data volume missing in mock mode")
                ssv_ok = False
            else:
                data_vol = report.primary_data_volume
                if data_vol.is_read_only:
                    issues.append("APFS Data Volume must be read-write")
                    ssv_ok = False
                if not data_vol.is_filevault_encrypted:
                    issues.append("APFS Data Volume must have FileVault active in standard profile")
                    ssv_ok = False

            if report.total_internal_capacity_bytes <= 0:
                issues.append("Total internal capacity must be positive in mock mode")
                ssv_ok = False

        except Exception as e:
            issues.append(f"MacStorageDetector audit failed with exception: {e}")
            detector_ok = False

        # 3. Audit Developer CLI Tool
        cli_path = base_dir / cls.CLI_REL_PATH
        if not cli_path.exists():
            issues.append(f"Developer CLI tool missing at: {cli_path}")
            cli_ok = False
        else:
            cli_text = cli_path.read_text(encoding="utf-8")
            if "shell=True" in cli_text:
                issues.append(f"Prohibited ambient shell invocation (shell=True) found in {cli_path}")
                cli_ok = False

            # Test execution of CLI tool in mock mode
            try:
                proc = subprocess.run(
                    [sys.executable, str(cli_path), "--mock", "--json"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    shell=False,
                    timeout=15.0,
                )
                if proc.returncode != 0:
                    issues.append(f"CLI tool returned non-zero exit code ({proc.returncode}): {proc.stderr}")
                    cli_ok = False
                else:
                    payload = json.loads(proc.stdout)
                    if payload.get("collection_method") != "MOCK_PLATFORM_ADAPTER":
                        issues.append("CLI JSON output missing expected collection_method in mock mode")
                        cli_ok = False
            except Exception as e:
                issues.append(f"Failed to execute CLI tool '{cli_path}': {e}")
                cli_ok = False

        # 4. Audit Rust Sensor File
        rust_sensor_path = base_dir / "crates" / "system-mind-sensors" / "src" / "macos_storage.rs"
        if not rust_sensor_path.exists():
            issues.append(f"Rust macOS storage sensor file missing: {rust_sensor_path}")
            detector_ok = False

        is_valid = len(issues) == 0
        return MacOsStorageAuditResult(
            valid=is_valid,
            issues=tuple(issues),
            models_valid=models_ok,
            detector_valid=detector_ok,
            cli_valid=cli_ok,
            apfs_ssv_valid=ssv_ok,
        )
