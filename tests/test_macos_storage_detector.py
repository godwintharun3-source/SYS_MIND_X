"""Comprehensive unit, contract, and integration tests for macOS Storage Volumes, APFS, and Filesystem Telemetry."""

from __future__ import annotations

import json
from pathlib import Path
import platform
import subprocess
import sys
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent

from system_mind.macos.storage_detector import MacStorageDetector
from system_mind.macos.storage_models import (
    FilesystemType,
    MacStorageReport,
    MacVolumeInfo,
    VolumeRole,
)
from system_mind.packaging.macos_storage import (
    MacOsStorageAuditResult,
    MacOsStorageValidator,
)
from system_mind.platform.adapter import (
    MockPlatformAdapter,
    MockPlatformProfileFactory,
)


def test_macos_storage_detector_mock_mode():
    """Verify storage detection using MockPlatformAdapter generates consistent APFS topology."""
    mock = MockPlatformProfileFactory.create_macos_apple_silicon_mock()
    report = MacStorageDetector.detect(mock_adapter=mock)

    assert isinstance(report, MacStorageReport)
    assert report.collection_method == "MOCK_PLATFORM_ADAPTER"
    assert report.collected_at_epoch_secs > 0

    assert len(report.volumes) == 3
    assert report.primary_system_volume is not None
    assert report.primary_data_volume is not None

    sys_vol = report.primary_system_volume
    assert sys_vol.mount_point == "/"
    assert sys_vol.volume_role == VolumeRole.SYSTEM
    assert sys_vol.is_read_only is True
    assert sys_vol.is_sealed_system_volume is True
    assert sys_vol.filesystem_type == "apfs"
    assert sys_vol.apfs_container_id == "disk3"

    data_vol = report.primary_data_volume
    assert data_vol.mount_point == "/System/Volumes/Data"
    assert data_vol.volume_role == VolumeRole.DATA
    assert data_vol.is_read_only is False
    assert data_vol.is_filevault_encrypted is True
    assert data_vol.filesystem_type == "apfs"

    assert report.total_internal_capacity_bytes > 0
    assert report.total_internal_available_bytes > 0
    assert report.has_filevault_active is True
    assert report.has_sealed_system_volume is True


def test_macos_storage_detector_live_on_darwin():
    """Verify live detection gathers valid filesystem facts when executing on native Darwin macOS host."""
    if platform.system() != "Darwin":
        pytest.skip("Test requires native macOS Darwin host")

    report = MacStorageDetector.detect()

    assert isinstance(report, MacStorageReport)
    assert report.collection_method == "NATIVE_DARWIN_STATVFS_DISKUTIL"
    assert report.collected_at_epoch_secs > 0

    assert len(report.volumes) >= 1
    assert report.primary_system_volume is not None
    assert report.primary_system_volume.mount_point == "/"

    if platform.machine() == "arm64":
        # On Apple Silicon (macOS 11+), Signed System Volume is sealed and read-only
        assert report.primary_system_volume.is_read_only is True
        assert report.primary_system_volume.is_sealed_system_volume is True
        assert report.has_sealed_system_volume is True

    assert report.total_internal_capacity_bytes >= 10 * 1024 * 1024 * 1024  # >= 10GB
    assert report.total_internal_available_bytes > 0


def test_parse_mount_output_structure():
    """Verify parsing of standard Darwin `/sbin/mount` format lines."""
    sample_mount = """/dev/disk3s1s1 on / (apfs, sealed, local, read-only, journaled)
devfs on /dev (devfs, local, nobrowse)
/dev/disk3s6 on /System/Volumes/VM (apfs, local, noexec, journaled, noatime, nobrowse)
/dev/disk3s5 on /System/Volumes/Data (apfs, local, journaled, nobrowse, protect, root data)
/dev/disk4s1 on /Volumes/ExternalDrive (hfs, local, nodev, nosuid, read-only)
"""
    records = MacStorageDetector.parse_mount_output(sample_mount)
    assert len(records) == 5

    rec_root = records[0]
    assert rec_root["device_node"] == "/dev/disk3s1s1"
    assert rec_root["mount_point"] == "/"
    assert rec_root["filesystem_type"] == "apfs"
    assert "sealed" in rec_root["flags"]
    assert "read-only" in rec_root["flags"]

    rec_data = records[3]
    assert rec_data["mount_point"] == "/System/Volumes/Data"
    assert rec_data["filesystem_type"] == "apfs"


