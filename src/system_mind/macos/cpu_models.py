"""Data models for macOS CPU topology, core counts, and hardware properties."""

from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import List, Optional


@dataclass(frozen=True)
class CpuPerfLevelInfo:
    """Core cluster metrics for a specific performance level (Performance or Efficiency)."""

    level: int
    name: str
    physical_cores: int
    logical_cores: int
    l1i_cache_bytes: int
    l1d_cache_bytes: int
    l2_cache_bytes: int
    cpus_per_l2: int


@dataclass(frozen=True)
class MacCpuHardwareInfo:
    """Comprehensive CPU model, core topology, cache hierarchy, and hardware properties."""

    cpu_brand_string: str
    hardware_model: str
    total_physical_cores: int
    total_logical_cores: int
    performance_cores: int
    efficiency_cores: int
    num_perf_levels: int
    perf_levels: List[CpuPerfLevelInfo] = field(default_factory=list)
    cache_line_size_bytes: int = 128
    l1i_cache_bytes: int = 0
    l1d_cache_bytes: int = 0
    l2_cache_bytes: int = 0
    l3_cache_bytes: int = 0
    timebase_frequency_hz: int = 24000000
    page_size_bytes: int = 16384
    physical_memory_bytes: int = 0
    supported_features: List[str] = field(default_factory=list)
    is_heterogeneous_core_topology: bool = False


@dataclass(frozen=True)
class MacCpuTelemetryReport:
    """Authoritative aggregated telemetry report for macOS CPU and compute hardware."""

    cpu_info: MacCpuHardwareInfo
    collected_at_epoch_secs: float = field(default_factory=time.time)
    collection_method: str = "NATIVE_DARWIN_SYSCTL"
    unavailable_telemetry: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    scan_proves_safe: bool = False  # Charter non-negotiable invariant: Scan != Safe
