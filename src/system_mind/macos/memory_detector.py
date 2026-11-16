"""Read-only macOS memory capacity, VM page statistics, swap, and memory pressure detector.

Gathers total physical memory, Mach virtual memory page allocations (app, wired, compressed,
cached, free), dynamic swap usage, and kernel memory pressure indicators using unprivileged
read-only Darwin sysctl and vm_stat queries in strict compliance with SC-01 and privacy constraints.
"""

from __future__ import annotations

import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from system_mind.macos.memory_models import (
    MacMemoryBreakdown,
    MacMemoryTelemetryReport,
    MacSwapUsage,
    MacVmPageStats,
    MemoryPressureLevel,
)
from system_mind.platform.adapter import MockPlatformAdapter


def _safe_exec(cmd: List[str], timeout: int = 5) -> Tuple[int, str]:
    """Execute a read-only query safely without shell=True in compliance with SC-01."""
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=False,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout.strip()
    except (FileNotFoundError, subprocess.SubprocessError):
        return 127, ""


def _parse_size_to_bytes(val_str: str) -> int:
    """Convert human-readable memory string (e.g., '3072.00M', '2.5G', '512K') to integer bytes."""
    val_str = val_str.strip()
    m = re.match(r"^([\d.]+)\s*([KMGTkmgt]?)[Bb]?$", val_str)
    if not m:
        try:
            return int(float(val_str))
        except ValueError:
            return 0

    num = float(m.group(1))
    unit = m.group(2).upper()
    multipliers = {
        "": 1,
        "K": 1024,
        "M": 1024 * 1024,
        "G": 1024 * 1024 * 1024,
        "T": 1024 * 1024 * 1024 * 1024,
    }
    return int(num * multipliers.get(unit, 1))


