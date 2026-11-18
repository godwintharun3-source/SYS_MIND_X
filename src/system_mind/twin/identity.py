"""Stable device and entity identifier architecture for the Temporal Digital Twin."""

from __future__ import annotations

import hashlib
import os
import platform
import re
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# RFC 4122 namespace for deterministic UUIDv5 generation
NAMESPACE_SYSTEM_MIND = uuid.UUID("e7b1a234-5678-4321-89ab-cdef01234567")

URN_PATTERN = re.compile(r"^urn:systemmind:([a-z_]+):([a-zA-Z0-9_.:\-]+)$")


class EntityDomain(str, Enum):
    """Canonical domains supported in System Mind entity URNs."""

    HOST = "host"
    KERNEL = "kernel"
    CPU = "cpu"
    MEMORY = "mem"
    STORAGE_VOLUME = "vol"
    NETWORK_INTERFACE = "net"
    APPLICATION = "app"
    PROCESS = "proc"
    SERVICE = "svc"
    FILESYSTEM_NODE = "file"
    PACKAGE = "pkg"


@dataclass(frozen=True)
class EntityUrn:
    """Strongly typed representation of a canonical digital twin entity URN."""

    domain: EntityDomain
    qualifier: str
    urn: str
    scan_proves_safe: bool = False  # Mandatory charter invariant SC-03

    def __post_init__(self) -> None:
        if self.scan_proves_safe is not False:
            raise ValueError("Charter invariant violation: scan_proves_safe must always be False")

    def __str__(self) -> str:
        return self.urn

    @classmethod
    def parse(cls, urn_string: str) -> EntityUrn:
        """Parse and validate a canonical URN string."""
        m = URN_PATTERN.match(urn_string)
        if not m:
            raise ValueError(f"Invalid entity URN syntax: {urn_string}")

        domain_str, qualifier = m.groups()
        try:
            domain = EntityDomain(domain_str)
        except ValueError:
            raise ValueError(f"Unknown entity domain in URN: {domain_str}")

        return cls(domain=domain, qualifier=qualifier, urn=urn_string, scan_proves_safe=False)


