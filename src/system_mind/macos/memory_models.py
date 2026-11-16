"""Data models for macOS memory capacity, Mach virtual memory statistics, swap, and memory pressure."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import List, Optional


class MemoryPressureLevel(str, Enum):
    """Categorical macOS kernel memory pressure state."""

    NORMAL = "NORMAL"      # Nominal memory pressure (green)
    WARN = "WARN"          # Elevated memory pressure (yellow)
    CRITICAL = "CRITICAL"  # Severe memory pressure, high reclamation/paging (red)
    UNKNOWN = "UNKNOWN"    # Unrecognized or unavailable pressure state


@dataclass(frozen=True)
class MacVmPageStats:
    """Detailed Mach virtual memory page allocation and compression counts."""

    page_size_bytes: int = 16384
    pages_free: int = 0
    pages_active: int = 0
    pages_inactive: int = 0
    pages_speculative: int = 0
    pages_wired_down: int = 0
    pages_purgeable: int = 0
    file_backed_pages: int = 0
    anonymous_pages: int = 0
    pages_stored_in_compressor: int = 0
    pages_occupied_by_compressor: int = 0
    decompressions: int = 0
    compressions: int = 0
    pageins: int = 0
    pageouts: int = 0
    swapins: int = 0
    swapouts: int = 0


@dataclass(frozen=True)
class MacSwapUsage:
    """macOS dynamic swapfile metrics and encryption status."""

    total_bytes: int = 0
    used_bytes: int = 0
    free_bytes: int = 0
    is_encrypted: bool = True


@dataclass(frozen=True)
class MacMemoryBreakdown:
    """Authoritative memory breakdown matching macOS Activity Monitor semantics."""

    total_physical_bytes: int
    app_memory_bytes: int
    wired_memory_bytes: int
    compressed_memory_bytes: int
    total_used_bytes: int
    cached_files_bytes: int
    free_bytes: int
    used_percent: float
    swap: MacSwapUsage
    pressure_level: MemoryPressureLevel = MemoryPressureLevel.NORMAL
    pressure_percentage: float = 0.0


@dataclass(frozen=True)
class MacMemoryTelemetryReport:
    """Authoritative aggregated telemetry report for macOS memory subsystem."""

    memory_info: MacMemoryBreakdown
    page_stats: MacVmPageStats
    collected_at_epoch_secs: float = field(default_factory=time.time)
    collection_method: str = "NATIVE_DARWIN_SYSCTL_VMSTAT"
    unavailable_telemetry: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
