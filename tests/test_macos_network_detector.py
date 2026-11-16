"""Comprehensive unit, contract, and integration tests for macOS network interface and connectivity telemetry."""

from __future__ import annotations

import json
from pathlib import Path
import platform
import subprocess
import sys
from unittest.mock import patch

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent

from system_mind.macos.network_detector import MacNetworkDetector
from system_mind.macos.network_models import (
    InterfaceType,
    LinkState,
    MacIpAddress,
    MacNetworkInterface,
    MacNetworkReport,
    MacNetworkRoute,
)
from system_mind.packaging.macos_network import (
    MacOsNetworkAuditResult,
    MacOsNetworkValidator,
)
from system_mind.platform.adapter import MockPlatformProfileFactory


@pytest.mark.unit
def test_macos_network_detector_mock_mode() -> None:
    """Verify network detection using MockPlatformAdapter generates consistent network telemetry."""
    detector = MacNetworkDetector()
    mock = MockPlatformProfileFactory.create_macos_apple_silicon_mock()
    report = detector.detect(use_mock=True, mock_adapter=mock)

    assert isinstance(report, MacNetworkReport)
    assert report.collection_method == "MOCK_PLATFORM_ADAPTER"
    assert report.is_online is True
    assert report.primary_interface_name == "en0"
    assert report.default_gateway == "192.168.1.1"
    assert len(report.dns_servers) == 2
    assert "1.1.1.1" in report.dns_servers
    assert len(report.interfaces) == 2

    # Verify lo0
    lo0 = [i for i in report.interfaces if i.name == "lo0"][0]
    assert lo0.interface_type == InterfaceType.LOOPBACK
    assert lo0.link_state == LinkState.UP_ACTIVE
    assert lo0.mtu == 16384
    assert lo0.mac_address is None

    # Verify en0
    en0 = [i for i in report.interfaces if i.name == "en0"][0]
    assert en0.interface_type == InterfaceType.WIFI
    assert en0.link_state == LinkState.UP_ACTIVE
    assert en0.is_primary is True
    assert en0.anonymized_mac_hash is not None
    assert en0.anonymized_mac_hash.startswith("sha256:")
    assert len(en0.anonymized_mac_hash) == 23


@pytest.mark.unit
def test_parse_hardware_ports() -> None:
    """Verify parsing `networksetup -listallhardwareports` blocks."""
    detector = MacNetworkDetector()
    sample_text = (
        "Hardware Port: Ethernet Adapter (en3)\n"
        "Device: en3\n"
        "Ethernet Address: ba:e1:4b:33:4a:53\n"
        "\n"
        "Hardware Port: Wi-Fi\n"
        "Device: en0\n"
        "Ethernet Address: 60:3e:5f:25:a6:b9\n"
        "\n"
        "Hardware Port: Thunderbolt Bridge\n"
        "Device: bridge0\n"
        "Ethernet Address: 36:4b:05:99:53:40\n"
    )

    ports = detector.parse_hardware_ports(sample_text)
    assert "en0" in ports
    assert ports["en0"]["port"] == "Wi-Fi"
    assert ports["en0"]["mac"] == "60:3e:5f:25:a6:b9"

    assert "en3" in ports
    assert ports["en3"]["port"] == "Ethernet Adapter (en3)"

    assert "bridge0" in ports
    assert ports["bridge0"]["port"] == "Thunderbolt Bridge"


