"""Read-only macOS storage volumes, APFS container topology, capacity, and filesystem detector.

Inspects mounted filesystems, APFS Signed System Volume (SSV) sealed state, FileVault
encryption status, volume roles (System, Data, VM, Preboot), and available space using
unprivileged Darwin mount, statvfs, and diskutil queries in strict compliance with SC-01
and privacy constraints.
"""

from __future__ import annotations

import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from system_mind.macos.storage_models import (
    FilesystemType,
    MacStorageReport,
    MacVolumeInfo,
    VolumeRole,
)
from system_mind.platform.adapter import MockPlatformAdapter


def _safe_exec(cmd: List[str], timeout: int = 5) -> Tuple[int, str]:
    """Execute a read-only query safely without shell=True in compliance with SC-01."""
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=False,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout.strip()
    except (FileNotFoundError, subprocess.SubprocessError):
        return 127, ""


class MacStorageDetector:
    """Read-only detector for macOS storage volumes, APFS container hierarchy, and capacity."""

    @classmethod
    def deduce_volume_role(cls, mount_point: str, fs_type: str, flags: List[str]) -> VolumeRole:
        """Deduce the functional role of a volume from its mount point and flags."""
        clean_mount = mount_point.rstrip("/")
        if clean_mount == "" or clean_mount == "/":
            return VolumeRole.SYSTEM
        elif clean_mount == "/System/Volumes/Data":
            return VolumeRole.DATA
        elif clean_mount == "/System/Volumes/VM":
            return VolumeRole.VM
        elif clean_mount == "/System/Volumes/Preboot" or "iSCPreboot" in clean_mount:
            return VolumeRole.PREBOOT
        elif clean_mount == "/System/Volumes/Update":
            return VolumeRole.UPDATE
        elif clean_mount == "/System/Volumes/Hardware" or clean_mount == "/System/Volumes/xarts":
            return VolumeRole.HARDWARE
        elif clean_mount.startswith("/Volumes/"):
            return VolumeRole.USER_EXTERNAL
        elif fs_type == "devfs" or clean_mount == "/dev":
            return VolumeRole.SYSTEM_SYNTHETIC
        return VolumeRole.GENERIC

    @classmethod
    def parse_mount_output(cls, raw: str) -> List[Dict[str, Any]]:
        """Parse raw `/sbin/mount` output lines into structured volume records."""
        records: List[Dict[str, Any]] = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            # Pattern: /dev/disk3s1s1 on / (apfs, sealed, local, read-only, journaled)
            m = re.match(r"^(\S+)\s+on\s+(.+?)\s+\(([^)]+)\)$", line)
            if not m:
                continue
            dev_node = m.group(1)
            mount_pt = m.group(2)
            raw_flags = [f.strip() for f in m.group(3).split(",")]
            fs_type = raw_flags[0] if raw_flags else "unknown"

            records.append(
                {
                    "device_node": dev_node,
                    "mount_point": mount_pt,
                    "filesystem_type": fs_type,
                    "flags": raw_flags,
                }
            )
        return records

    @classmethod
    def enrich_via_diskutil(cls, mount_or_device: str) -> Dict[str, Any]:
        """Query non-privileged `diskutil info` to extract APFS container and security properties."""
        rc, out = _safe_exec(["diskutil", "info", mount_or_device])
        info: Dict[str, Any] = {
            "volume_name": "",
            "device_identifier": "",
            "filevault": False,
            "sealed": False,
            "volume_uuid": None,
            "apfs_container": None,
            "is_internal": True,
            "is_solid_state": True,
        }
        if rc != 0 or not out:
            return info

        for line in out.splitlines():
            line = line.strip()
            if ":" not in line:
                continue
            k, v = line.split(":", 1)
            k = k.strip()
            v = v.strip()

            if k == "Volume Name":
                info["volume_name"] = v
            elif k == "Device Identifier":
                info["device_identifier"] = v
            elif k == "FileVault":
                info["filevault"] = "yes" in v.lower()
            elif k == "Sealed":
                info["sealed"] = "yes" in v.lower()
            elif k in ("Volume UUID", "Disk / Partition UUID"):
                if not info["volume_uuid"]:
                    info["volume_uuid"] = v
            elif k == "APFS Container":
                info["apfs_container"] = v
            elif k == "Device Location":
                info["is_internal"] = "internal" in v.lower()
            elif k == "Solid State":
                info["is_solid_state"] = "yes" in v.lower()

        return info

    @classmethod
    def query_statvfs(cls, mount_point: str) -> Tuple[int, int, int, float, bool]:
        """Query POSIX statvfs for capacity, used bytes, available bytes, and read-only flag."""
        try:
            st = os.statvfs(mount_point)
            frsize = st.f_frsize or st.f_bsize or 4096
            total = st.f_blocks * frsize
            available = st.f_bavail * frsize
            free = st.f_bfree * frsize
            used = max(0, total - free)
            used_pct = round((used / total) * 100, 2) if total > 0 else 0.0
            is_ro = bool(st.f_flag & getattr(os, "ST_RDONLY", 1))
            return total, used, available, used_pct, is_ro
        except (OSError, PermissionError):
            return 0, 0, 0, 0.0, False

    @classmethod
    def detect(cls, mock_adapter: Optional[MockPlatformAdapter] = None) -> MacStorageReport:
        """Execute storage detection using live Darwin host or mock platform adapter."""
        if mock_adapter is not None:
            return cls._detect_from_mock(mock_adapter)

        if platform.system() == "Darwin":
            return cls._detect_live_darwin()

        return cls._detect_non_darwin_fallback()

    @classmethod
    def _detect_live_darwin(cls) -> MacStorageReport:
        """Collect live volume, APFS, and filesystem telemetry from native Darwin interfaces."""
        unavailable: List[str] = []
        warnings: List[str] = []

        rc_mount, out_mount = _safe_exec(["/sbin/mount"])
        if rc_mount != 0 or not out_mount:
            rc_mount, out_mount = _safe_exec(["mount"])

        if rc_mount != 0 or not out_mount:
            unavailable.append("/sbin/mount")
            warnings.append("Failed to execute mount command; falling back to root statvfs.")
            mount_records = [{"device_node": "/dev/root", "mount_point": "/", "filesystem_type": "apfs", "flags": ["read-only"]}]
        else:
            mount_records = cls.parse_mount_output(out_mount)

        volumes: List[MacVolumeInfo] = []
        primary_sys: Optional[MacVolumeInfo] = None
        primary_data: Optional[MacVolumeInfo] = None
        has_filevault = False
        has_sealed_ssv = False
        total_internal_cap = 0
        total_internal_avail = 0

        for rec in mount_records:
            mount_pt = rec["mount_point"]
            dev_node = rec["device_node"]
            fs_type = rec["filesystem_type"]
            flags = rec["flags"]

            role = cls.deduce_volume_role(mount_pt, fs_type, flags)

            # Query POSIX statvfs for capacity and available space
            cap_bytes, used_bytes, avail_bytes, used_pct, is_ro = cls.query_statvfs(mount_pt)

            # If mount flag contains 'read-only' or 'sealed', enforce read-only
            if "read-only" in flags or "sealed" in flags:
                is_ro = True

            # Query diskutil info for APFS properties on primary volumes
            diskutil_info = {}
            if role in (VolumeRole.SYSTEM, VolumeRole.DATA) or mount_pt == "/" or "disk" in dev_node:
                diskutil_info = cls.enrich_via_diskutil(mount_pt)

            vol_name = diskutil_info.get("volume_name") or Path(mount_pt).name or "Root"
            dev_id = diskutil_info.get("device_identifier") or Path(dev_node).name
            is_sealed = diskutil_info.get("sealed", False) or "sealed" in flags
            is_fv = diskutil_info.get("filevault", False)
            vol_uuid = diskutil_info.get("volume_uuid")
            apfs_cont = diskutil_info.get("apfs_container")
            is_internal = diskutil_info.get("is_internal", True)
            is_ssd = diskutil_info.get("is_solid_state", True)

            vol = MacVolumeInfo(
                device_node=dev_node,
                device_identifier=dev_id,
                mount_point=mount_pt,
                volume_name=vol_name,
                filesystem_type=fs_type,
                volume_role=role,
                total_capacity_bytes=cap_bytes,
                used_bytes=used_bytes,
                available_bytes=avail_bytes,
                used_percent=used_pct,
                is_read_only=is_ro,
                is_sealed_system_volume=is_sealed,
                is_filevault_encrypted=is_fv,
                is_internal=is_internal,
                is_solid_state=is_ssd,
                volume_uuid=vol_uuid,
                apfs_container_id=apfs_cont,
                mount_flags=flags,
            )
            volumes.append(vol)

            if role == VolumeRole.SYSTEM:
                primary_sys = vol
                if is_sealed:
                    has_sealed_ssv = True
            elif role == VolumeRole.DATA and primary_data is None:
                primary_data = vol
                if is_fv:
                    has_filevault = True

            if is_internal and cap_bytes > total_internal_cap:
                # In APFS, multiple volumes share the container; use max container cap
                total_internal_cap = cap_bytes
                total_internal_avail = avail_bytes

        if not has_filevault and primary_data and primary_data.is_filevault_encrypted:
            has_filevault = True

        return MacStorageReport(
            volumes=volumes,
            primary_system_volume=primary_sys,
            primary_data_volume=primary_data,
            total_internal_capacity_bytes=total_internal_cap,
            total_internal_available_bytes=total_internal_avail,
            has_filevault_active=has_filevault,
            has_sealed_system_volume=has_sealed_ssv,
            collection_method="NATIVE_DARWIN_STATVFS_DISKUTIL",
            unavailable_telemetry=unavailable,
            warnings=warnings,
        )

    @classmethod
    def _detect_from_mock(cls, mock: MockPlatformAdapter) -> MacStorageReport:
        """Synthesize deterministic storage telemetry matching Apple Silicon APFS container."""
        container_cap = 245107195904  # ~245 GB
        avail_bytes = 35981094912     # ~36 GB available
        used_pct = round(((container_cap - avail_bytes) / container_cap) * 100, 2)

        sys_vol = MacVolumeInfo(
            device_node="/dev/disk3s1s1",
            device_identifier="disk3s1s1",
            mount_point="/",
            volume_name="Macintosh HD",
            filesystem_type="apfs",
            volume_role=VolumeRole.SYSTEM,
            total_capacity_bytes=container_cap,
            used_bytes=13947080704,  # ~13.9 GB
            available_bytes=avail_bytes,
            used_percent=5.7,
            is_read_only=True,
            is_sealed_system_volume=True,
            is_filevault_encrypted=False,
            is_internal=True,
            is_solid_state=True,
            volume_uuid="89B0F266-E9F9-40A2-86A0-B56EC413D5BB",
            apfs_container_id="disk3",
            mount_flags=["apfs", "sealed", "local", "read-only", "journaled"],
        )

        data_vol = MacVolumeInfo(
            device_node="/dev/disk3s5",
            device_identifier="disk3s5",
            mount_point="/System/Volumes/Data",
            volume_name="Data",
            filesystem_type="apfs",
            volume_role=VolumeRole.DATA,
            total_capacity_bytes=container_cap,
            used_bytes=178003226624,  # ~178 GB
            available_bytes=avail_bytes,
            used_percent=72.6,
            is_read_only=False,
            is_sealed_system_volume=False,
            is_filevault_encrypted=True,
            is_internal=True,
            is_solid_state=True,
            volume_uuid="D055B4C7-7917-4E57-9478-C0BC3BCB1226",
            apfs_container_id="disk3",
            mount_flags=["apfs", "local", "journaled", "nobrowse", "protect", "root data"],
        )

        vm_vol = MacVolumeInfo(
            device_node="/dev/disk3s6",
            device_identifier="disk3s6",
            mount_point="/System/Volumes/VM",
            volume_name="VM",
            filesystem_type="apfs",
            volume_role=VolumeRole.VM,
            total_capacity_bytes=container_cap,
            used_bytes=4194492000,
            available_bytes=avail_bytes,
            used_percent=1.7,
            is_read_only=False,
            is_sealed_system_volume=False,
            is_filevault_encrypted=False,
            is_internal=True,
            is_solid_state=True,
            volume_uuid="A1B2C3D4-E5F6-4A5B-8C9D-0E1F2A3B4C5D",
            apfs_container_id="disk3",
            mount_flags=["apfs", "local", "noexec", "journaled", "noatime", "nobrowse"],
        )

        volumes = [sys_vol, data_vol, vm_vol]

        return MacStorageReport(
            volumes=volumes,
            primary_system_volume=sys_vol,
            primary_data_volume=data_vol,
            total_internal_capacity_bytes=container_cap,
            total_internal_available_bytes=avail_bytes,
            has_filevault_active=True,
            has_sealed_system_volume=True,
            collection_method="MOCK_PLATFORM_ADAPTER",
            unavailable_telemetry=[],
            warnings=[],
        )

    @classmethod
    def _detect_non_darwin_fallback(cls) -> MacStorageReport:
        """Provide safe fallback report when executed on non-Darwin platforms."""
        unavailable = [
            "diskutil",
            "apfs.container",
            "apfs.ssv_sealed",
            "apfs.filevault",
        ]
        warnings = [
            f"Native Darwin storage interfaces unavailable on non-Darwin OS: '{platform.system()}'",
            "Report synthesized from generic POSIX statvfs.",
        ]

        cap_bytes, used_bytes, avail_bytes, used_pct, is_ro = cls.query_statvfs("/")
        root_vol = MacVolumeInfo(
            device_node="/dev/root",
            device_identifier="root",
            mount_point="/",
            volume_name="Root",
            filesystem_type="ext4" if platform.system() == "Linux" else "ntfs",
            volume_role=VolumeRole.SYSTEM,
            total_capacity_bytes=cap_bytes,
            used_bytes=used_bytes,
            available_bytes=avail_bytes,
            used_percent=used_pct,
            is_read_only=is_ro,
            is_sealed_system_volume=False,
            is_filevault_encrypted=False,
            is_internal=True,
            is_solid_state=True,
            mount_flags=[],
        )

        return MacStorageReport(
            volumes=[root_vol],
            primary_system_volume=root_vol,
            primary_data_volume=None,
            total_internal_capacity_bytes=cap_bytes,
            total_internal_available_bytes=avail_bytes,
            has_filevault_active=False,
            has_sealed_system_volume=False,
            collection_method="GENERIC_NON_DARWIN_FALLBACK",
            unavailable_telemetry=unavailable,
            warnings=warnings,
        )
