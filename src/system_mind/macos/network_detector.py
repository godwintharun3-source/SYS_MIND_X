"""Read-only macOS network interfaces, link states, routing, and connectivity telemetry detector."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
import platform
import re
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple

from system_mind.macos.network_models import (
    InterfaceType,
    LinkState,
    MacIpAddress,
    MacNetworkInterface,
    MacNetworkReport,
    MacNetworkRoute,
)

logger = logging.getLogger(__name__)

_MAC_SALT = "sysmind-mac-salt:"


class MacNetworkDetector:
    """Read-only, passive introspection engine for macOS network interfaces and connectivity."""

    def __init__(self, salt: str = _MAC_SALT) -> None:
        self._salt = salt

    def anonymize_mac(self, raw_mac: Optional[str]) -> Optional[str]:
        """Anonymize hardware MAC addresses using a salted SHA-256 digest (INV-NET-02)."""
        if not raw_mac or not raw_mac.strip():
            return None
        clean_mac = raw_mac.strip().lower()
        digest = hashlib.sha256(f"{self._salt}{clean_mac}".encode("utf-8")).hexdigest()[:16]
        return f"sha256:{digest}"

    def parse_hardware_ports(self, output: str) -> Dict[str, Dict[str, str]]:
        """Parse text output from unprivileged `networksetup -listallhardwareports`."""
        mapping: Dict[str, Dict[str, str]] = {}
        if not output:
            return mapping

        current_port: Optional[str] = None
        current_dev: Optional[str] = None
        current_mac: Optional[str] = None

        for line in output.splitlines():
            line = line.strip()
            if line.startswith("Hardware Port:"):
                current_port = line.split(":", 1)[1].strip()
            elif line.startswith("Device:"):
                current_dev = line.split(":", 1)[1].strip()
            elif line.startswith("Ethernet Address:"):
                current_mac = line.split(":", 1)[1].strip().lower()

            if current_port and current_dev and current_mac:
                mapping[current_dev] = {
                    "port": current_port,
                    "mac": current_mac,
                }
                current_port = None
                current_dev = None
                current_mac = None

        return mapping

    def classify_interface(
        self,
        name: str,
        flags: List[str],
        hardware_port: Optional[str] = None,
    ) -> InterfaceType:
        """Classify interface into InterfaceType enum based on name, flags, and hardware port."""
        if name == "lo0" or "LOOPBACK" in flags:
            return InterfaceType.LOOPBACK

        port_lower = hardware_port.lower() if hardware_port else ""

        if "wi-fi" in port_lower or "airport" in port_lower:
            return InterfaceType.WIFI
        elif "thunderbolt bridge" in port_lower or name.startswith("bridge"):
            return InterfaceType.BRIDGE
        elif "thunderbolt" in port_lower:
            return InterfaceType.THUNDERBOLT
        elif "ethernet" in port_lower:
            return InterfaceType.ETHERNET

        if name.startswith("awdl"):
            return InterfaceType.AWDL
        elif name.startswith("llw") or name.startswith("nan"):
            return InterfaceType.AWDL
        elif name.startswith("utun") or name.startswith("ipsec") or name.startswith("ppp") or name.startswith("wg"):
            return InterfaceType.VPN_TUNNEL
        elif name.startswith("pdp_ip"):
            return InterfaceType.CELLULAR

        # Default fallback for en0/en1 on Darwin if hardware_port not identified
        if name == "en0":
            return InterfaceType.WIFI
        elif name.startswith("en"):
            return InterfaceType.ETHERNET

        return InterfaceType.OTHER

    def parse_ifconfig_output(
        self,
        output: str,
        hardware_ports: Optional[Dict[str, Any]] = None,
        primary_name: Optional[str] = None,
    ) -> List[MacNetworkInterface]:
        """Parse raw `/sbin/ifconfig` stdout into strongly typed MacNetworkInterface records."""
        if not output:
            return []

        ports = hardware_ports or {}
        interfaces: List[MacNetworkInterface] = []

        # Split output into interface blocks
        blocks: List[str] = []
        current_block: List[str] = []

        for line in output.splitlines():
            if re.match(r"^[a-zA-Z0-9_]+:\s+flags=", line):
                if current_block:
                    blocks.append("\n".join(current_block))
                    current_block = []
            current_block.append(line)

        if current_block:
            blocks.append("\n".join(current_block))

        for block in blocks:
            lines = block.splitlines()
            if not lines:
                continue

            header_match = re.match(r"^([a-zA-Z0-9_]+):\s+flags=(\d+)<([^>]*)>\s+mtu\s+(\d+)", lines[0])
            if not header_match:
                continue

            name = header_match.group(1)
            flags_str = header_match.group(3)
            flags = [f.strip() for f in flags_str.split(",") if f.strip()]
            mtu = int(header_match.group(4))

            hw_info = ports.get(name, {})
            if isinstance(hw_info, dict):
                hw_port = hw_info.get("port")
                hw_mac = hw_info.get("mac")
            elif isinstance(hw_info, str):
                hw_port = hw_info
                hw_mac = None
            else:
                hw_port = None
                hw_mac = None

            iface_type = self.classify_interface(name, flags, hw_port)

            mac_address: Optional[str] = None
            media: Optional[str] = None
            has_active_status: Optional[bool] = None
            ip_addresses: List[MacIpAddress] = []

            for line in lines[1:]:
                line_str = line.strip()

                # ether / MAC address
                if line_str.startswith("ether "):
                    mac_match = re.search(r"ether\s+([a-fA-F0-9:]+)", line_str)
                    if mac_match:
                        raw_val = mac_match.group(1).lower()
                        # If Darwin unprivileged redacts to dummy 02:00:00:00:00:00, use networksetup mac if available
                        if raw_val == "02:00:00:00:00:00" and hw_mac:
                            mac_address = hw_mac
                        else:
                            mac_address = raw_val

                # media
                elif line_str.startswith("media:"):
                    media = line_str.split("media:", 1)[1].strip()

                # status
                elif line_str.startswith("status:"):
                    status_val = line_str.split("status:", 1)[1].strip().lower()
                    has_active_status = (status_val == "active")

                # inet (IPv4)
                elif line_str.startswith("inet "):
                    # e.g. "inet 192.168.1.13 netmask 0xffffff00 broadcast 192.168.1.255"
                    inet_parts = line_str.split()
                    if len(inet_parts) >= 2:
                        ip_addr = inet_parts[1]
                        netmask: Optional[str] = None
                        bcast: Optional[str] = None
                        if "netmask" in inet_parts:
                            idx = inet_parts.index("netmask")
                            if idx + 1 < len(inet_parts):
                                netmask = inet_parts[idx + 1]
                        if "broadcast" in inet_parts:
                            idx = inet_parts.index("broadcast")
                            if idx + 1 < len(inet_parts):
                                bcast = inet_parts[idx + 1]

                        ip_addresses.append(
                            MacIpAddress(
                                address=ip_addr,
                                family="inet",
                                netmask=netmask,
                                broadcast=bcast,
                                is_loopback=(iface_type == InterfaceType.LOOPBACK),
                            )
                        )

                # inet6 (IPv6)
                elif line_str.startswith("inet6 "):
                    # e.g. "inet6 fe80::b0:dc87:ed66:e14c%en0 prefixlen 64 secured scopeid 0xb"
                    inet_parts = line_str.split()
                    if len(inet_parts) >= 2:
                        ip_addr = inet_parts[1]
                        prefixlen: Optional[int] = None
                        scope: Optional[str] = None
                        if "prefixlen" in inet_parts:
                            idx = inet_parts.index("prefixlen")
                            if idx + 1 < len(inet_parts):
                                try:
                                    prefixlen = int(inet_parts[idx + 1])
                                except ValueError:
                                    prefixlen = None
                        if "scopeid" in inet_parts:
                            idx = inet_parts.index("scopeid")
                            if idx + 1 < len(inet_parts):
                                scope = inet_parts[idx + 1]

                        ip_addresses.append(
                            MacIpAddress(
                                address=ip_addr,
                                family="inet6",
                                prefixlen=prefixlen,
                                scope=scope,
                                is_loopback=(iface_type == InterfaceType.LOOPBACK),
                            )
                        )

            # Determine LinkState
            is_up = "UP" in flags
            if not is_up:
                link_state = LinkState.DOWN
            elif has_active_status is True:
                link_state = LinkState.UP_ACTIVE
            elif has_active_status is False:
                link_state = LinkState.UP_INACTIVE
            else:
                # No status line reported (e.g. lo0 or point-to-point tunnels)
                link_state = LinkState.UP_ACTIVE if is_up else LinkState.DOWN

            anon_mac = self.anonymize_mac(mac_address) if mac_address else None

            interfaces.append(
                MacNetworkInterface(
                    name=name,
                    hardware_port=hw_port,
                    interface_type=iface_type,
                    link_state=link_state,
                    mtu=mtu,
                    mac_address=mac_address,
                    anonymized_mac_hash=anon_mac,
                    ip_addresses=ip_addresses,
                    flags=flags,
                    is_primary=(name == primary_name),
                    media=media,
                )
            )

        return interfaces

    def parse_scutil_nwi(self, output: str) -> Tuple[Optional[str], bool]:
        """Parse primary interface and reachability from `scutil --nwi`."""
        primary_name: Optional[str] = None
        is_reachable = False

        if not output:
            return None, False

        # Match "Network interfaces: en0"
        match = re.search(r"Network interfaces:\s*([a-zA-Z0-9_]+)", output)
        if match:
            primary_name = match.group(1).strip()

        # Match "REACH : flags 0x00000002 (Reachable)"
        if "Reachable" in output and "0x00000002" in output:
            is_reachable = True

        return primary_name, is_reachable

    def parse_scutil_dns(self, output: str) -> Tuple[List[str], List[str]]:
        """Parse DNS nameservers and search domains from `scutil --dns`."""
        dns_servers: List[str] = []
        search_domains: List[str] = []

        if not output:
            return dns_servers, search_domains

        for line in output.splitlines():
            line = line.strip()
            # nameserver[0] : 192.168.1.1
            ns_match = re.search(r"nameserver\[\d+\]\s*:\s*([a-fA-F0-9\.:]+)", line)
            if ns_match:
                server = ns_match.group(1).strip()
                if server not in dns_servers:
                    dns_servers.append(server)

            # search domain[0] : domain.name
            sd_match = re.search(r"search domain\[\d+\]\s*:\s*([a-zA-Z0-9\.\-_]+)", line)
            if sd_match:
                dom = sd_match.group(1).strip()
                if dom not in search_domains:
                    search_domains.append(dom)

        return dns_servers, search_domains

    def parse_default_gateway(self, output: str) -> Optional[str]:
        """Parse default IPv4 gateway from `netstat -nr -f inet`."""
        if not output:
            return None

        for line in output.splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[0] == "default":
                return parts[1].strip()

        return None

    def detect(
        self,
        use_mock: bool = False,
        mock_adapter: Optional[Any] = None,
    ) -> MacNetworkReport:
        """Collect network interfaces, link states, routing, and DNS telemetry."""
        if use_mock:
            return self._detect_via_mock(mock_adapter)

        if platform.system() != "Darwin":
            logger.info("Non-Darwin platform detected; returning mock fallback.")
            return self._detect_via_mock(mock_adapter)

        return self._detect_via_darwin()

    def _detect_via_darwin(self) -> MacNetworkReport:
        """Execute unprivileged ifconfig, networksetup, scutil, and netstat commands."""
        unavailable: List[str] = []
        warnings: List[str] = []

        hardware_ports: Dict[str, str] = {}
        primary_name: Optional[str] = None
        is_online = False
        dns_servers: List[str] = []
        search_domains: List[str] = []
        default_gw: Optional[str] = None
        ifconfig_out = ""

        # 1. Query networksetup -listallhardwareports
        try:
            ns_proc = subprocess.run(
                ["/usr/sbin/networksetup", "-listallhardwareports"],
                capture_output=True,
                text=True,
                timeout=5.0,
                check=False,
            )
            if ns_proc.returncode == 0:
                hardware_ports = self.parse_hardware_ports(ns_proc.stdout)
            else:
                unavailable.append("/usr/sbin/networksetup -listallhardwareports")
                warnings.append(f"networksetup returned {ns_proc.returncode}")
        except Exception as exc:
            unavailable.append("/usr/sbin/networksetup -listallhardwareports")
            warnings.append(f"Failed to execute networksetup: {exc}")

        # 2. Query scutil --nwi
        try:
            nwi_proc = subprocess.run(
                ["/usr/sbin/scutil", "--nwi"],
                capture_output=True,
                text=True,
                timeout=5.0,
                check=False,
            )
            if nwi_proc.returncode == 0:
                primary_name, is_online = self.parse_scutil_nwi(nwi_proc.stdout)
            else:
                unavailable.append("/usr/sbin/scutil --nwi")
        except Exception as exc:
            unavailable.append("/usr/sbin/scutil --nwi")
            warnings.append(f"Failed to execute scutil --nwi: {exc}")

        # 3. Query scutil --dns
        try:
            dns_proc = subprocess.run(
                ["/usr/sbin/scutil", "--dns"],
                capture_output=True,
                text=True,
                timeout=5.0,
                check=False,
            )
            if dns_proc.returncode == 0:
                dns_servers, search_domains = self.parse_scutil_dns(dns_proc.stdout)
            else:
                unavailable.append("/usr/sbin/scutil --dns")
        except Exception as exc:
            unavailable.append("/usr/sbin/scutil --dns")
            warnings.append(f"Failed to execute scutil --dns: {exc}")

        # 4. Query netstat -nr -f inet for default gateway
        try:
            route_proc = subprocess.run(
                ["/usr/sbin/netstat", "-nr", "-f", "inet"],
                capture_output=True,
                text=True,
                timeout=5.0,
                check=False,
            )
            if route_proc.returncode == 0:
                default_gw = self.parse_default_gateway(route_proc.stdout)
            else:
                unavailable.append("/usr/sbin/netstat -nr -f inet")
        except Exception as exc:
            unavailable.append("/usr/sbin/netstat -nr -f inet")
            warnings.append(f"Failed to execute netstat: {exc}")

        # 5. Query /sbin/ifconfig
        try:
            ifc_proc = subprocess.run(
                ["/sbin/ifconfig"],
                capture_output=True,
                text=True,
                timeout=5.0,
                check=False,
            )
            if ifc_proc.returncode == 0:
                ifconfig_out = ifc_proc.stdout
            else:
                unavailable.append("/sbin/ifconfig")
                warnings.append(f"ifconfig returned code {ifc_proc.returncode}")
        except Exception as exc:
            unavailable.append("/sbin/ifconfig")
            warnings.append(f"Failed to execute ifconfig: {exc}")

        interfaces = self.parse_ifconfig_output(ifconfig_out, hardware_ports, primary_name)

        # Fallback for primary interface if scutil didn't resolve
        if not primary_name:
            for iface in interfaces:
                if iface.link_state == LinkState.UP_ACTIVE and iface.interface_type != InterfaceType.LOOPBACK:
                    primary_name = iface.name
                    break

        return MacNetworkReport(
            interfaces=interfaces,
            primary_interface_name=primary_name,
            is_online=is_online or bool(default_gw),
            default_gateway=default_gw,
            dns_servers=dns_servers,
            search_domains=search_domains,
            collected_at_epoch_secs=time.time(),
            collection_method="NATIVE_DARWIN_IFCONFIG_SCUTIL_NETSTAT",
            unavailable_telemetry=unavailable,
            warnings=warnings,
        )

    def _detect_via_mock(self, mock_adapter: Optional[Any] = None) -> MacNetworkReport:
        """Generate deterministic simulated network telemetry report."""
        anon_mac = self.anonymize_mac("ca:01:8c:90:8c:35")

        lo_ip = MacIpAddress(
            address="127.0.0.1",
            family="inet",
            netmask="0xff000000",
            is_loopback=True,
        )
        lo_ip6 = MacIpAddress(
            address="::1",
            family="inet6",
            prefixlen=128,
            is_loopback=True,
        )

        lo0 = MacNetworkInterface(
            name="lo0",
            hardware_port="Loopback",
            interface_type=InterfaceType.LOOPBACK,
            link_state=LinkState.UP_ACTIVE,
            mtu=16384,
            mac_address=None,
            anonymized_mac_hash=None,
            ip_addresses=[lo_ip, lo_ip6],
            flags=["UP", "LOOPBACK", "RUNNING", "MULTICAST"],
            is_primary=False,
            media=None,
        )

        en0_ip4 = MacIpAddress(
            address="192.168.1.100",
            family="inet",
            netmask="0xffffff00",
            broadcast="192.168.1.255",
            is_loopback=False,
        )
        en0_ip6 = MacIpAddress(
            address="fe80::b0:dc87:ed66:e14c",
            family="inet6",
            prefixlen=64,
            scope="0xb",
            is_loopback=False,
        )

        en0 = MacNetworkInterface(
            name="en0",
            hardware_port="Wi-Fi",
            interface_type=InterfaceType.WIFI,
            link_state=LinkState.UP_ACTIVE,
            mtu=1500,
            mac_address="ca:01:8c:90:8c:35",
            anonymized_mac_hash=anon_mac,
            ip_addresses=[en0_ip4, en0_ip6],
            flags=["UP", "BROADCAST", "SMART", "RUNNING", "SIMPLEX", "MULTICAST"],
            is_primary=True,
            media="autoselect",
        )

        return MacNetworkReport(
            interfaces=[lo0, en0],
            primary_interface_name="en0",
            is_online=True,
            default_gateway="192.168.1.1",
            dns_servers=["1.1.1.1", "8.8.8.8"],
            search_domains=["local"],
            collected_at_epoch_secs=time.time(),
            collection_method="MOCK_PLATFORM_ADAPTER",
            unavailable_telemetry=[],
            warnings=[],
        )
