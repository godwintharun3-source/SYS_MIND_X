"""Comprehensive unit, contract, and integration tests for macOS USB and peripheral inventory telemetry."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import platform
import subprocess
import sys
from unittest.mock import patch

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent

from system_mind.macos.usb_detector import MacUsbDetector
from system_mind.macos.usb_models import (
    MacUsbController,
    MacUsbDevice,
    MacUsbReport,
    UsbDeviceClass,
    UsbSpeed,
)
from system_mind.packaging.macos_usb import (
    MacOsUsbAuditResult,
    MacOsUsbValidator,
)
from system_mind.platform.adapter import MockPlatformProfileFactory


@pytest.mark.unit
def test_macos_usb_detector_mock_mode() -> None:
    """Verify USB and peripheral detection using safe MockPlatformAdapter."""
    detector = MacUsbDetector()
    mock = MockPlatformProfileFactory.create_macos_apple_silicon_mock()
    report = detector.detect(use_mock=True, mock_adapter=mock)

    assert isinstance(report, MacUsbReport)
    assert report.collection_method == "MOCK_PLATFORM_ADAPTER"
    assert report.total_controller_count == 1
    assert report.total_device_count == 2
    assert report.has_external_devices is False
    assert report.has_security_tokens is False
    assert report.has_mass_storage is False

    ctrl = report.controllers[0]
    assert ctrl.name == "USB 3.1 Bus"
    assert ctrl.host_controller == "AppleSynopsysUSB40XHCI"
    assert len(ctrl.devices) == 2

    kb = ctrl.devices[0]
    assert kb.name == "Apple Internal Keyboard / Trackpad"
    assert kb.vendor_id == "0x05ac"
    assert kb.product_id == "0x027c"
    assert kb.manufacturer == "Apple Inc."
    assert kb.device_class == UsbDeviceClass.HUMAN_INTERFACE
    assert kb.speed == UsbSpeed.FULL_SPEED_12_MBPS
    assert kb.is_builtin is True
    assert kb.is_hub is False
    assert kb.bus_power_ma == 500
    assert kb.current_used_ma == 40
    assert kb.anonymized_serial_hash is not None
    assert kb.anonymized_serial_hash.startswith("sha256:")
    assert len(kb.anonymized_serial_hash) == 23

    cam = ctrl.devices[1]
    assert cam.name == "FaceTime HD Camera"
    assert cam.device_class == UsbDeviceClass.AUDIO_VIDEO
    assert cam.speed == UsbSpeed.HIGH_SPEED_480_MBPS
    assert cam.is_builtin is True


@pytest.mark.unit
def test_parse_spusb_json_apple_silicon_internal() -> None:
    """Verify parsing SPUSBDataType JSON representing Apple Silicon built-in peripherals."""
    detector = MacUsbDetector()
    sample_data = {
        "SPUSBDataType": [
            {
                "_name": "USB 3.1 Bus",
                "host_controller": "AppleSynopsysUSB40XHCI",
                "pci_device": "0x0000",
                "pci_vendor": "0x106b",
                "_items": [
                    {
                        "_name": "Apple Internal Keyboard / Trackpad",
                        "bcd_device": "1.00",
                        "bus_power": "500",
                        "bus_power_used": "40",
                        "extra_current_used": "0",
                        "location_id": "0x01100000 / 1",
                        "manufacturer": "Apple Inc.",
                        "product_id": "0x027c",
                        "serial_num": "FM0123456789",
                        "speed": "up_to_12_mbit_s",
                        "vendor_id": "0x05ac",
                    }
                ],
            }
        ]
    }

    controllers, warnings = detector.parse_spusb_json(sample_data)
    assert len(warnings) == 0
    assert len(controllers) == 1

    ctrl = controllers[0]
    assert ctrl.name == "USB 3.1 Bus"
    assert len(ctrl.devices) == 1

    dev = ctrl.devices[0]
    assert dev.name == "Apple Internal Keyboard / Trackpad"
    assert dev.device_class == UsbDeviceClass.HUMAN_INTERFACE
    assert dev.speed == UsbSpeed.FULL_SPEED_12_MBPS
    assert dev.is_builtin is True
    assert dev.bus_power_ma == 500
    assert dev.current_used_ma == 40
    assert dev.anonymized_serial_hash is not None
    assert dev.anonymized_serial_hash.startswith("sha256:")
    assert "FM0123456789" not in dev.anonymized_serial_hash


@pytest.mark.unit
def test_parse_spusb_json_external_hub_and_devices() -> None:
    """Verify recursive hub traversal, external flags, security tokens, and mass storage detection."""
    detector = MacUsbDetector()
    sample_data = {
        "SPUSBDataType": [
            {
                "_name": "USB 3.1 Bus",
                "host_controller": "AppleSynopsysUSB40XHCI",
                "_items": [
                    {
                        "_name": "4-Port USB 3.0 Hub",
                        "location_id": "0x02100000 / 2",
                        "manufacturer": "Generic",
                        "speed": "up_to_5_gb_s",
                        "_items": [
                            {
                                "_name": "YubiKey 5 NFC",
                                "location_id": "0x02110000 / 3",
                                "manufacturer": "Yubico",
                                "product_id": "0x0407",
                                "serial_num": "12345678",
                                "speed": "up_to_12_mbit_s",
                                "vendor_id": "0x1050",
                            },
                            {
                                "_name": "SanDisk Extreme SSD",
                                "location_id": "0x02120000 / 4",
                                "manufacturer": "SanDisk",
                                "product_id": "0x5583",
                                "serial_num": "SD9988776655",
                                "speed": "up_to_10_gb_s",
                                "vendor_id": "0x0781",
                            },
                        ],
                    }
                ],
            }
        ]
    }

    controllers, warnings = detector.parse_spusb_json(sample_data)
    assert len(controllers) == 1
    ctrl = controllers[0]
    assert len(ctrl.devices) == 1

    hub = ctrl.devices[0]
    assert hub.is_hub is True
    assert hub.device_class == UsbDeviceClass.HUB
    assert len(hub.children) == 2

    # Flattened check
    flat = detector.flatten_devices(ctrl.devices)
    assert len(flat) == 3

    yubi = hub.children[0]
    assert yubi.device_class == UsbDeviceClass.SECURITY_TOKEN
    assert yubi.is_builtin is False
    assert yubi.anonymized_serial_hash is not None
    assert "12345678" not in yubi.anonymized_serial_hash

    ssd = hub.children[1]
    assert ssd.device_class == UsbDeviceClass.MASS_STORAGE
    assert ssd.speed == UsbSpeed.SUPER_SPEED_PLUS_10_GBPS
    assert ssd.is_builtin is False


@pytest.mark.unit
def test_classify_device_and_speed() -> None:
    """Verify peripheral functional classification and signaling speeds."""
    detector = MacUsbDetector()

    # Classes
    assert detector.classify_device("USB Hub", is_hub=True) == UsbDeviceClass.HUB
    assert detector.classify_device("Logitech MX Master 3S Mouse") == UsbDeviceClass.HUMAN_INTERFACE
    assert detector.classify_device("Keychron K2 Mechanical Keyboard") == UsbDeviceClass.HUMAN_INTERFACE
    assert detector.classify_device("YubiKey FIDO", "Yubico") == UsbDeviceClass.SECURITY_TOKEN
    assert detector.classify_device("Cruzer Blade Flash Drive", "SanDisk") == UsbDeviceClass.MASS_STORAGE
    assert detector.classify_device("Shure MV7 Microphone") == UsbDeviceClass.AUDIO_VIDEO
    assert detector.classify_device("Realtek USB 10/100/1000 LAN") == UsbDeviceClass.COMMUNICATIONS
    assert detector.classify_device("Logitech Unifying Receiver") == UsbDeviceClass.WIRELESS
    assert detector.classify_device("HP LaserJet Pro") == UsbDeviceClass.PRINTER
    assert detector.classify_device("Generic Unknown Widget") == UsbDeviceClass.OTHER

    # Speeds
    assert detector.classify_speed("up_to_1.5_mbit_s") == UsbSpeed.LOW_SPEED_1_5_MBPS
    assert detector.classify_speed("up_to_12_mbit_s") == UsbSpeed.FULL_SPEED_12_MBPS
    assert detector.classify_speed("up_to_480_mbit_s") == UsbSpeed.HIGH_SPEED_480_MBPS
    assert detector.classify_speed("up_to_5_gb_s") == UsbSpeed.SUPER_SPEED_5_GBPS
    assert detector.classify_speed("up_to_10_gb_s") == UsbSpeed.SUPER_SPEED_PLUS_10_GBPS
    assert detector.classify_speed("up_to_20_gb_s") == UsbSpeed.SUPER_SPEED_PLUS_20_GBPS
    assert detector.classify_speed("up_to_40_gb_s") == UsbSpeed.USB4_40_GBPS
    assert detector.classify_speed(None) == UsbSpeed.UNKNOWN


@pytest.mark.unit
def test_privacy_usb_serial_anonymization_invariant() -> None:
    """Verify INV-USB-02 peripheral serial anonymization requirements."""
    detector = MacUsbDetector()

    # None and empty return None
    assert detector.anonymize_serial(None) is None
    assert detector.anonymize_serial("") is None
    assert detector.anonymize_serial("   ") is None

    # Valid serial produces 23-char salted sha256 prefix
    serial = "FE0123456789"
    anon1 = detector.anonymize_serial(serial)
    assert anon1 is not None
    assert anon1.startswith("sha256:")
    assert len(anon1) == 23

    # Determinism
    anon2 = detector.anonymize_serial(serial)
    assert anon1 == anon2

    # Salt isolation
    detector_alt = MacUsbDetector(salt="different-salt:")
    anon_alt = detector_alt.anonymize_serial(serial)
    assert anon1 != anon_alt


@pytest.mark.unit
def test_non_darwin_fallback_behavior() -> None:
    """Verify that execution on non-Darwin platforms gracefully falls back."""
    detector = MacUsbDetector()

    with patch("platform.system", return_value="Linux"):
        report = detector.detect()
        assert report.collection_method == "NON_DARWIN_MOCK_FALLBACK"
        assert len(report.unavailable_telemetry) > 0
        assert "Darwin" in report.unavailable_telemetry[0]
        assert report.total_controller_count == 1
        assert report.total_device_count == 2


@pytest.mark.integration
def test_macos_usb_detector_live_on_darwin() -> None:
    """Verify live macOS USB collection if running on Darwin."""
    if platform.system() != "Darwin":
        pytest.skip("Test requires Darwin macOS host environment")

    detector = MacUsbDetector()
    report = detector.detect()

    assert isinstance(report, MacUsbReport)
    assert report.collection_method in (
        "NATIVE_DARWIN_SYSTEM_PROFILER",
        "MOCK_PLATFORM_ADAPTER",
    )
    assert isinstance(report.controllers, list)
    assert isinstance(report.total_controller_count, int)
    assert isinstance(report.total_device_count, int)


@pytest.mark.contract
def test_macos_usb_validator_clean_audit() -> None:
    """Verify MacOsUsbValidator reports zero issues on repository code."""
    result = MacOsUsbValidator.audit(ROOT_DIR)
    assert isinstance(result, MacOsUsbAuditResult)
    assert result.valid is True
    assert result.models_valid is True
    assert result.detector_valid is True
    assert result.cli_valid is True
    assert result.privacy_valid is True
    assert result.issues == ()


@pytest.mark.contract
def test_detect_usb_cli_execution() -> None:
    """Verify tools/detect_usb.py runs cleanly with CLI arguments."""
    cli_path = ROOT_DIR / "tools" / "detect_usb.py"

    # Test --mock
    proc_mock = subprocess.run(
        [sys.executable, str(cli_path), "--mock"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc_mock.returncode == 0
    assert "SYSTEM MIND X — macOS USB & Peripheral Inventory Telemetry" in proc_mock.stdout
    assert "Apple Internal Keyboard / Trackpad" in proc_mock.stdout

    # Test --mock --json
    proc_json = subprocess.run(
        [sys.executable, str(cli_path), "--mock", "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc_json.returncode == 0
    data = json.loads(proc_json.stdout)
    assert data["total_controller_count"] == 1
    assert data["total_device_count"] == 2
    assert data["controllers"][0]["name"] == "USB 3.1 Bus"

    # Test assertions
    proc_assert_ok = subprocess.run(
        [sys.executable, str(cli_path), "--mock", "--assert-usb", "--assert-devices", "2"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc_assert_ok.returncode == 0

    proc_assert_fail = subprocess.run(
        [sys.executable, str(cli_path), "--mock", "--assert-devices", "99"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc_assert_fail.returncode == 1


@pytest.mark.unit
def test_usb_models_immutability() -> None:
    """Verify that all USB telemetry dataclasses are strictly frozen."""
    dev = MacUsbDevice(name="Test USB Device")
    with pytest.raises(FrozenInstanceError):
        dev.name = "Modified Name"  # type: ignore

    ctrl = MacUsbController(name="Test Bus", devices=[dev])
    with pytest.raises(FrozenInstanceError):
        ctrl.name = "Modified Bus"  # type: ignore

    report = MacUsbReport(controllers=[ctrl])
    with pytest.raises(FrozenInstanceError):
        report.total_device_count = 10  # type: ignore


@pytest.mark.unit
def test_parse_current_ma() -> None:
    """Verify electric current parsing."""
    detector = MacUsbDetector()
    assert detector.parse_current_ma(500) == 500
    assert detector.parse_current_ma("500") == 500
    assert detector.parse_current_ma("500 mA") == 500
    assert detector.parse_current_ma("200mA") == 200
    assert detector.parse_current_ma(None) is None
    assert detector.parse_current_ma("unspecified") is None
