"""Data models for macOS GPU and display inventory telemetry."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import List, Optional


class GpuBusType(str, Enum):
    """Categorical classification of GPU bus interconnect architecture."""

    BUILTIN = "BUILTIN"          # Built-in / integrated SoC graphics (Apple Silicon, Intel Iris/UHD)
    PCIE = "PCIE"                # Discrete PCIe graphics (AMD Radeon Pro, eGPU)
    UNKNOWN = "UNKNOWN"          # Unrecognized or virtual display adapter


class DisplayConnectionType(str, Enum):
    """Physical or virtual display connection interconnect type."""

    INTERNAL = "INTERNAL"        # Built-in laptop display / Retina panel (spdisplays_internal)
    DISPLAYPORT = "DISPLAYPORT"  # DisplayPort / USB-C DP Alt Mode (spdisplays_displayport)
    HDMI = "HDMI"                # High-Definition Multimedia Interface (spdisplays_hdmi)
    THUNDERBOLT = "THUNDERBOLT"  # Thunderbolt direct display (spdisplays_thunderbolt)
    AIRPLAY = "AIRPLAY"          # Wireless AirPlay or iPad Sidecar virtual display
    UNKNOWN = "UNKNOWN"          # Unclassified or synthetic connection


@dataclass(frozen=True)
class MacDisplayInfo:
    """Strongly typed inventory and configuration for a single connected display monitor."""

    name: str
    display_id: Optional[str] = None
    vendor_id: Optional[str] = None
    product_id: Optional[str] = None
    anonymized_serial_hash: Optional[str] = None  # Truncated SHA-256 digest (INV-GPU-02)
    native_pixels: Optional[str] = None           # e.g. "2880 x 1800", "2560 x 1600"
    resolution: Optional[str] = None              # e.g. "1440 x 900 @ 60.00Hz"
    ui_resolution: Optional[str] = None           # e.g. "1440 x 900"
    refresh_rate_hz: Optional[float] = None       # e.g. 60.0 or 120.0 (ProMotion)
    is_main: bool = False
    is_builtin: bool = False
    is_online: bool = True
    is_mirror: bool = False
    connection_type: DisplayConnectionType = DisplayConnectionType.UNKNOWN
    pixel_density_retina: bool = False
    ambient_brightness: bool = False


@dataclass(frozen=True)
class MacGpuInfo:
    """Strongly typed hardware properties and display associations for a single GPU."""

    name: str
    vendor: str = "Apple"
    core_count: Optional[int] = None
    bus_type: GpuBusType = GpuBusType.BUILTIN
    metal_support: Optional[str] = None
    device_type: str = "spdisplays_gpu"
    vram_bytes: Optional[int] = None
    vram_text: Optional[str] = None
    displays: List[MacDisplayInfo] = field(default_factory=list)


@dataclass(frozen=True)
class MacGpuReport:
    """Authoritative aggregated GPU and display inventory report for macOS companion agent."""

    gpus: List[MacGpuInfo] = field(default_factory=list)
    total_gpu_count: int = 0
    total_display_count: int = 0
    primary_display_resolution: Optional[str] = None
    has_builtin_display: bool = False
    has_external_display: bool = False
    collected_at_epoch_secs: float = field(default_factory=time.time)
    collection_method: str = "NATIVE_DARWIN_SYSTEM_PROFILER"
    unavailable_telemetry: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    scan_proves_safe: bool = False  # Charter non-negotiable invariant: Scan != Safe
