"""Comprehensive unit, contract, and integration tests for macOS GPU and display inventory telemetry."""

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

from system_mind.macos.gpu_detector import MacGpuDetector
from system_mind.macos.gpu_models import (
    DisplayConnectionType,
    GpuBusType,
    MacDisplayInfo,
    MacGpuInfo,
    MacGpuReport,
)
from system_mind.packaging.macos_gpu import (
    MacOsGpuAuditResult,
    MacOsGpuValidator,
)
from system_mind.platform.adapter import MockPlatformProfileFactory


@pytest.mark.unit
def test_macos_gpu_detector_mock_mode() -> None:
    """Verify GPU and display detection using safe MockPlatformAdapter."""
    detector = MacGpuDetector()
    mock = MockPlatformProfileFactory.create_macos_apple_silicon_mock()
    report = detector.detect(use_mock=True, mock_adapter=mock)

    assert isinstance(report, MacGpuReport)
    assert report.collection_method == "MOCK_PLATFORM_ADAPTER"
    assert report.total_gpu_count == 1
    assert report.total_display_count == 1
    assert report.has_builtin_display is True
    assert report.has_external_display is False
    assert report.primary_display_resolution == "1440 x 900 @ 60.00Hz"

    gpu = report.gpus[0]
    assert gpu.name == "Apple M1"
    assert gpu.vendor == "Apple"
    assert gpu.core_count == 8
    assert gpu.bus_type == GpuBusType.BUILTIN
    assert gpu.metal_support == "spdisplays_metal4"
    assert gpu.device_type == "spdisplays_gpu"
    assert gpu.vram_text == "Unified Memory"

    display = gpu.displays[0]
    assert display.name == "Color LCD"
    assert display.display_id == "1"
    assert display.vendor_id == "610"
    assert display.product_id == "a045"
    assert display.native_pixels == "2880 x 1800"
    assert display.resolution == "1440 x 900 @ 60.00Hz"
    assert display.ui_resolution == "1440 x 900"
    assert display.refresh_rate_hz == 60.0
    assert display.is_main is True
    assert display.is_builtin is True
    assert display.is_online is True
    assert display.is_mirror is False
    assert display.connection_type == DisplayConnectionType.INTERNAL
    assert display.pixel_density_retina is True
    assert display.ambient_brightness is True

    # Check INV-GPU-02 anonymized serial format
    assert display.anonymized_serial_hash is not None
    assert display.anonymized_serial_hash.startswith("sha256:")
    assert len(display.anonymized_serial_hash) == 23


