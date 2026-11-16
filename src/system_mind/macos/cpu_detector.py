"""Read-only macOS CPU model, core counts, and hardware properties detector.

Gathers processor brand string, hardware model, symmetric/asymmetric core topology
(Performance vs. Efficiency cores), cache hierarchy, timebase frequency, page size,
and vector/SIMD instruction extensions using unprivileged read-only Darwin sysctl queries
in strict compliance with SC-01 and privacy constraints.
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

from system_mind.macos.cpu_models import (
    CpuPerfLevelInfo,
    MacCpuHardwareInfo,
    MacCpuTelemetryReport,
)
from system_mind.platform.adapter import MockPlatformAdapter
from system_mind.platform.matrix import PlatformTargetId


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


class MacCpuHardwareDetector:
    """Read-only detector for macOS CPU architecture, core topology, and hardware properties."""

    @classmethod
    def _get_sysctl_str(cls, key: str) -> str:
        """Query a string sysctl key via read-only sysctl utility."""
        rc, out = _safe_exec(["sysctl", "-n", key])
        if rc == 0 and out:
            return out
        return ""

    @classmethod
    def _get_sysctl_int(cls, key: str, default: int = 0) -> int:
        """Query an integer sysctl key via read-only sysctl utility."""
        rc, out = _safe_exec(["sysctl", "-n", key])
        if rc == 0 and out:
            try:
                return int(out)
            except ValueError:
                return default
        return default

    @classmethod
    def detect(cls, mock_adapter: Optional[MockPlatformAdapter] = None) -> MacCpuTelemetryReport:
        """Execute CPU hardware detection using live Darwin host or mock adapter."""
        if mock_adapter is not None:
            return cls._detect_from_mock(mock_adapter)

        if platform.system() == "Darwin":
            return cls._detect_live_darwin()

        return cls._detect_non_darwin_fallback()

    @classmethod
    def _detect_live_darwin(cls) -> MacCpuTelemetryReport:
        """Collect live CPU and hardware properties from native Darwin sysctl interfaces."""
        unavailable: List[str] = []
        warnings: List[str] = []

        # 1. CPU Brand String and Hardware Model Identifier
        cpu_brand = cls._get_sysctl_str("machdep.cpu.brand_string")
        if not cpu_brand:
            cpu_brand = platform.processor() or "Apple Silicon"

        hw_model = cls._get_sysctl_str("hw.model")
        if not hw_model:
            unavailable.append("hw.model")
            hw_model = "Mac"

        # 2. Core Counts (Physical and Logical)
        physical_cores = cls._get_sysctl_int("hw.physicalcpu", default=0)
        logical_cores = cls._get_sysctl_int("hw.logicalcpu", default=0)
        if physical_cores == 0:
            physical_cores = os.cpu_count() or 1
            unavailable.append("hw.physicalcpu")
        if logical_cores == 0:
            logical_cores = os.cpu_count() or physical_cores
            unavailable.append("hw.logicalcpu")

        # 3. Performance Level Topology (Apple Silicon P-cores vs E-cores)
        nperflevels = cls._get_sysctl_int("hw.nperflevels", default=0)
        perf_levels: List[CpuPerfLevelInfo] = []
        p_cores = 0
        e_cores = 0

        if nperflevels > 0:
            for level in range(nperflevels):
                name = cls._get_sysctl_str(f"hw.perflevel{level}.name")
                if not name:
                    name = "Performance" if level == 0 else "Efficiency"
                phys = cls._get_sysctl_int(f"hw.perflevel{level}.physicalcpu", default=0)
                logi = cls._get_sysctl_int(f"hw.perflevel{level}.logicalcpu", default=0)
                l1i = cls._get_sysctl_int(f"hw.perflevel{level}.l1icachesize", default=0)
                l1d = cls._get_sysctl_int(f"hw.perflevel{level}.l1dcachesize", default=0)
                l2 = cls._get_sysctl_int(f"hw.perflevel{level}.l2cachesize", default=0)
                cpus_per_l2 = cls._get_sysctl_int(f"hw.perflevel{level}.cpusperl2", default=0)

                perf_levels.append(
                    CpuPerfLevelInfo(
                        level=level,
                        name=name,
                        physical_cores=phys,
                        logical_cores=logi,
                        l1i_cache_bytes=l1i,
                        l1d_cache_bytes=l1d,
                        l2_cache_bytes=l2,
                        cpus_per_l2=cpus_per_l2,
                    )
                )

                if "performance" in name.lower() or level == 0:
                    p_cores += logi or phys
                elif "efficiency" in name.lower() or level == 1:
                    e_cores += logi or phys
        else:
            unavailable.append("hw.nperflevels")
            # Symmetric processor fallback
            p_cores = physical_cores
            e_cores = 0

        # If p_cores + e_cores doesn't match total, adjust
        if p_cores == 0 and e_cores == 0:
            p_cores = physical_cores

        is_heterogeneous = p_cores > 0 and e_cores > 0

        # 4. Cache Hierarchy and Page Size
        cache_line = cls._get_sysctl_int("hw.cachelinesize", default=128 if platform.machine() == "arm64" else 64)
        l1i_cache = cls._get_sysctl_int("hw.l1icachesize", default=0)
        l1d_cache = cls._get_sysctl_int("hw.l1dcachesize", default=0)
        l2_cache = cls._get_sysctl_int("hw.l2cachesize", default=0)
        l3_cache = cls._get_sysctl_int("hw.l3cachesize", default=0)

        timebase_freq = cls._get_sysctl_int("hw.tbfrequency", default=24000000)
        page_size = cls._get_sysctl_int("hw.pagesize", default=16384 if platform.machine() == "arm64" else 4096)
        mem_size = cls._get_sysctl_int("hw.memsize", default=0)

        # 5. Supported Hardware Features & Vector Extensions
        features: List[str] = []
        if cls._get_sysctl_int("hw.optional.floatingpoint", default=0) == 1:
            features.append("floatingpoint")
        if cls._get_sysctl_int("hw.optional.neon", default=0) == 1:
            features.append("neon")

        # Discover active ARM optional features
        rc, opt_out = _safe_exec(["sysctl", "-a"])
        if rc == 0 and opt_out:
            for line in opt_out.splitlines():
                if "hw.optional.arm.FEAT_" in line and ": 1" in line:
                    m = re.search(r"hw\.optional\.arm\.(FEAT_\w+):\s*1", line)
                    if m:
                        features.append(m.group(1))
                elif "machdep.cpu.features" in line and ": " in line:
                    for feat in line.split(":", 1)[1].strip().split():
                        if feat not in features:
                            features.append(feat)

        info = MacCpuHardwareInfo(
            cpu_brand_string=cpu_brand,
            hardware_model=hw_model,
            total_physical_cores=physical_cores,
            total_logical_cores=logical_cores,
            performance_cores=p_cores,
            efficiency_cores=e_cores,
            num_perf_levels=nperflevels,
            perf_levels=perf_levels,
            cache_line_size_bytes=cache_line,
            l1i_cache_bytes=l1i_cache,
            l1d_cache_bytes=l1d_cache,
            l2_cache_bytes=l2_cache,
            l3_cache_bytes=l3_cache,
            timebase_frequency_hz=timebase_freq,
            page_size_bytes=page_size,
            physical_memory_bytes=mem_size,
            supported_features=sorted(set(features)),
            is_heterogeneous_core_topology=is_heterogeneous,
        )

        return MacCpuTelemetryReport(
            cpu_info=info,
            collection_method="NATIVE_DARWIN_SYSCTL",
            unavailable_telemetry=unavailable,
            warnings=warnings,
        )

    @classmethod
    def _detect_from_mock(cls, mock: MockPlatformAdapter) -> MacCpuTelemetryReport:
        """Synthesize deterministic CPU hardware telemetry from mock platform profile."""
        host_report = mock.get_host_report()
        target_id = mock.get_target_id()
        is_arm = target_id == PlatformTargetId.MACOS_APPLE_SILICON

        if is_arm:
            perf_levels = [
                CpuPerfLevelInfo(
                    level=0,
                    name="Performance",
                    physical_cores=4,
                    logical_cores=4,
                    l1i_cache_bytes=196608,
                    l1d_cache_bytes=131072,
                    l2_cache_bytes=12582912,
                    cpus_per_l2=4,
                ),
                CpuPerfLevelInfo(
                    level=1,
                    name="Efficiency",
                    physical_cores=4,
                    logical_cores=4,
                    l1i_cache_bytes=131072,
                    l1d_cache_bytes=65536,
                    l2_cache_bytes=4194304,
                    cpus_per_l2=4,
                ),
            ]
            features = ["FEAT_AES", "FEAT_CRC32", "FEAT_DotProd", "FEAT_LSE", "FEAT_SHA256", "floatingpoint", "neon"]
            info = MacCpuHardwareInfo(
                cpu_brand_string="Apple M1",
                hardware_model="MacBookAir10,1",
                total_physical_cores=host_report.cpu_cores,
                total_logical_cores=host_report.cpu_cores,
                performance_cores=4,
                efficiency_cores=4,
                num_perf_levels=2,
                perf_levels=perf_levels,
                cache_line_size_bytes=128,
                l1i_cache_bytes=131072,
                l1d_cache_bytes=65536,
                l2_cache_bytes=4194304,
                l3_cache_bytes=0,
                timebase_frequency_hz=24000000,
                page_size_bytes=16384,
                physical_memory_bytes=host_report.memory_bytes,
                supported_features=features,
                is_heterogeneous_core_topology=True,
            )
        else:
            # Symmetric mock profile
            perf_levels = [
                CpuPerfLevelInfo(
                    level=0,
                    name="Performance",
                    physical_cores=host_report.cpu_cores,
                    logical_cores=host_report.cpu_cores,
                    l1i_cache_bytes=32768,
                    l1d_cache_bytes=32768,
                    l2_cache_bytes=524288,
                    cpus_per_l2=1,
                )
            ]
            features = ["floatingpoint", "sse", "sse2", "avx", "avx2"]
            info = MacCpuHardwareInfo(
                cpu_brand_string="Mock Synthetic CPU",
                hardware_model="Standard-PC",
                total_physical_cores=host_report.cpu_cores,
                total_logical_cores=host_report.cpu_cores,
                performance_cores=host_report.cpu_cores,
                efficiency_cores=0,
                num_perf_levels=1,
                perf_levels=perf_levels,
                cache_line_size_bytes=64,
                l1i_cache_bytes=32768,
                l1d_cache_bytes=32768,
                l2_cache_bytes=524288,
                l3_cache_bytes=16777216,
                timebase_frequency_hz=1000000,
                page_size_bytes=4096,
                physical_memory_bytes=host_report.memory_bytes,
                supported_features=features,
                is_heterogeneous_core_topology=False,
            )

        return MacCpuTelemetryReport(
            cpu_info=info,
            collection_method="MOCK_PLATFORM_ADAPTER",
            unavailable_telemetry=[],
            warnings=[],
        )

    @classmethod
    def _detect_non_darwin_fallback(cls) -> MacCpuTelemetryReport:
        """Provide safe fallback report when running on non-Darwin operating systems."""
        cores = os.cpu_count() or 1
        unavailable = [
            "machdep.cpu.brand_string",
            "hw.model",
            "hw.nperflevels",
            "hw.perflevel0.logicalcpu",
            "hw.perflevel1.logicalcpu",
            "hw.cachelinesize",
            "hw.tbfrequency",
        ]
        warnings = [
            f"Native Darwin sysctls unavailable on non-Darwin OS: '{platform.system()}'",
            "Report synthesized from Python generic platform heuristics.",
        ]

        info = MacCpuHardwareInfo(
            cpu_brand_string=platform.processor() or "Generic Processor",
            hardware_model=f"Generic-{platform.system()}",
            total_physical_cores=cores,
            total_logical_cores=cores,
            performance_cores=cores,
            efficiency_cores=0,
            num_perf_levels=1,
            perf_levels=[],
            cache_line_size_bytes=64,
            l1i_cache_bytes=0,
            l1d_cache_bytes=0,
            l2_cache_bytes=0,
            l3_cache_bytes=0,
            timebase_frequency_hz=0,
            page_size_bytes=4096,
            physical_memory_bytes=0,
            supported_features=[],
            is_heterogeneous_core_topology=False,
        )

        return MacCpuTelemetryReport(
            cpu_info=info,
            collection_method="GENERIC_NON_DARWIN_FALLBACK",
            unavailable_telemetry=unavailable,
            warnings=warnings,
        )
