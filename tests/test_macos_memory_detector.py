"""Comprehensive unit, contract, and integration tests for macOS Memory Telemetry and Pressure Detection."""

from __future__ import annotations

import json
from pathlib import Path
import platform
import subprocess
import sys
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent

from system_mind.macos.memory_detector import MacMemoryDetector, _parse_size_to_bytes
from system_mind.macos.memory_models import (
    MacMemoryBreakdown,
    MacMemoryTelemetryReport,
    MacSwapUsage,
    MacVmPageStats,
    MemoryPressureLevel,
)
from system_mind.packaging.macos_memory import (
    MacOsMemoryAuditResult,
    MacOsMemoryValidator,
)
from system_mind.platform.adapter import (
    MockPlatformAdapter,
    MockPlatformProfileFactory,
)


def test_macos_memory_detector_mock_mode():
    """Verify memory detection using MockPlatformAdapter generates consistent telemetry."""
    mock = MockPlatformProfileFactory.create_macos_apple_silicon_mock()
    report = MacMemoryDetector.detect(mock_adapter=mock)

    assert isinstance(report, MacMemoryTelemetryReport)
    assert report.collection_method == "MOCK_PLATFORM_ADAPTER"
    assert report.collected_at_epoch_secs > 0

    mem = report.memory_info
    assert isinstance(mem, MacMemoryBreakdown)
    assert mem.total_physical_bytes > 0
    assert mem.app_memory_bytes > 0
    assert mem.wired_memory_bytes > 0
    assert mem.compressed_memory_bytes > 0

    # Invariant: Activity Monitor total used = app + wired + compressed
    expected_used = mem.app_memory_bytes + mem.wired_memory_bytes + mem.compressed_memory_bytes
    assert mem.total_used_bytes == expected_used
    assert mem.total_used_bytes <= mem.total_physical_bytes
    assert 0.0 <= mem.used_percent <= 100.0

    # Invariant: swap usage and encryption
    assert mem.swap.total_bytes > 0
    assert mem.swap.is_encrypted is True
    assert mem.pressure_level == MemoryPressureLevel.NORMAL

    # Page stats validation
    assert report.page_stats.page_size_bytes == 16384
    assert report.page_stats.pages_free > 0


def test_macos_memory_detector_live_on_darwin():
    """Verify live detection gathers valid memory facts when executing on native Darwin macOS host."""
    if platform.system() != "Darwin":
        pytest.skip("Test requires native macOS Darwin host")

    report = MacMemoryDetector.detect()

    assert isinstance(report, MacMemoryTelemetryReport)
    assert report.collection_method == "NATIVE_DARWIN_SYSCTL_VMSTAT"
    assert report.collected_at_epoch_secs > 0

    mem = report.memory_info
    assert mem.total_physical_bytes >= 1024 * 1024 * 1024  # At least 1GB
    assert mem.app_memory_bytes >= 0
    assert mem.wired_memory_bytes >= 0
    assert mem.compressed_memory_bytes >= 0
    assert mem.total_used_bytes == mem.app_memory_bytes + mem.wired_memory_bytes + mem.compressed_memory_bytes
    assert mem.cached_files_bytes >= 0
    assert mem.free_bytes >= 0
    assert 0.0 <= mem.used_percent <= 100.0

    # Dynamic swap is encrypted on modern macOS
    assert mem.swap.is_encrypted is True
    assert mem.pressure_level in (MemoryPressureLevel.NORMAL, MemoryPressureLevel.WARN, MemoryPressureLevel.CRITICAL)


def test_vm_stat_parser_edge_cases():
    """Verify Darwin vm_stat text output parsing across different page sizes and quoting styles."""
    sample_raw = """Mach Virtual Memory Statistics: (page size of 16384 bytes)
Pages free:                                     5000.
Pages active:                                 100000.
Pages inactive:                                80000.
Pages speculative:                              1000.
Pages throttled:                                   0.
Pages wired down:                              50000.
Pages purgeable:                                2000.
"Translation faults":                      100000000.
Pages copy-on-write:                         5000000.
Pages zero filled:                          40000000.
Pages reactivated:                          10000000.
Pages purged:                                1000000.
File-backed pages:                             60000.
Anonymous pages:                              120000.
Pages stored in compressor:                   150000.
Pages occupied by compressor:                  80000.
Decompressions:                             20000000.
Compressions:                               25000000.
Pageins:                                    10000000.
Pageouts:                                     200000.
Swapins:                                      100000.
Swapouts:                                     200000.
"""
    stats = MacMemoryDetector.parse_vm_stat(sample_raw)
    assert stats.page_size_bytes == 16384
    assert stats.pages_free == 5000
    assert stats.pages_active == 100000
    assert stats.pages_inactive == 80000
    assert stats.pages_wired_down == 50000
    assert stats.pages_purgeable == 2000
    assert stats.file_backed_pages == 60000
    assert stats.anonymous_pages == 120000
    assert stats.pages_occupied_by_compressor == 80000
    assert stats.pageins == 10000000
    assert stats.swapins == 100000