@pytest.mark.unit
def test_parse_spdisplays_json_apple_silicon() -> None:
    """Verify parsing realistic SPDisplaysDataType JSON from Apple Silicon M1 workstation."""
    detector = MacGpuDetector()
    sample_data = {
        "SPDisplaysDataType": [
            {
                "_name": "kHW_AppleM1Item",
                "spdisplays_mtlgpufamilysupport": "spdisplays_metal4",
                "spdisplays_ndrvs": [
                    {
                        "_name": "Color LCD",
                        "_spdisplays_display-product-id": "a045",
                        "_spdisplays_display-serial-number": "fd626d62",
                        "_spdisplays_display-vendor-id": "610",
                        "_spdisplays_displayID": "1",
                        "_spdisplays_pixels": "2880 x 1800",
                        "_spdisplays_resolution": "1440 x 900 @ 60.00Hz",
                        "spdisplays_ambient_brightness": "spdisplays_yes",
                        "spdisplays_connection_type": "spdisplays_internal",
                        "spdisplays_display_type": "spdisplays_built-in_retinaLCD",
                        "spdisplays_main": "spdisplays_yes",
                        "spdisplays_mirror": "spdisplays_off",
                        "spdisplays_online": "spdisplays_yes",
                        "spdisplays_pixelresolution": "spdisplays_2560x1600Retina",
                    }
                ],
                "spdisplays_vendor": "sppci_vendor_Apple",
                "sppci_bus": "spdisplays_builtin",
                "sppci_cores": "7",
                "sppci_device_type": "spdisplays_gpu",
                "sppci_model": "Apple M1",
            }
        ]
    }

    gpus, warnings = detector.parse_spdisplays_json(sample_data)
    assert len(warnings) == 0
    assert len(gpus) == 1

    gpu = gpus[0]
    assert gpu.name == "Apple M1"
    assert gpu.vendor == "Apple"
    assert gpu.core_count == 7
    assert gpu.bus_type == GpuBusType.BUILTIN
    assert gpu.metal_support == "spdisplays_metal4"
    assert gpu.vram_text == "Unified Memory"

    assert len(gpu.displays) == 1
    display = gpu.displays[0]
    assert display.name == "Color LCD"
    assert display.display_id == "1"
    assert display.vendor_id == "610"
    assert display.product_id == "a045"
    assert display.native_pixels == "2880 x 1800"
    assert display.resolution == "1440 x 900 @ 60.00Hz"
    assert display.ui_resolution == "1440 x 900"
    assert display.refresh_rate_hz == 60.0
    assert display.is_main is True
    assert display.is_builtin is True
    assert display.is_online is True
    assert display.is_mirror is False
    assert display.connection_type == DisplayConnectionType.INTERNAL
    assert display.pixel_density_retina is True
    assert display.ambient_brightness is True

    # INV-GPU-02: verify serial anonymization
    assert display.anonymized_serial_hash is not None
    assert display.anonymized_serial_hash.startswith("sha256:")
    assert "fd626d62" not in display.anonymized_serial_hash


@pytest.mark.unit
def test_parse_spdisplays_json_intel_dual_gpu() -> None:
    """Verify parsing multi-GPU setup (Intel integrated + AMD discrete with external monitor)."""
    detector = MacGpuDetector()
    sample_data = {
        "SPDisplaysDataType": [
            {
                "_name": "Intel UHD Graphics 630",
                "spdisplays_mtlgpufamilysupport": "spdisplays_metal3",
                "spdisplays_vendor": "Intel",
                "sppci_bus": "spdisplays_builtin",
                "sppci_device_type": "spdisplays_gpu",
                "sppci_model": "Intel UHD Graphics 630",
                "spdisplays_vram": "1536 MB",
                "spdisplays_ndrvs": [],
            },
            {
                "_name": "AMD Radeon Pro 5500M",
                "spdisplays_mtlgpufamilysupport": "spdisplays_metal3",
                "spdisplays_vendor": "AMD",
                "sppci_bus": "spdisplays_pcie",
                "sppci_cores": "24",
                "sppci_device_type": "spdisplays_gpu",
                "sppci_model": "AMD Radeon Pro 5500M",
                "spdisplays_vram": "4 GB",
                "spdisplays_ndrvs": [
                    {
                        "_name": "Color LCD",
                        "_spdisplays_displayID": "1",
                        "_spdisplays_pixels": "3072 x 1920",
                        "_spdisplays_resolution": "1792 x 1120 @ 60.00Hz",
                        "spdisplays_connection_type": "spdisplays_internal",
                        "spdisplays_display_type": "spdisplays_built-in_retinaLCD",
                        "spdisplays_main": "spdisplays_yes",
                        "spdisplays_online": "spdisplays_yes",
                    },
                    {
                        "_name": "DELL U2720Q",
                        "_spdisplays_displayID": "2",
                        "_spdisplays_pixels": "3840 x 2160",
                        "_spdisplays_resolution": "2560 x 1440 @ 60.00Hz",
                        "spdisplays_connection_type": "spdisplays_displayport",
                        "spdisplays_display_type": "spdisplays_external",
                        "spdisplays_main": "spdisplays_no",
                        "spdisplays_online": "spdisplays_yes",
                    },
                ],
            },
        ]
    }

    gpus, warnings = detector.parse_spdisplays_json(sample_data)
    assert len(gpus) == 2

    intel_gpu = gpus[0]
    assert intel_gpu.name == "Intel UHD Graphics 630"
    assert intel_gpu.bus_type == GpuBusType.BUILTIN
    assert intel_gpu.vram_text == "1536 MB"
    assert len(intel_gpu.displays) == 0

    amd_gpu = gpus[1]
    assert amd_gpu.name == "AMD Radeon Pro 5500M"
    assert amd_gpu.bus_type == GpuBusType.PCIE
    assert amd_gpu.core_count == 24
    assert amd_gpu.vram_text == "4 GB"
    assert len(amd_gpu.displays) == 2

    builtin_disp = amd_gpu.displays[0]
    assert builtin_disp.name == "Color LCD"
    assert builtin_disp.is_builtin is True
    assert builtin_disp.is_main is True
    assert builtin_disp.connection_type == DisplayConnectionType.INTERNAL

    external_disp = amd_gpu.displays[1]
    assert external_disp.name == "DELL U2720Q"
    assert external_disp.is_builtin is False
    assert external_disp.is_main is False
    assert external_disp.connection_type == DisplayConnectionType.DISPLAYPORT


