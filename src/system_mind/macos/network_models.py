"""Data models for macOS network interfaces, link states, IP addresses, and connectivity metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import List, Optional


class InterfaceType(str, Enum):
    """Categorical classification of macOS network interface architecture."""

    LOOPBACK = "LOOPBACK"          # lo0
    WIFI = "WIFI"                  # Wi-Fi (en0 on MacBooks)
    ETHERNET = "ETHERNET"          # Built-in or USB/Thunderbolt Ethernet
    THUNDERBOLT = "THUNDERBOLT"    # Thunderbolt bridge/direct
    BRIDGE = "BRIDGE"              # Software or Thunderbolt bridge
    VPN_TUNNEL = "VPN_TUNNEL"      # utun*, ipsec, wireguard
    AWDL = "AWDL"                  # Apple Wireless Direct Link (awdl0)
    CELLULAR = "CELLULAR"          # Cellular modem / iPad tether
    OTHER = "OTHER"                # Virtual, synthetic, or unclassified


class LinkState(str, Enum):
    """Operational and physical link status of a network interface."""

    UP_ACTIVE = "UP_ACTIVE"        # Interface marked UP with active carrier link
    UP_INACTIVE = "UP_INACTIVE"    # Interface marked UP but carrier media inactive/unplugged
    DOWN = "DOWN"                  # Interface administratively disabled or powered off


@dataclass(frozen=True)
class MacIpAddress:
    """Strongly typed IPv4 or IPv6 network address binding."""

    address: str
    family: str                    # "inet" (IPv4) or "inet6" (IPv6)
    netmask: Optional[str] = None
    broadcast: Optional[str] = None
    prefixlen: Optional[int] = None
    scope: Optional[str] = None
    is_loopback: bool = False


@dataclass(frozen=True)
class MacNetworkInterface:
    """Strongly typed metadata and address bindings for a single network interface."""

    name: str                      # e.g. "en0", "lo0", "utun0"
    hardware_port: Optional[str] = None  # e.g. "Wi-Fi", "Thunderbolt 1"
    interface_type: InterfaceType = InterfaceType.OTHER
    link_state: LinkState = LinkState.DOWN
    mtu: int = 1500
    mac_address: Optional[str] = None
    anonymized_mac_hash: Optional[str] = None  # Truncated SHA-256 digest (INV-NET-02)
    ip_addresses: List[MacIpAddress] = field(default_factory=list)
    flags: List[str] = field(default_factory=list)
    is_primary: bool = False
    media: Optional[str] = None


@dataclass(frozen=True)
class MacNetworkRoute:
    """Strongly typed network route entry from Darwin routing tables."""

    destination: str
    gateway: str
    interface: str
    flags: str = ""


@dataclass(frozen=True)
class MacNetworkReport:
    """Authoritative aggregated network telemetry report for macOS companion agent."""

    interfaces: List[MacNetworkInterface] = field(default_factory=list)
    primary_interface_name: Optional[str] = None
    is_online: bool = False
    default_gateway: Optional[str] = None
    dns_servers: List[str] = field(default_factory=list)
    search_domains: List[str] = field(default_factory=list)
    collected_at_epoch_secs: float = field(default_factory=time.time)
    collection_method: str = "NATIVE_DARWIN_IFCONFIG_SCUTIL_NETSTAT"
    unavailable_telemetry: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    scan_proves_safe: bool = False  # Charter non-negotiable invariant: Scan != Safe