def test_deduce_volume_role():
    """Verify mapping from mount point and flags to canonical VolumeRole enum."""
    assert MacStorageDetector.deduce_volume_role("/", "apfs", ["read-only"]) == VolumeRole.SYSTEM
    assert MacStorageDetector.deduce_volume_role("/System/Volumes/Data", "apfs", []) == VolumeRole.DATA
    assert MacStorageDetector.deduce_volume_role("/System/Volumes/VM", "apfs", ["noexec"]) == VolumeRole.VM
    assert MacStorageDetector.deduce_volume_role("/System/Volumes/Preboot", "apfs", []) == VolumeRole.PREBOOT
    assert MacStorageDetector.deduce_volume_role("/System/Volumes/Update", "apfs", []) == VolumeRole.UPDATE
    assert MacStorageDetector.deduce_volume_role("/Volumes/BackupUSB", "hfs", []) == VolumeRole.USER_EXTERNAL
    assert MacStorageDetector.deduce_volume_role("/dev", "devfs", []) == VolumeRole.SYSTEM_SYNTHETIC
    assert MacStorageDetector.deduce_volume_role("/mnt/unknown", "ext4", []) == VolumeRole.GENERIC


def test_non_darwin_fallback_behavior():
    """Verify graceful degradation when queried on non-Darwin platforms."""
    report = MacStorageDetector._detect_non_darwin_fallback()

    assert isinstance(report, MacStorageReport)
    assert report.collection_method == "GENERIC_NON_DARWIN_FALLBACK"
    assert len(report.unavailable_telemetry) > 0
    assert "diskutil" in report.unavailable_telemetry
    assert len(report.warnings) > 0
    assert len(report.volumes) >= 1
    assert report.primary_system_volume is not None


def test_macos_storage_validator_clean_audit():
    """Verify programmatic packaging validator passes with zero issues."""
    audit = MacOsStorageValidator.audit()

    assert audit.valid is True, f"Validator found issues: {audit.issues}"
    assert audit.models_valid is True
    assert audit.detector_valid is True
    assert audit.cli_valid is True
    assert audit.apfs_ssv_valid is True
    assert len(audit.issues) == 0


def test_detect_storage_cli_execution():
    """Verify developer CLI tool executes cleanly in mock, JSON, and check-free-space modes."""
    cli_path = ROOT_DIR / "tools" / "detect_storage.py"
    assert cli_path.exists()

    # 1. Test mock with JSON
    proc = subprocess.run(
        [sys.executable, str(cli_path), "--mock", "--json"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=False,
        timeout=15,
    )
    assert proc.returncode == 0, f"CLI mock failed: {proc.stderr}"
    data = json.loads(proc.stdout)
    assert data["collection_method"] == "MOCK_PLATFORM_ADAPTER"
    assert data["has_sealed_system_volume"] is True
    assert data["has_filevault_active"] is True
    assert len(data["volumes"]) >= 2

    # 2. Test check-free-space-gb pass case in mock mode (mock has ~36GB free, check 10GB)
    proc_space_pass = subprocess.run(
        [sys.executable, str(cli_path), "--mock", "--check-free-space-gb", "10.0"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=False,
        timeout=15,
    )
    assert proc_space_pass.returncode == 0

    # 3. Test check-free-space-gb fail case in mock mode (check 500GB)
    proc_space_fail = subprocess.run(
        [sys.executable, str(cli_path), "--mock", "--check-free-space-gb", "500.0"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=False,
        timeout=15,
    )
    assert proc_space_fail.returncode == 1
    assert "Precondition Failed" in proc_space_fail.stderr


def test_storage_models_immutability():
    """Verify dataclasses enforce frozen immutability to prevent runtime tampering."""
    vol = MacVolumeInfo(
        device_node="/dev/disk3s1s1",
        device_identifier="disk3s1s1",
        mount_point="/",
        volume_name="Macintosh HD",
        filesystem_type="apfs",
        volume_role=VolumeRole.SYSTEM,
        total_capacity_bytes=245107195904,
        used_bytes=13947080704,
        available_bytes=35981094912,
        used_percent=5.7,
        is_read_only=True,
        is_sealed_system_volume=True,
    )
    with pytest.raises(Exception):
        vol.is_read_only = False  # type: ignore