class MacMemoryDetector:
    """Read-only detector for macOS memory capacity, VM page metrics, swap, and pressure."""

    @classmethod
    def _get_sysctl_int(cls, key: str, default: int = 0) -> int:
        """Query integer sysctl value."""
        rc, out = _safe_exec(["sysctl", "-n", key])
        if rc == 0 and out:
            try:
                return int(out)
            except ValueError:
                return default
        return default

    @classmethod
    def parse_vm_stat(cls, raw: str) -> MacVmPageStats:
        """Parse raw output of Darwin `vm_stat` utility into structured page stats."""
        page_size = 16384 if platform.machine() == "arm64" else 4096
        m_page = re.search(r"page size of (\d+) bytes", raw)
        if m_page:
            page_size = int(m_page.group(1))

        counts: Dict[str, int] = {}
        for line in raw.splitlines():
            line = line.strip()
            if ":" not in line:
                continue
            key, val = line.split(":", 1)
            key = key.strip().strip('"')
            val = val.strip().rstrip(".")
            try:
                counts[key] = int(val)
            except ValueError:
                continue

        return MacVmPageStats(
            page_size_bytes=page_size,
            pages_free=counts.get("Pages free", 0),
            pages_active=counts.get("Pages active", 0),
            pages_inactive=counts.get("Pages inactive", 0),
            pages_speculative=counts.get("Pages speculative", 0),
            pages_wired_down=counts.get("Pages wired down", 0),
            pages_purgeable=counts.get("Pages purgeable", 0),
            file_backed_pages=counts.get("File-backed pages", 0),
            anonymous_pages=counts.get("Anonymous pages", 0),
            pages_stored_in_compressor=counts.get("Pages stored in compressor", 0),
            pages_occupied_by_compressor=counts.get("Pages occupied by compressor", 0),
            decompressions=counts.get("Decompressions", 0),
            compressions=counts.get("Compressions", 0),
            pageins=counts.get("Pageins", 0),
            pageouts=counts.get("Pageouts", 0),
            swapins=counts.get("Swapins", 0),
            swapouts=counts.get("Swapouts", 0),
        )

    @classmethod
    def parse_swapusage(cls, raw: str) -> MacSwapUsage:
        """Parse `sysctl vm.swapusage` output: 'total = 3072.00M used = 2396.06M free = 675.94M (encrypted)'."""
        m_total = re.search(r"total\s*=\s*([\d.]+[KMGTkmgt]?)", raw)
        m_used = re.search(r"used\s*=\s*([\d.]+[KMGTkmgt]?)", raw)
        m_free = re.search(r"free\s*=\s*([\d.]+[KMGTkmgt]?)", raw)
        is_enc = "encrypted" in raw.lower()

        total = _parse_size_to_bytes(m_total.group(1)) if m_total else 0
        used = _parse_size_to_bytes(m_used.group(1)) if m_used else 0
        free = _parse_size_to_bytes(m_free.group(1)) if m_free else 0

        return MacSwapUsage(
            total_bytes=total,
            used_bytes=used,
            free_bytes=free,
            is_encrypted=is_enc,
        )

    @classmethod
    def detect_pressure(cls) -> Tuple[MemoryPressureLevel, float]:
        """Query kernel memory pressure level and numeric pressure percentage."""
        level_int = cls._get_sysctl_int("vm.memory_pressure", default=-1)
        status_pct = float(cls._get_sysctl_int("kern.memorystatus_level", default=0))

        if level_int == 0:
            level = MemoryPressureLevel.NORMAL
        elif level_int == 1:
            level = MemoryPressureLevel.WARN
        elif level_int >= 2:
            level = MemoryPressureLevel.CRITICAL
        else:
            # Fallback deduction from memorystatus_level or load
            if status_pct > 80:
                level = MemoryPressureLevel.CRITICAL
            elif status_pct > 60:
                level = MemoryPressureLevel.WARN
            elif status_pct > 0:
                level = MemoryPressureLevel.NORMAL
            else:
                level = MemoryPressureLevel.UNKNOWN

        return level, status_pct

    @classmethod
    def detect(cls, mock_adapter: Optional[MockPlatformAdapter] = None) -> MacMemoryTelemetryReport:
        """Execute memory detection using live Darwin host or mock platform adapter."""
        if mock_adapter is not None:
            return cls._detect_from_mock(mock_adapter)

        if platform.system() == "Darwin":
            return cls._detect_live_darwin()

        return cls._detect_non_darwin_fallback()

    @classmethod
    def _detect_live_darwin(cls) -> MacMemoryTelemetryReport:
        """Collect live memory metrics from native Darwin sysctl and vm_stat interfaces."""
        unavailable: List[str] = []
        warnings: List[str] = []

        # 1. Total Physical RAM
        total_mem = cls._get_sysctl_int("hw.memsize", default=0)
        if total_mem == 0:
            unavailable.append("hw.memsize")
            total_mem = 8 * 1024 * 1024 * 1024  # 8GB safe default

        # 2. Virtual Memory Page Statistics (vm_stat)
        rc_vm, out_vm = _safe_exec(["vm_stat"])
        if rc_vm == 0 and out_vm:
            page_stats = cls.parse_vm_stat(out_vm)
        else:
            unavailable.append("vm_stat")
            warnings.append("vm_stat utility returned non-zero or empty output")
            page_stats = MacVmPageStats()

        # 3. Swap Usage (sysctl vm.swapusage)
        rc_swap, out_swap = _safe_exec(["sysctl", "vm.swapusage"])
        if rc_swap == 0 and out_swap:
            swap_usage = cls.parse_swapusage(out_swap)
        else:
            unavailable.append("vm.swapusage")
            swap_usage = MacSwapUsage()

        # 4. Memory Pressure Level & Percentage
        pressure_level, pressure_pct = cls.detect_pressure()
        if pressure_level == MemoryPressureLevel.UNKNOWN:
            unavailable.append("vm.memory_pressure")

        # 5. Activity Monitor Standard Breakdown Calculations
        page_size = page_stats.page_size_bytes
        app_mem = max(0, (page_stats.anonymous_pages - page_stats.pages_purgeable) * page_size)
        wired_mem = page_stats.pages_wired_down * page_size
        compressed_mem = page_stats.pages_occupied_by_compressor * page_size
        total_used = app_mem + wired_mem + compressed_mem
        cached_files = (page_stats.file_backed_pages + page_stats.pages_purgeable) * page_size
        free_mem = page_stats.pages_free * page_size

        used_pct = round((total_used / total_mem) * 100, 2) if total_mem > 0 else 0.0

        breakdown = MacMemoryBreakdown(
            total_physical_bytes=total_mem,
            app_memory_bytes=app_mem,
            wired_memory_bytes=wired_mem,
            compressed_memory_bytes=compressed_mem,
            total_used_bytes=total_used,
            cached_files_bytes=cached_files,
            free_bytes=free_mem,
            used_percent=used_pct,
            swap=swap_usage,
            pressure_level=pressure_level,
            pressure_percentage=pressure_pct,
        )

        return MacMemoryTelemetryReport(
            memory_info=breakdown,
            page_stats=page_stats,
            collection_method="NATIVE_DARWIN_SYSCTL_VMSTAT",
            unavailable_telemetry=unavailable,
            warnings=warnings,
        )

    @classmethod
    def _detect_from_mock(cls, mock: MockPlatformAdapter) -> MacMemoryTelemetryReport:
        """Synthesize deterministic memory telemetry from mock platform adapter."""
        host_report = mock.get_host_report()
        total_mem = host_report.memory_bytes or (8 * 1024 * 1024 * 1024)
        page_size = 16384

        # Deterministic simulation of typical 8GB system load:
        # App: ~2.5GB, Wired: ~1.2GB, Compressed: ~0.8GB, Cached: ~2.0GB, Free: ~1.5GB
        app_mem = int(total_mem * 0.30)
        wired_mem = int(total_mem * 0.15)
        compressed_mem = int(total_mem * 0.10)
        total_used = app_mem + wired_mem + compressed_mem
        cached_files = int(total_mem * 0.25)
        free_mem = max(0, total_mem - total_used - cached_files)

        page_stats = MacVmPageStats(
            page_size_bytes=page_size,
            pages_free=free_mem // page_size,
            pages_active=(app_mem // 2) // page_size,
            pages_inactive=(app_mem // 2) // page_size,
            pages_speculative=256,
            pages_wired_down=wired_mem // page_size,
            pages_purgeable=512,
            file_backed_pages=(cached_files - (512 * page_size)) // page_size,
            anonymous_pages=(app_mem // page_size) + 512,
            pages_stored_in_compressor=(compressed_mem * 2) // page_size,
            pages_occupied_by_compressor=compressed_mem // page_size,
            pageins=100000,
            pageouts=5000,
            swapins=1000,
            swapouts=2000,
        )

        swap = MacSwapUsage(
            total_bytes=3 * 1024 * 1024 * 1024,      # 3GB
            used_bytes=512 * 1024 * 1024,           # 512MB
            free_bytes=2560 * 1024 * 1024,          # 2.5GB
            is_encrypted=True,
        )

        used_pct = round((total_used / total_mem) * 100, 2)

        breakdown = MacMemoryBreakdown(
            total_physical_bytes=total_mem,
            app_memory_bytes=app_mem,
            wired_memory_bytes=wired_mem,
            compressed_memory_bytes=compressed_mem,
            total_used_bytes=total_used,
            cached_files_bytes=cached_files,
            free_bytes=free_mem,
            used_percent=used_pct,
            swap=swap,
            pressure_level=MemoryPressureLevel.NORMAL,
            pressure_percentage=15.0,
        )

        return MacMemoryTelemetryReport(
            memory_info=breakdown,
            page_stats=page_stats,
            collection_method="MOCK_PLATFORM_ADAPTER",
            unavailable_telemetry=[],
            warnings=[],
        )

    @classmethod
    def _detect_non_darwin_fallback(cls) -> MacMemoryTelemetryReport:
        """Provide safe fallback report when executed on non-Darwin platforms."""
        unavailable = [
            "hw.memsize",
            "vm_stat",
            "vm.swapusage",
            "vm.memory_pressure",
            "kern.memorystatus_level",
        ]
        warnings = [
            f"Native Darwin memory interfaces unavailable on non-Darwin OS: '{platform.system()}'",
            "Report synthesized from generic platform fallback.",
        ]

        total_mem = 8 * 1024 * 1024 * 1024
        breakdown = MacMemoryBreakdown(
            total_physical_bytes=total_mem,
            app_memory_bytes=total_mem // 3,
            wired_memory_bytes=total_mem // 6,
            compressed_memory_bytes=0,
            total_used_bytes=total_mem // 2,
            cached_files_bytes=total_mem // 4,
            free_bytes=total_mem // 4,
            used_percent=50.0,
            swap=MacSwapUsage(total_bytes=0, used_bytes=0, free_bytes=0, is_encrypted=False),
            pressure_level=MemoryPressureLevel.UNKNOWN,
            pressure_percentage=0.0,
        )

        return MacMemoryTelemetryReport(
            memory_info=breakdown,
            page_stats=MacVmPageStats(),
            collection_method="GENERIC_NON_DARWIN_FALLBACK",
            unavailable_telemetry=unavailable,
            warnings=warnings,
        )