@pytest.mark.unit
def test_parse_refresh_rate() -> None:
    """Verify refresh rate string parsing logic."""
    detector = MacGpuDetector()

    ui, hz = detector.parse_refresh_rate("1440 x 900 @ 60.00Hz")
    assert ui == "1440 x 900"
    assert hz == 60.0

    ui, hz = detector.parse_refresh_rate("2560 x 1440 @ 120.00Hz")
    assert ui == "2560 x 1440"
    assert hz == 120.0

    ui, hz = detector.parse_refresh_rate("3840 x 2160")
    assert ui == "3840 x 2160"
    assert hz is None

    ui, hz = detector.parse_refresh_rate(None)
    assert ui is None
    assert hz is None


@pytest.mark.unit
def test_privacy_display_serial_anonymization_invariant() -> None:
    """Verify INV-GPU-02 display serial anonymization requirements."""
    detector = MacGpuDetector()

    # None and empty return None
    assert detector.anonymize_serial(None) is None
    assert detector.anonymize_serial("") is None
    assert detector.anonymize_serial("   ") is None

    # Valid serial produces 23-char salted sha256 prefix
    serial = "fd626d62"
    anon1 = detector.anonymize_serial(serial)
    assert anon1 is not None
    assert anon1.startswith("sha256:")
    assert len(anon1) == 23

    # Determinism
    anon2 = detector.anonymize_serial(serial)
    assert anon1 == anon2

    # Salt isolation
    detector_alt = MacGpuDetector(salt="different-salt:")
    anon_alt = detector_alt.anonymize_serial(serial)
    assert anon1 != anon_alt


@pytest.mark.unit
def test_non_darwin_fallback_behavior() -> None:
    """Verify that execution on non-Darwin platforms gracefully falls back."""
    detector = MacGpuDetector()

    with patch("platform.system", return_value="Linux"):
        report = detector.detect()
        assert report.collection_method == "NON_DARWIN_MOCK_FALLBACK"
        assert len(report.unavailable_telemetry) > 0
        assert "Darwin" in report.unavailable_telemetry[0]
        assert report.total_gpu_count == 1
        assert report.total_display_count == 1


@pytest.mark.integration
def test_macos_gpu_detector_live_on_darwin() -> None:
    """Verify live macOS GPU and display collection if running on Darwin."""
    if platform.system() != "Darwin":
        pytest.skip("Test requires Darwin macOS host environment")

    detector = MacGpuDetector()
    report = detector.detect()

    assert isinstance(report, MacGpuReport)
    assert report.collection_method in (
        "NATIVE_DARWIN_SYSTEM_PROFILER",
        "MOCK_PLATFORM_ADAPTER",
    )

    # In cloud virtual machine runners (e.g. GitHub Actions macos-latest VMs),
    # there may be 0 physical GPUs/displays attached.
    if report.total_gpu_count >= 1:
        assert report.total_display_count >= 1
        gpu = report.gpus[0]
        assert len(gpu.name) > 0
        assert len(gpu.displays) >= 1
        disp = gpu.displays[0]
        assert len(disp.name) > 0

        if disp.anonymized_serial_hash:
            assert disp.anonymized_serial_hash.startswith("sha256:")
            assert len(disp.anonymized_serial_hash) == 23