@pytest.mark.unit
def test_parse_ifconfig_output() -> None:
    """Verify parsing `/sbin/ifconfig` stdout across loopback, Wi-Fi, AWDL, and tunnels."""
    detector = MacNetworkDetector()

    sample_ifconfig = (
        "lo0: flags=8049<UP,LOOPBACK,RUNNING,MULTICAST> mtu 16384\n"
        "\toptions=1203<RXCSUM,TXCSUM,TXSTATUS,SW_TIMESTAMP>\n"
        "\tinet 127.0.0.1 netmask 0xff000000\n"
        "\tinet6 ::1 prefixlen 128\n"
        "en0: flags=8863<UP,BROADCAST,SMART,RUNNING,SIMPLEX,MULTICAST> mtu 1500\n"
        "\toptions=6460<TSO4,TSO6,CHANNEL_IO,PARTIAL_CSUM,ZEROINVERT_CSUM>\n"
        "\tether 60:3e:5f:25:a6:b9\n"
        "\tinet 192.168.1.13 netmask 0xffffff00 broadcast 192.168.1.255\n"
        "\tmedia: autoselect\n"
        "\tstatus: active\n"
        "awdl0: flags=8863<UP,BROADCAST,SMART,RUNNING,SIMPLEX,MULTICAST> mtu 1500\n"
        "\tether 12:4c:92:b4:17:10\n"
        "\tstatus: active\n"
        "utun0: flags=8051<UP,POINTOPOINT,RUNNING,MULTICAST> mtu 1380\n"
        "\tinet6 fe80::8532:ee34:c569:1091%utun0 prefixlen 64 scopeid 0xf\n"
    )

    hardware_ports = {
        "en0": {"port": "Wi-Fi", "mac": "60:3e:5f:25:a6:b9"},
    }

    ifaces = detector.parse_ifconfig_output(sample_ifconfig, hardware_ports, primary_name="en0")
    assert len(ifaces) == 4

    # lo0
    lo = [i for i in ifaces if i.name == "lo0"][0]
    assert lo.interface_type == InterfaceType.LOOPBACK
    assert lo.link_state == LinkState.UP_ACTIVE
    assert len(lo.ip_addresses) == 2
    assert lo.ip_addresses[0].address == "127.0.0.1"
    assert lo.ip_addresses[0].is_loopback is True

    # en0
    en = [i for i in ifaces if i.name == "en0"][0]
    assert en.interface_type == InterfaceType.WIFI
    assert en.link_state == LinkState.UP_ACTIVE
    assert en.is_primary is True
    assert en.mac_address == "60:3e:5f:25:a6:b9"
    assert en.anonymized_mac_hash is not None
    assert en.anonymized_mac_hash.startswith("sha256:")
    assert len(en.ip_addresses) == 1
    assert en.ip_addresses[0].address == "192.168.1.13"
    assert en.ip_addresses[0].netmask == "0xffffff00"
    assert en.ip_addresses[0].broadcast == "192.168.1.255"

    # awdl0
    aw = [i for i in ifaces if i.name == "awdl0"][0]
    assert aw.interface_type == InterfaceType.AWDL
    assert aw.link_state == LinkState.UP_ACTIVE

    # utun0
    ut = [i for i in ifaces if i.name == "utun0"][0]
    assert ut.interface_type == InterfaceType.VPN_TUNNEL
    assert ut.link_state == LinkState.UP_ACTIVE
    assert ut.mtu == 1380


@pytest.mark.unit
def test_parse_scutil_nwi_and_dns() -> None:
    """Verify parsing `scutil --nwi` reachability and `scutil --dns` nameservers."""
    detector = MacNetworkDetector()

    nwi_sample = (
        "Network information\n"
        "IPv4 network interface information\n"
        "     en0 : flags      : 0x7 (IPv4,IPv6,DNS)\n"
        "           address    : 192.168.1.13\n"
        "           reach      : 0x00000002 (Reachable)\n"
        "   REACH : flags 0x00000002 (Reachable)\n"
        "Network interfaces: en0\n"
    )
    primary, reachable = detector.parse_scutil_nwi(nwi_sample)
    assert primary == "en0"
    assert reachable is True

    dns_sample = (
        "DNS configuration\n"
        "resolver #1\n"
        "  search domain[0] : home.lan\n"
        "  nameserver[0] : 192.168.1.1\n"
        "  nameserver[1] : 1.1.1.1\n"
        "  if_index : 11 (en0)\n"
    )
    servers, domains = detector.parse_scutil_dns(dns_sample)
    assert "192.168.1.1" in servers
    assert "1.1.1.1" in servers
    assert "home.lan" in domains


@pytest.mark.unit
def test_parse_default_gateway() -> None:
    """Verify parsing default route from `netstat -nr -f inet`."""
    detector = MacNetworkDetector()

    netstat_sample = (
        "Routing tables\n"
        "Internet:\n"
        "Destination        Gateway            Flags               Netif Expire\n"
        "default            192.168.1.1        UGScg                 en0\n"
        "127                127.0.0.1          UCS                   lo0\n"
        "127.0.0.1          127.0.0.1          UH                    lo0\n"
    )
    gw = detector.parse_default_gateway(netstat_sample)
    assert gw == "192.168.1.1"