class DeviceIdentifierManager:
    """Manages persistent, collision-resistant device identifiers across reboots."""

    DEFAULT_CACHE_DIR = Path.home() / ".system-mind"
    CACHE_FILE_NAME = "device_id"

    @classmethod
    def resolve_device_id(
        cls,
        hardware_uuid: Optional[str] = None,
        use_cache: bool = True,
        cache_dir: Optional[Path] = None,
    ) -> str:
        """Resolve a stable device identifier from cache, hardware anchor, or deterministic seed."""
        target_dir = cache_dir or cls.DEFAULT_CACHE_DIR
        cache_file = target_dir / cls.CACHE_FILE_NAME

        # 1. Attempt reading from cache
        if use_cache and cache_file.is_file():
            try:
                cached_id = cache_file.read_text(encoding="utf-8").strip()
                # Validate UUID format
                uuid.UUID(cached_id)
                return cached_id
            except Exception:
                pass  # Corrupted cache will be regenerated

        # 2. Derive device ID from hardware UUID anchor
        seed = hardware_uuid
        if not seed:
            seed = cls._detect_platform_anchor()

        device_uuid = str(uuid.uuid5(NAMESPACE_SYSTEM_MIND, seed))

        # 3. Persist to cache if permitted
        if use_cache:
            try:
                target_dir.mkdir(parents=True, exist_ok=True)
                cache_file.write_text(device_uuid, encoding="utf-8")
            except Exception:
                pass  # Unprivileged read-only environments gracefully skip disk cache write

        return device_uuid

    @staticmethod
    def _detect_platform_anchor() -> str:
        """Extract a stable hardware anchor string without requiring elevated privileges."""
        system = platform.system()
        if system == "Darwin":
            try:
                # Query IOPlatformUUID via read-only sysctl/ioreg or fallback to node
                import subprocess

                proc = subprocess.run(
                    ["/usr/sbin/ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    shell=False,
                    timeout=2.0,
                )
                for line in proc.stdout.splitlines():
                    if "IOPlatformUUID" in line:
                        parts = line.split("=")
                        if len(parts) > 1:
                            return parts[1].strip().strip('"')
            except Exception:
                pass

        # Fallback to salted node and machine architecture
        node = platform.node() or "system-mind-default-host"
        arch = platform.machine() or "arm64"
        return f"{system}:{arch}:{node}"


class StableEntityIdGenerator:
    """Factory generating deterministic, collision-resistant URN identifiers for all twin entities."""

    @staticmethod
    def hash_token(data: str, length: int = 12) -> str:
        """Compute short deterministic SHA-256 hash token."""
        return hashlib.sha256(data.encode("utf-8")).hexdigest()[:length]

    @classmethod
    def generate_host_urn(cls, device_id: str) -> EntityUrn:
        """Generate canonical host device URN."""
        clean_id = device_id.strip()
        urn_str = f"urn:systemmind:{EntityDomain.HOST.value}:{clean_id}"
        return EntityUrn(EntityDomain.HOST, clean_id, urn_str)

    @classmethod
    def generate_kernel_urn(cls, os_family: str, kernel_release: str, arch: str) -> EntityUrn:
        """Generate canonical OS kernel URN."""
        clean_os = os_family.lower().strip()
        clean_rel = kernel_release.lower().strip()
        clean_arch = arch.lower().strip()
        qualifier = f"{clean_os}:{clean_rel}:{clean_arch}"
        urn_str = f"urn:systemmind:{EntityDomain.KERNEL.value}:{qualifier}"
        return EntityUrn(EntityDomain.KERNEL, qualifier, urn_str)

    @classmethod
    def generate_cpu_urn(cls, arch: str, brand_string: str, core_count: int) -> EntityUrn:
        """Generate canonical CPU hardware URN."""
        clean_arch = arch.lower().strip()
        brand_digest = cls.hash_token(brand_string.strip(), length=12)
        qualifier = f"{clean_arch}:{brand_digest}:{core_count}"
        urn_str = f"urn:systemmind:{EntityDomain.CPU.value}:{qualifier}"
        return EntityUrn(EntityDomain.CPU, qualifier, urn_str)

    @classmethod
    def generate_memory_urn(cls, device_id: str, capacity_bytes: int) -> EntityUrn:
        """Generate canonical physical memory URN."""
        clean_id = device_id.strip()[:8]
        qualifier = f"{clean_id}:{capacity_bytes}"
        urn_str = f"urn:systemmind:{EntityDomain.MEMORY.value}:{qualifier}"
        return EntityUrn(EntityDomain.MEMORY, qualifier, urn_str)

    @classmethod
    def generate_storage_volume_urn(cls, device_id: str, volume_uuid_or_mount: str) -> EntityUrn:
        """Generate canonical storage volume URN."""
        clean_id = device_id.strip()[:8]
        vol_digest = cls.hash_token(volume_uuid_or_mount.strip(), length=16)
        qualifier = f"{clean_id}:{vol_digest}"
        urn_str = f"urn:systemmind:{EntityDomain.STORAGE_VOLUME.value}:{qualifier}"
        return EntityUrn(EntityDomain.STORAGE_VOLUME, qualifier, urn_str)

    @classmethod
    def generate_network_interface_urn(cls, device_id: str, if_name: str) -> EntityUrn:
        """Generate canonical network interface URN."""
        clean_id = device_id.strip()[:8]
        clean_if = if_name.strip().lower()
        qualifier = f"{clean_id}:{clean_if}"
        urn_str = f"urn:systemmind:{EntityDomain.NETWORK_INTERFACE.value}:{qualifier}"
        return EntityUrn(EntityDomain.NETWORK_INTERFACE, qualifier, urn_str)

    @classmethod
    def generate_app_urn(cls, bundle_id_or_name: str) -> EntityUrn:
        """Generate canonical application URN."""
        clean_app = bundle_id_or_name.strip().lower()
        # Sanitize for URN qualifier syntax
        safe_app = re.sub(r"[^a-zA-Z0-9_.-]", "_", clean_app)
        urn_str = f"urn:systemmind:{EntityDomain.APPLICATION.value}:{safe_app}"
        return EntityUrn(EntityDomain.APPLICATION, safe_app, urn_str)

    @classmethod
    def generate_process_urn(
        cls,
        device_id: str,
        pid: int,
        start_time_epoch_ms: int,
        binary_path: str,
    ) -> EntityUrn:
        """Generate temporally qualified process URN to prevent PID recycling collisions."""
        clean_id = device_id.strip()[:8]
        path_digest = cls.hash_token(binary_path.strip(), length=8)
        qualifier = f"{clean_id}:{start_time_epoch_ms}:{pid}:{path_digest}"
        urn_str = f"urn:systemmind:{EntityDomain.PROCESS.value}:{qualifier}"
        return EntityUrn(EntityDomain.PROCESS, qualifier, urn_str)

    @classmethod
    def generate_service_urn(cls, domain: str, service_label: str) -> EntityUrn:
        """Generate canonical background service URN."""
        clean_domain = re.sub(r"[^a-zA-Z0-9_.-]", "_", domain.strip().lower())
        clean_label = re.sub(r"[^a-zA-Z0-9_.-]", "_", service_label.strip())
        qualifier = f"{clean_domain}:{clean_label}"
        urn_str = f"urn:systemmind:{EntityDomain.SERVICE.value}:{qualifier}"
        return EntityUrn(EntityDomain.SERVICE, qualifier, urn_str)

    @classmethod
    def generate_file_urn(cls, device_id: str, volume_id: str, canonical_path: str) -> EntityUrn:
        """Generate canonical filesystem node URN with privacy-preserving path hashing."""
        clean_id = device_id.strip()[:8]
        clean_vol = cls.hash_token(volume_id.strip(), length=8)
        clean_path = cls.hash_token(os.path.normpath(canonical_path.strip()), length=16)
        qualifier = f"{clean_id}:{clean_vol}:{clean_path}"
        urn_str = f"urn:systemmind:{EntityDomain.FILESYSTEM_NODE.value}:{qualifier}"
        return EntityUrn(EntityDomain.FILESYSTEM_NODE, qualifier, urn_str)

    @classmethod
    def generate_package_urn(cls, ecosystem: str, name: str, version: str) -> EntityUrn:
        """Generate canonical software package dependency URN."""
        clean_eco = ecosystem.strip().lower()
        clean_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", name.strip().lower())
        clean_ver = re.sub(r"[^a-zA-Z0-9_.-]", "_", version.strip())
        qualifier = f"{clean_eco}:{clean_name}:{clean_ver}"
        urn_str = f"urn:systemmind:{EntityDomain.PACKAGE.value}:{qualifier}"
        return EntityUrn(EntityDomain.PACKAGE, qualifier, urn_str)


def validate_entity_urn(urn_string: str) -> bool:
    """Validate that a string conforms to the canonical System Mind URN specification."""
    try:
        EntityUrn.parse(urn_string)
        return True
    except Exception:
        return False
