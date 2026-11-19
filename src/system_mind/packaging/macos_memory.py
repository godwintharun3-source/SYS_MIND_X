"""Automated packaging validator auditing macOS memory telemetry models and detection engine."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
from typing import List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent

from system_mind.macos.memory_detector import MacMemoryDetector
from system_mind.macos.memory_models import (
    MacMemoryBreakdown,
    MacMemoryTelemetryReport,
    MacSwapUsage,
    MacVmPageStats,
    MemoryPressureLevel,
)
from system_mind.platform.adapter import MockPlatformProfileFactory


@dataclass(frozen=True)
class MacOsMemoryAuditResult:
    """Outcome of auditing macOS companion agent memory telemetry engine and CLI tooling."""

    valid: bool
    issues: tuple[str, ...]
    models_valid: bool
    detector_valid: bool
    cli_valid: bool
    math_invariants_valid: bool


class MacOsMemoryValidator:
    """Programmatic validator verifying macOS memory data models, Activity Monitor formulas, and CLI tools."""

    CLI_REL_PATH = Path("tools") / "detect_memory.py"

    REQUIRED_PAGE_FIELDS = [
        "page_size_bytes",
        "pages_free",
        "pages_active",
        "pages_inactive",
        "pages_speculative",
        "pages_wired_down",
        "pages_purgeable",
        "file_backed_pages",
        "anonymous_pages",
        "pages_stored_in_compressor",
        "pages_occupied_by_compressor",
        "pageins",
        "pageouts",
        "swapins",
        "swapouts",
    ]

    REQUIRED_SWAP_FIELDS = [
        "total_bytes",
        "used_bytes",
        "free_bytes",
        "is_encrypted",
    ]

    REQUIRED_BREAKDOWN_FIELDS = [
        "total_physical_bytes",
        "app_memory_bytes",
        "wired_memory_bytes",
        "compressed_memory_bytes",
        "total_used_bytes",
        "cached_files_bytes",
        "free_bytes",
        "used_percent",
        "swap",
        "pressure_level",
        "pressure_percentage",
    ]

    REQUIRED_REPORT_FIELDS = [
        "memory_info",
        "page_stats",
        "collected_at_epoch_secs",
        "collection_method",
        "unavailable_telemetry",
        "warnings",
    ]

    @classmethod
    def audit(cls, root_dir: Optional[Path] = None) -> MacOsMemoryAuditResult:
        """Executes full audit across memory models, detection logic, math invariants, and CLI."""
        base_dir = root_dir or ROOT_DIR
        issues: List[str] = []
        models_ok = True
        detector_ok = True
        cli_ok = True
        math_ok = True

        # 1. Audit Data Model Fields
        for f in cls.REQUIRED_PAGE_FIELDS:
            if f not in MacVmPageStats.__dataclass_fields__:
                issues.append(f"MacVmPageStats missing required field: '{f}'")
                models_ok = False

        for f in cls.REQUIRED_SWAP_FIELDS:
            if f not in MacSwapUsage.__dataclass_fields__:
                issues.append(f"MacSwapUsage missing required field: '{f}'")
                models_ok = False

        for f in cls.REQUIRED_BREAKDOWN_FIELDS:
            if f not in MacMemoryBreakdown.__dataclass_fields__:
                issues.append(f"MacMemoryBreakdown missing required field: '{f}'")
                models_ok = False

        for f in cls.REQUIRED_REPORT_FIELDS:
            if f not in MacMemoryTelemetryReport.__dataclass_fields__:
                issues.append(f"MacMemoryTelemetryReport missing required field: '{f}'")
                models_ok = False

        # 2. Audit Mock Platform Detection & Mathematical Invariants
        try:
            mock = MockPlatformProfileFactory.create_macos_apple_silicon_mock()
            report = MacMemoryDetector.detect(mock_adapter=mock)

            if not isinstance(report, MacMemoryTelemetryReport):
                issues.append("MacMemoryDetector.detect() did not return a MacMemoryTelemetryReport instance")
                detector_ok = False

            if report.collection_method != "MOCK_PLATFORM_ADAPTER":
                issues.append(f"Unexpected collection method in mock mode: '{report.collection_method}'")
                detector_ok = False

            mem = report.memory_info
            if mem.total_physical_bytes <= 0:
                issues.append("Detected non-positive total physical memory in mock mode")
                math_ok = False

            # Invariant: total_used = app + wired + compressed
            expected_used = mem.app_memory_bytes + mem.wired_memory_bytes + mem.compressed_memory_bytes
            if mem.total_used_bytes != expected_used:
                issues.append(
                    f"Activity Monitor invariant breach: total_used ({mem.total_used_bytes}) != app+wired+comp ({expected_used})"
                )
                math_ok = False

            if mem.total_used_bytes > mem.total_physical_bytes:
                issues.append("Total used bytes exceeds total physical memory in mock mode")
                math_ok = False

            if not (0.0 <= mem.used_percent <= 100.0):
                issues.append(f"Memory used percent out of valid [0, 100] range: {mem.used_percent}")
                math_ok = False

            if mem.pressure_level not in (MemoryPressureLevel.NORMAL, MemoryPressureLevel.WARN, MemoryPressureLevel.CRITICAL):
                issues.append(f"Unexpected memory pressure level in mock mode: {mem.pressure_level}")
                math_ok = False

        except Exception as e:
            issues.append(f"MacMemoryDetector audit failed with exception: {e}")
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
        rust_sensor_path = base_dir / "crates" / "system-mind-sensors" / "src" / "macos_memory.rs"
        if not rust_sensor_path.exists():
            issues.append(f"Rust macOS memory sensor file missing: {rust_sensor_path}")
            detector_ok = False

        is_valid = len(issues) == 0
        return MacOsMemoryAuditResult(
            valid=is_valid,
            issues=tuple(issues),
            models_valid=models_ok,
            detector_valid=detector_ok,
            cli_valid=cli_ok,
            math_invariants_valid=math_ok,
        )
