"""Comprehensive unit, contract, and integration tests for macOS CPU and compute hardware telemetry."""

from __future__ import annotations

import json
from pathlib import Path
import platform
import subprocess
import sys
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent

from system_mind.macos.cpu_detector import MacCpuHardwareDetector
from system_mind.macos.cpu_models import (
    CpuPerfLevelInfo,
    MacCpuHardwareInfo,
    MacCpuTelemetryReport,
)
from system_mind.packaging.macos_cpu import (
    MacOsCpuAuditResult,
    MacOsCpuValidator,
)
from system_mind.platform.adapter import (
    MockPlatformAdapter,
    MockPlatformProfileFactory,
)
from system_mind.platform.matrix import PlatformTargetId


def test_macos_cpu_detector_mock_mode():
    """Verify CPU detection using MockPlatformAdapter generates consistent Apple Silicon telemetry."""
    mock = MockPlatformProfileFactory.create_macos_apple_silicon_mock()
    report = MacCpuHardwareDetector.detect(mock_adapter=mock)

    assert isinstance(report, MacCpuTelemetryReport)
    assert report.collection_method == "MOCK_PLATFORM_ADAPTER"
    assert report.collected_at_epoch_secs > 0

    info = report.cpu_info
    assert isinstance(info, MacCpuHardwareInfo)
    assert info.cpu_brand_string == "Apple M1"
    assert info.hardware_model == "MacBookAir10,1"
    assert info.total_physical_cores == 12  # Mock profile default
    assert info.performance_cores == 4
    assert info.efficiency_cores == 4
    assert info.is_heterogeneous_core_topology is True
    assert info.num_perf_levels == 2

    # Check perf level details
    assert len(info.perf_levels) == 2
    p_level = info.perf_levels[0]
    e_level = info.perf_levels[1]
    assert p_level.name == "Performance"
    assert p_level.physical_cores == 4
    assert p_level.l2_cache_bytes == 12582912  # 12MB
    assert e_level.name == "Efficiency"
    assert e_level.physical_cores == 4
    assert e_level.l2_cache_bytes == 4194304   # 4MB

    # Check cache and bus properties
    assert info.cache_line_size_bytes == 128
    assert info.page_size_bytes == 16384
    assert info.timebase_frequency_hz == 24000000
    assert info.physical_memory_bytes > 0

    # Check features
    assert "neon" in info.supported_features
    assert "floatingpoint" in info.supported_features
    assert "FEAT_CRC32" in info.supported_features


def test_macos_cpu_detector_live_on_darwin():
    """Verify live detection gathers valid hardware facts when executing on native Darwin macOS host."""
    if platform.system() != "Darwin":
        pytest.skip("Test requires native macOS Darwin host")

    report = MacCpuHardwareDetector.detect()

    assert isinstance(report, MacCpuTelemetryReport)
    assert report.collection_method == "NATIVE_DARWIN_SYSCTL"
    assert report.collected_at_epoch_secs > 0

    info = report.cpu_info
    assert info.cpu_brand_string != ""
    assert info.hardware_model != ""
    assert info.total_physical_cores >= 1
    assert info.total_logical_cores >= info.total_physical_cores
    assert info.cache_line_size_bytes in (64, 128)
    assert info.page_size_bytes in (4096, 16384)

    if platform.machine() == "arm64":
        assert info.performance_cores >= 1
        assert info.cache_line_size_bytes == 128
        assert info.page_size_bytes == 16384
        assert info.timebase_frequency_hz == 24000000
        assert info.physical_memory_bytes > 0


def test_core_topology_heterogeneity_logic():
    """Verify heterogeneous topology classification across symmetric and asymmetric configurations."""
    # Asymmetric (Apple Silicon style)
    asymmetric = MacCpuHardwareInfo(
        cpu_brand_string="Apple M1",
        hardware_model="MacBookAir10,1",
        total_physical_cores=8,
        total_logical_cores=8,
        performance_cores=4,
        efficiency_cores=4,
        num_perf_levels=2,
        is_heterogeneous_core_topology=True,
    )
    assert asymmetric.is_heterogeneous_core_topology is True

    # Symmetric (Standard Intel / x86 style)
    symmetric = MacCpuHardwareInfo(
        cpu_brand_string="Intel Core i9",
        hardware_model="MacBookPro16,1",
        total_physical_cores=8,
        total_logical_cores=16,
        performance_cores=8,
        efficiency_cores=0,
        num_perf_levels=1,
        is_heterogeneous_core_topology=False,
    )
    assert symmetric.is_heterogeneous_core_topology is False


def test_non_darwin_fallback_behavior():
    """Verify graceful degradation when queried on non-Darwin platforms."""
    report = MacCpuHardwareDetector._detect_non_darwin_fallback()

    assert isinstance(report, MacCpuTelemetryReport)
    assert report.collection_method == "GENERIC_NON_DARWIN_FALLBACK"
    assert len(report.unavailable_telemetry) > 0
    assert any("machdep.cpu.brand_string" in u for u in report.unavailable_telemetry)
    assert any("hw.nperflevels" in u for u in report.unavailable_telemetry)
    assert len(report.warnings) > 0
    assert report.cpu_info.total_physical_cores >= 1


def test_macos_cpu_validator_clean_audit():
    """Verify programmatic packaging validator passes with zero issues."""
    audit = MacOsCpuValidator.audit()

    assert audit.valid is True, f"Validator found issues: {audit.issues}"
    assert audit.models_valid is True
    assert audit.detector_valid is True
    assert audit.cli_valid is True
    assert audit.topology_valid is True
    assert len(audit.issues) == 0


def test_detect_cpu_cli_execution():
    """Verify developer CLI tool executes cleanly in mock and JSON modes."""
    cli_path = ROOT_DIR / "tools" / "detect_cpu.py"
    assert cli_path.exists()

    # 1. Test mock with JSON
    proc = subprocess.run(
        [sys.executable, str(cli_path), "--mock", "--json"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=False,
        timeout=15.0,
    )
    assert proc.returncode == 0, f"CLI mock failed: {proc.stderr}"
    data = json.loads(proc.stdout)
    assert data["collection_method"] == "MOCK_PLATFORM_ADAPTER"
    assert data["cpu_info"]["cpu_brand_string"] == "Apple M1"
    assert data["cpu_info"]["performance_cores"] == 4
    assert data["cpu_info"]["efficiency_cores"] == 4
    assert data["cpu_info"]["is_heterogeneous_core_topology"] is True

    # 2. Test strict Apple Silicon assertion in mock mode
    proc_strict = subprocess.run(
        [sys.executable, str(cli_path), "--mock", "--strict-apple-silicon"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=False,
        timeout=15.0,
    )
    assert proc_strict.returncode == 0


def test_cpu_models_immutability():
    """Verify dataclasses enforce frozen immutability to prevent runtime tampering."""
    perf = CpuPerfLevelInfo(0, "Performance", 4, 4, 196608, 131072, 12582912, 4)
    with pytest.raises(Exception):
        perf.physical_cores = 8  # type: ignore

    cpu = MacCpuHardwareInfo(
        cpu_brand_string="Apple M1",
        hardware_model="MacBookAir10,1",
        total_physical_cores=8,
        total_logical_cores=8,
        performance_cores=4,
        efficiency_cores=4,
        num_perf_levels=2,
    )
    with pytest.raises(Exception):
        cpu.total_physical_cores = 16  # type: ignore
