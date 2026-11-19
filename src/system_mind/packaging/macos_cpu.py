"""Automated packaging validator auditing macOS CPU topology and hardware telemetry."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
from typing import List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent

from system_mind.macos.cpu_detector import MacCpuHardwareDetector
from system_mind.macos.cpu_models import (
    CpuPerfLevelInfo,
    MacCpuHardwareInfo,
    MacCpuTelemetryReport,
)
from system_mind.platform.adapter import MockPlatformProfileFactory


@dataclass(frozen=True)
class MacOsCpuAuditResult:
    """Outcome of auditing macOS companion agent CPU telemetry engine and CLI tooling."""

    valid: bool
    issues: tuple[str, ...]
    models_valid: bool
    detector_valid: bool
    cli_valid: bool
    topology_valid: bool


class MacOsCpuValidator:
    """Programmatic validator verifying macOS CPU data models, core topology, and CLI tools."""

    CLI_REL_PATH = Path("tools") / "detect_cpu.py"

    REQUIRED_PERF_LEVEL_FIELDS = [
        "level",
        "name",
        "physical_cores",
        "logical_cores",
        "l1i_cache_bytes",
        "l1d_cache_bytes",
        "l2_cache_bytes",
        "cpus_per_l2",
    ]

    REQUIRED_CPU_FIELDS = [
        "cpu_brand_string",
        "hardware_model",
        "total_physical_cores",
        "total_logical_cores",
        "performance_cores",
        "efficiency_cores",
        "num_perf_levels",
        "perf_levels",
        "cache_line_size_bytes",
        "l1i_cache_bytes",
        "l1d_cache_bytes",
        "l2_cache_bytes",
        "l3_cache_bytes",
        "timebase_frequency_hz",
        "page_size_bytes",
        "physical_memory_bytes",
        "supported_features",
        "is_heterogeneous_core_topology",
    ]

    REQUIRED_REPORT_FIELDS = [
        "cpu_info",
        "collected_at_epoch_secs",
        "collection_method",
        "unavailable_telemetry",
        "warnings",
    ]

    @classmethod
    def audit(cls, root_dir: Optional[Path] = None) -> MacOsCpuAuditResult:
        """Executes full audit across CPU data models, detection logic, topology rules, and CLI."""
        base_dir = root_dir or ROOT_DIR
        issues: List[str] = []
        models_ok = True
        detector_ok = True
        cli_ok = True
        topology_ok = True

        # 1. Audit Data Model Fields
        for f in cls.REQUIRED_PERF_LEVEL_FIELDS:
            if f not in CpuPerfLevelInfo.__dataclass_fields__:
                issues.append(f"CpuPerfLevelInfo missing required field: '{f}'")
                models_ok = False

        for f in cls.REQUIRED_CPU_FIELDS:
            if f not in MacCpuHardwareInfo.__dataclass_fields__:
                issues.append(f"MacCpuHardwareInfo missing required field: '{f}'")
                models_ok = False

        for f in cls.REQUIRED_REPORT_FIELDS:
            if f not in MacCpuTelemetryReport.__dataclass_fields__:
                issues.append(f"MacCpuTelemetryReport missing required field: '{f}'")
                models_ok = False

        # 2. Audit Mock Platform Detection & Topology Rules
        try:
            mock = MockPlatformProfileFactory.create_macos_apple_silicon_mock()
            report = MacCpuHardwareDetector.detect(mock_adapter=mock)

            if not isinstance(report, MacCpuTelemetryReport):
                issues.append("MacCpuHardwareDetector.detect() did not return a MacCpuTelemetryReport instance")
                detector_ok = False

            if report.collection_method != "MOCK_PLATFORM_ADAPTER":
                issues.append(f"Unexpected collection method in mock mode: '{report.collection_method}'")
                detector_ok = False

            info = report.cpu_info
            if info.total_physical_cores <= 0:
                issues.append("Detected non-positive physical core count in mock mode")
                topology_ok = False

            if info.performance_cores <= 0:
                issues.append("Apple Silicon profile must have at least 1 performance core")
                topology_ok = False

            if not info.is_heterogeneous_core_topology:
                issues.append("Apple Silicon M1 mock profile must indicate heterogeneous core topology")
                topology_ok = False

            if info.cache_line_size_bytes != 128:
                issues.append(f"Expected 128-byte cache line for Apple Silicon, got {info.cache_line_size_bytes}")
                topology_ok = False

        except Exception as e:
            issues.append(f"MacCpuHardwareDetector audit failed with exception: {e}")
            detector_ok = False

        # 3. Audit Developer CLI Tool
        cli_path = base_dir / cls.CLI_REL_PATH
        if not cli_path.exists():
            issues.append(f"Developer CLI tool missing at: {cli_path}")
            cli_ok = False
        else:
            cli_text = cli_path.read_text(encoding="utf-8")
            if "shell=True" in cli_text:
                issues.append(f"Prohibited ambient shell invocation (shell=True) found in {cli_path}")
                cli_ok = False

            # Test execution of CLI tool in mock mode
            try:
                proc = subprocess.run(
                    [sys.executable, str(cli_path), "--mock", "--json"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    shell=False,
                    timeout=15.0,
                )
                if proc.returncode != 0:
                    issues.append(f"CLI tool returned non-zero exit code ({proc.returncode}): {proc.stderr}")
                    cli_ok = False
                else:
                    payload = json.loads(proc.stdout)
                    if payload.get("collection_method") != "MOCK_PLATFORM_ADAPTER":
                        issues.append("CLI JSON output missing expected collection_method in mock mode")
                        cli_ok = False
            except Exception as e:
                issues.append(f"Failed to execute CLI tool '{cli_path}': {e}")
                cli_ok = False

        # 4. Audit Rust Sensor File
        rust_sensor_path = base_dir / "crates" / "system-mind-sensors" / "src" / "macos_cpu.rs"
        if not rust_sensor_path.exists():
            issues.append(f"Rust macOS CPU sensor file missing: {rust_sensor_path}")
            detector_ok = False

        is_valid = len(issues) == 0
        return MacOsCpuAuditResult(
            valid=is_valid,
            issues=tuple(issues),
            models_valid=models_ok,
            detector_valid=detector_ok,
            cli_valid=cli_ok,
            topology_valid=topology_ok,
        )
