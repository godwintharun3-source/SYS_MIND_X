"""Data models for macOS USB and peripheral inventory telemetry with privacy constraints."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import List, Optional


class UsbDeviceClass(str, Enum):
    """Categorical classification of USB peripheral device functionality."""

    HUB = "HUB"                        # USB root hub or downstream port multiplier
    HUMAN_INTERFACE = "HUMAN_INTERFACE"  # Keyboards, mice, trackpads, drawing tablets, gamepads
    SECURITY_TOKEN = "SECURITY_TOKEN"  # Hardware security tokens (YubiKey, smartcards, FIDO/U2F)
    MASS_STORAGE = "MASS_STORAGE"      # Flash drives, external SSDs/HDDs, SD card readers
    AUDIO_VIDEO = "AUDIO_VIDEO"        # Microphones, webcams, DACs, audio interfaces
    COMMUNICATIONS = "COMMUNICATIONS"  # USB Ethernet adapters, serial ports, modems
    WIRELESS = "WIRELESS"              # Bluetooth dongles, proprietary RF receivers
    PRINTER = "PRINTER"                # Connected printers / scanners
    OTHER = "OTHER"                    # Miscellaneous, composite, or unclassified devices


class UsbSpeed(str, Enum):
    """Signaling and link speed capability of a USB bus connection."""

    LOW_SPEED_1_5_MBPS = "LOW_SPEED_1_5_MBPS"              # 1.5 Mbps (USB 1.0/1.1)
    FULL_SPEED_12_MBPS = "FULL_SPEED_12_MBPS"              # 12 Mbps (USB 1.1/2.0)
    HIGH_SPEED_480_MBPS = "HIGH_SPEED_480_MBPS"            # 480 Mbps (USB 2.0)
    SUPER_SPEED_5_GBPS = "SUPER_SPEED_5_GBPS"              # 5 Gbps (USB 3.0 / USB 3.1 Gen 1)
    SUPER_SPEED_PLUS_10_GBPS = "SUPER_SPEED_PLUS_10_GBPS"  # 10 Gbps (USB 3.1 Gen 2 / USB 3.2 Gen 2)
    SUPER_SPEED_PLUS_20_GBPS = "SUPER_SPEED_PLUS_20_GBPS"  # 20 Gbps (USB 3.2 Gen 2x2)
    USB4_40_GBPS = "USB4_40_GBPS"                          # 40 Gbps (USB4 / Thunderbolt 4)
    UNKNOWN = "UNKNOWN"                                    # Unspecified or virtual speed


@dataclass(frozen=True)
class MacUsbDevice:
    """Strongly typed inventory and descriptor configuration for a single USB peripheral."""

    name: str
    vendor_id: Optional[str] = None
    product_id: Optional[str] = None
    manufacturer: Optional[str] = None
    anonymized_serial_hash: Optional[str] = None  # Truncated SHA-256 digest (INV-USB-02)
    device_class: UsbDeviceClass = UsbDeviceClass.OTHER
    speed: UsbSpeed = UsbSpeed.UNKNOWN
    speed_text: Optional[str] = None
    location_id: Optional[str] = None
    bus_power_ma: Optional[int] = None
    current_used_ma: Optional[int] = None
    extra_current_ma: Optional[int] = None
    bcd_device: Optional[str] = None
    is_builtin: bool = False
    is_hub: bool = False
    children: List[MacUsbDevice] = field(default_factory=list)


@dataclass(frozen=True)
class MacUsbController:
    """Strongly typed USB host controller or root bus instance."""

    name: str
    host_controller: Optional[str] = None
    pci_device: Optional[str] = None
    pci_vendor: Optional[str] = None
    devices: List[MacUsbDevice] = field(default_factory=list)


@dataclass(frozen=True)
class MacUsbReport:
    """Authoritative aggregated USB and peripheral inventory report for macOS companion agent."""

    controllers: List[MacUsbController] = field(default_factory=list)
    total_controller_count: int = 0
    total_device_count: int = 0  # Total count of all devices (including nested hub children)
    has_external_devices: bool = False
    has_security_tokens: bool = False
    has_mass_storage: bool = False
    collected_at_epoch_secs: float = field(default_factory=time.time)
    collection_method: str = "NATIVE_DARWIN_SYSTEM_PROFILER"
    unavailable_telemetry: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    scan_proves_safe: bool = False  # Charter non-negotiable invariant: Scan != Safe