@pytest.mark.contract
def test_macos_gpu_validator_clean_audit() -> None:
    """Verify MacOsGpuValidator reports zero issues on repository code."""
    result = MacOsGpuValidator.audit(ROOT_DIR)
    assert isinstance(result, MacOsGpuAuditResult)
    assert result.valid is True
    assert result.models_valid is True
    assert result.detector_valid is True
    assert result.cli_valid is True
    assert result.privacy_valid is True
    assert result.issues == ()


@pytest.mark.contract
def test_detect_gpu_cli_execution() -> None:
    """Verify tools/detect_gpu.py runs cleanly with CLI arguments."""
    cli_path = ROOT_DIR / "tools" / "detect_gpu.py"

    # Test --mock
    proc_mock = subprocess.run(
        [sys.executable, str(cli_path), "--mock"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc_mock.returncode == 0
    assert "SYSTEM MIND X — macOS GPU & Display Inventory Telemetry" in proc_mock.stdout
    assert "Apple M1" in proc_mock.stdout

    # Test --mock --json
    proc_json = subprocess.run(
        [sys.executable, str(cli_path), "--mock", "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc_json.returncode == 0
    data = json.loads(proc_json.stdout)
    assert data["total_gpu_count"] == 1
    assert data["total_display_count"] == 1
    assert data["gpus"][0]["name"] == "Apple M1"

    # Test assertions
    proc_assert_ok = subprocess.run(
        [sys.executable, str(cli_path), "--mock", "--assert-gpu", "--assert-displays", "1"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc_assert_ok.returncode == 0

    proc_assert_fail = subprocess.run(
        [sys.executable, str(cli_path), "--mock", "--assert-displays", "99"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc_assert_fail.returncode == 1


@pytest.mark.unit
def test_gpu_models_immutability() -> None:
    """Verify that all GPU and display telemetry dataclasses are strictly frozen."""
    display = MacDisplayInfo(name="Test Display")
    with pytest.raises(FrozenInstanceError):
        display.name = "Modified Display"  # type: ignore

    gpu = MacGpuInfo(name="Test GPU", displays=[display])
    with pytest.raises(FrozenInstanceError):
        gpu.name = "Modified GPU"  # type: ignore

    report = MacGpuReport(gpus=[gpu])
    with pytest.raises(FrozenInstanceError):
        report.total_gpu_count = 5  # type: ignore


@pytest.mark.unit
def test_classify_bus_and_connection_types() -> None:
    """Verify edge cases for GPU bus and display connection classification."""
    detector = MacGpuDetector()

    assert detector.classify_bus("spdisplays_builtin") == GpuBusType.BUILTIN
    assert detector.classify_bus("Built-in Integrated") == GpuBusType.BUILTIN
    assert detector.classify_bus("spdisplays_pcie") == GpuBusType.PCIE
    assert detector.classify_bus("Thunderbolt 3 eGPU") == GpuBusType.PCIE
    assert detector.classify_bus("virtual_adapter") == GpuBusType.UNKNOWN
    assert detector.classify_bus(None) == GpuBusType.UNKNOWN

    assert detector.classify_connection("spdisplays_internal") == DisplayConnectionType.INTERNAL
    assert detector.classify_connection(None, "spdisplays_built-in_retinaLCD") == DisplayConnectionType.INTERNAL
    assert detector.classify_connection("spdisplays_displayport") == DisplayConnectionType.DISPLAYPORT
    assert detector.classify_connection("spdisplays_hdmi") == DisplayConnectionType.HDMI
    assert detector.classify_connection("spdisplays_thunderbolt") == DisplayConnectionType.THUNDERBOLT
    assert detector.classify_connection("spdisplays_airplay") == DisplayConnectionType.AIRPLAY
    assert detector.classify_connection("custom_pipe") == DisplayConnectionType.UNKNOWN