def test_swapusage_parser():
    """Verify parsing of Darwin sysctl vm.swapusage strings."""
    sample_encrypted = "vm.swapusage: total = 3072.00M  used = 2048.50M  free = 1023.50M  (encrypted)"
    swap_enc = MacMemoryDetector.parse_swapusage(sample_encrypted)
    assert swap_enc.total_bytes == int(3072.00 * 1024 * 1024)
    assert swap_enc.used_bytes == int(2048.50 * 1024 * 1024)
    assert swap_enc.free_bytes == int(1023.50 * 1024 * 1024)
    assert swap_enc.is_encrypted is True

    sample_unencrypted = "vm.swapusage: total = 1.00G  used = 0.00M  free = 1.00G"
    swap_unenc = MacMemoryDetector.parse_swapusage(sample_unencrypted)
    assert swap_unenc.total_bytes == 1024 * 1024 * 1024
    assert swap_unenc.used_bytes == 0
    assert swap_unenc.is_encrypted is False


def test_parse_size_to_bytes_helper():
    """Verify human-readable unit conversion helper."""
    assert _parse_size_to_bytes("1024") == 1024
    assert _parse_size_to_bytes("1K") == 1024
    assert _parse_size_to_bytes("2M") == 2 * 1024 * 1024
    assert _parse_size_to_bytes("4G") == 4 * 1024 * 1024 * 1024
    assert _parse_size_to_bytes("invalid") == 0


def test_non_darwin_fallback_behavior():
    """Verify graceful degradation when queried on non-Darwin platforms."""
    report = MacMemoryDetector._detect_non_darwin_fallback()

    assert isinstance(report, MacMemoryTelemetryReport)
    assert report.collection_method == "GENERIC_NON_DARWIN_FALLBACK"
    assert len(report.unavailable_telemetry) > 0
    assert "hw.memsize" in report.unavailable_telemetry
    assert "vm_stat" in report.unavailable_telemetry
    assert len(report.warnings) > 0
    assert report.memory_info.total_physical_bytes > 0


def test_macos_memory_validator_clean_audit():
    """Verify programmatic packaging validator passes with zero issues."""
    audit = MacOsMemoryValidator.audit()

    assert audit.valid is True, f"Validator found issues: {audit.issues}"
    assert audit.models_valid is True
    assert audit.detector_valid is True
    assert audit.cli_valid is True
    assert audit.math_invariants_valid is True
    assert len(audit.issues) == 0


def test_detect_memory_cli_execution():
    """Verify developer CLI tool executes cleanly in mock, JSON, and check-pressure modes."""
    cli_path = ROOT_DIR / "tools" / "detect_memory.py"
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
    assert data["memory_info"]["total_physical_bytes"] > 0
    assert data["memory_info"]["pressure_level"] == "NORMAL"

    # 2. Test check-pressure mode
    proc_pressure = subprocess.run(
        [sys.executable, str(cli_path), "--mock", "--check-pressure"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=False,
        timeout=5,
    )
    assert proc_pressure.returncode == 0


def test_memory_models_immutability():
    """Verify dataclasses enforce frozen immutability to prevent runtime tampering."""
    stats = MacVmPageStats(page_size_bytes=16384, pages_free=100)
    with pytest.raises(Exception):
        stats.pages_free = 200  # type: ignore

    mem = MacMemoryBreakdown(
        total_physical_bytes=8589934592,
        app_memory_bytes=2000000000,
        wired_memory_bytes=1000000000,
        compressed_memory_bytes=500000000,
        total_used_bytes=3500000000,
        cached_files_bytes=2000000000,
        free_bytes=3089934592,
        used_percent=40.7,
        swap=MacSwapUsage(),
    )
    with pytest.raises(Exception):
        mem.total_used_bytes = 0  # type: ignore
