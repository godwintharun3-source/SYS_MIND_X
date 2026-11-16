"""Data models for macOS system agent and platform telemetry."""

from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import List, Optional


@dataclass(frozen=True)
class MacOSVersionInfo:
    """macOS product version, Darwin kernel release, and build metadata."""

    product_name: str
    product_version: str
    major_version: int
    minor_version: int
    patch_version: int
    build_version: str
    darwin_kernel_release: str
    marketing_name: str


@dataclass(frozen=True)
class MacArchitecture:
    """Processor architecture, Apple Silicon classification, and execution mode."""

    machine: str
    is_apple_silicon: bool
    byte_order: str = "little"
    pointer_size_bits: int = 64
    is_rosetta_translated: bool = False


@dataclass(frozen=True)
class MacHostIdentity:
    """Privacy-preserving host identity, names, and anonymized hardware identifiers."""

    hostname: str
    computer_name: str
    local_host_name: str
    platform_uuid: Optional[str] = None
    anonymized_serial_hash: Optional[str] = None
    is_virtual_machine: bool = False


@dataclass(frozen=True)
class MacTelemetryReport:
    """Authoritative aggregated telemetry report for macOS host companion agent."""

    version_info: MacOSVersionInfo
    architecture: MacArchitecture
    identity: MacHostIdentity
    collected_at_epoch_secs: float = field(default_factory=time.time)
    collection_method: str = "NATIVE_DARWIN_SYSCTL"
    unavailable_telemetry: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