@pytest.mark.unit
def test_privacy_mac_anonymization_invariant() -> None:
    """Verify hardware MAC addresses are strictly hashed into salted SHA-256 digests (INV-NET-02)."""
    detector = MacNetworkDetector()
    raw_mac = "60:3e:5f:25:a6:b9"

    hashed1 = detector.anonymize_mac(raw_mac)
    hashed2 = detector.anonymize_mac(raw_mac)

    assert hashed1 is not None
    assert raw_mac not in hashed1
    assert hashed1.startswith("sha256:")
    assert len(hashed1) == 23
    assert hashed1 == hashed2  # Deterministic

    # Custom salt produces different digest
    detector_custom = MacNetworkDetector(salt="other-salt:")
    assert detector_custom.anonymize_mac(raw_mac) != hashed1

    # Empty and None handling
    assert detector.anonymize_mac(None) is None
    assert detector.anonymize_mac("") is None
    assert detector.anonymize_mac("   ") is None


@pytest.mark.unit
def test_non_darwin_fallback_behavior() -> None:
    """Verify graceful fallback to mock report when executed on non-Darwin platforms (INV-NET-05)."""
    detector = MacNetworkDetector()
    with patch("platform.system", return_value="Linux"):
        report = detector.detect()
        assert isinstance(report, MacNetworkReport)
        assert report.collection_method == "MOCK_PLATFORM_ADAPTER"
        assert len(report.interfaces) >= 2


@pytest.mark.integration
def test_macos_network_detector_live_on_darwin() -> None:
    """Verify live detection executes safely and gathers valid facts on native macOS Darwin host."""
    if platform.system() != "Darwin":
        pytest.skip("Test requires native macOS Darwin host")

    detector = MacNetworkDetector()
    report = detector.detect()

    assert isinstance(report, MacNetworkReport)
    assert report.collection_method == "NATIVE_DARWIN_IFCONFIG_SCUTIL_NETSTAT"
    assert len(report.interfaces) >= 1

    # lo0 must always be present on Darwin
    lo_matches = [i for i in report.interfaces if i.name == "lo0"]
    assert len(lo_matches) == 1
    lo = lo_matches[0]
    assert lo.interface_type == InterfaceType.LOOPBACK
    assert lo.link_state == LinkState.UP_ACTIVE

    if report.primary_interface_name:
        primary = [i for i in report.interfaces if i.name == report.primary_interface_name]
        assert len(primary) == 1
        assert primary[0].is_primary is True
        assert primary[0].link_state == LinkState.UP_ACTIVE


@pytest.mark.contract
def test_macos_network_validator_clean_audit() -> None:
    """Verify programmatic packaging validator audits network components with zero issues in CI."""
    audit = MacOsNetworkValidator.audit()

    assert audit.valid is True, f"Validator found issues: {audit.issues}"
    assert audit.models_valid is True
    assert audit.detector_valid is True
    assert audit.cli_valid is True
    assert audit.privacy_valid is True
    assert len(audit.issues) == 0


@pytest.mark.integration
def test_detect_network_cli_execution() -> None:
    """Verify developer CLI tool executes cleanly in mock, JSON, and assertion modes."""
    cli_path = ROOT_DIR / "tools" / "detect_network.py"
    assert cli_path.exists()

    # 1. Test mock with JSON
    proc = subprocess.run(
        [sys.executable, str(cli_path), "--mock", "--json"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=False,
        timeout=5,
    )
    assert proc.returncode == 0, f"CLI mock failed: {proc.stderr}"
    data = json.loads(proc.stdout)
    assert data["collection_method"] == "MOCK_PLATFORM_ADAPTER"
    assert data["is_online"] is True
    assert data["primary_interface_name"] == "en0"
    assert len(data["interfaces"]) == 2

    # 2. Test mock human-readable output
    proc_human = subprocess.run(
        [sys.executable, str(cli_path), "--mock"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=False,
        timeout=5,
    )
    assert proc_human.returncode == 0
    assert "SYSTEM MIND X — macOS Network Interfaces & Connectivity Telemetry" in proc_human.stdout
    assert "MOCK_PLATFORM_ADAPTER" in proc_human.stdout

    # 3. Test assertion gates
    proc_assert_online = subprocess.run(
        [sys.executable, str(cli_path), "--mock", "--assert-online"],
        capture_output=True,
        text=True,
        shell=False,
        timeout=5,
    )
    assert proc_assert_online.returncode == 0

    proc_assert_iface = subprocess.run(
        [sys.executable, str(cli_path), "--mock", "--assert-interface", "en0"],
        capture_output=True,
        text=True,
        shell=False,
        timeout=5,
    )
    assert proc_assert_iface.returncode == 0


@pytest.mark.unit
def test_network_models_immutability() -> None:
    """Verify network models enforce frozen immutability."""
    report = MacNetworkReport(
        is_online=True,
        primary_interface_name="en0",
    )

    with pytest.raises((TypeError, AttributeError)):
        report.is_online = False  # type: ignore[misc]
