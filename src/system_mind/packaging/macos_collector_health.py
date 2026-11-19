"""Automated packaging validator auditing macOS telemetry collector health and timeout architecture."""

from __future__ import annotations

import ast
from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
import time
from typing import List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent

from system_mind.macos.collector_health_manager import (
    CORE_COLLECTORS,
    CollectorHealthManager,
)
from system_mind.macos.collector_health_models import (
    CollectorHealthRecord,
    CollectorResult,
    CollectorStatus,
    CompanionHealthReport,
    PartialDataReason,
)


@dataclass(frozen=True)
class MacOsCollectorHealthAuditResult:
    """Outcome of auditing macOS collector health models, manager, CLI, sensors, and safety invariants."""

    valid: bool
    issues: tuple[str, ...]
    models_valid: bool
    manager_valid: bool
    cli_valid: bool
    sensors_valid: bool
    safety_valid: bool


class MacOsCollectorHealthValidator:
    """Programmatic validator verifying collector health management, timeouts, circuit breaking, and safety."""

    CLI_REL_PATH = Path("tools") / "detect_collector_health.py"
    SENSOR_RUST_PATH = Path("crates") / "system-mind-sensors" / "src" / "macos_collector_health.rs"

    REQUIRED_RECORD_FIELDS = [
        "collector_id",
        "status",
        "latency_ms",
        "timeout_seconds",
        "consecutive_failures",
        "last_success_timestamp",
        "last_error",
        "partial_data",
        "partial_reasons",
        "unavailable_fields",
        "is_operational",
    ]

    REQUIRED_REPORT_FIELDS = [
        "timestamp",
        "host_platform",
        "total_collectors",
        "healthy_count",
        "degraded_count",
        "failed_count",
        "timed_out_count",
        "unsupported_count",
        "overall_status",
        "collectors",
        "partial_data_present",
        "scan_proves_safe",
        "is_mock",
    ]

    def __init__(self, root_dir: Optional[Path] = None) -> None:
        self.root_dir = root_dir or ROOT_DIR
        self.cli_path = self.root_dir / self.CLI_REL_PATH

    def audit(self) -> MacOsCollectorHealthAuditResult:
        """Execute comprehensive audit across collector health models, detector, CLI, and invariants."""
        issues: List[str] = []

        models_valid = self._audit_models(issues)
        manager_valid = self._audit_manager(issues)
        cli_valid = self._audit_cli(issues)
        sensors_valid = self._audit_sensors(issues)
        safety_valid = self._audit_safety_invariants(issues)

        valid = (
            models_valid
            and manager_valid
            and cli_valid
            and sensors_valid
            and safety_valid
            and len(issues) == 0
        )

        return MacOsCollectorHealthAuditResult(
            valid=valid,
            issues=tuple(issues),
            models_valid=models_valid,
            manager_valid=manager_valid,
            cli_valid=cli_valid,
            sensors_valid=sensors_valid,
            safety_valid=safety_valid,
        )

    def audit_all(self) -> MacOsCollectorHealthAuditResult:
        """Alias for audit()."""
        return self.audit()

    def _audit_models(self, issues: List[str]) -> bool:
        """Audit CollectorHealthRecord, CompanionHealthReport, and enum values."""
        valid = True

        if CollectorStatus.HEALTHY.value != "HEALTHY" or CollectorStatus.TIMED_OUT.value != "TIMED_OUT":
            issues.append("CollectorStatus enum value mismatch")
            valid = False

        if PartialDataReason.HARDWARE_ABSENT.value != "HARDWARE_ABSENT":
            issues.append("PartialDataReason enum value mismatch")
            valid = False

        rec = CollectorHealthRecord(
            collector_id="cpu",
            status=CollectorStatus.HEALTHY,
            latency_ms=15.2,
            timeout_seconds=2.0,
            consecutive_failures=0,
            partial_data=False,
        )
        rec_dict = rec.to_dict()
        for f in self.REQUIRED_RECORD_FIELDS:
            if f not in rec_dict:
                issues.append(f"CollectorHealthRecord missing required field: {f}")
                valid = False

        manager = CollectorHealthManager()
        report = manager.collect_all_telemetry(use_mock=True, profile="healthy")
        rep_dict = report.to_dict()
        for f in self.REQUIRED_REPORT_FIELDS:
            if f not in rep_dict:
                issues.append(f"CompanionHealthReport missing required field: {f}")
                valid = False

        # Invariant: scan_proves_safe == False
        if report.scan_proves_safe is not False:
            issues.append("Mandatory charter invariant 'Scan != Safe' violated in CompanionHealthReport")
            valid = False

        return valid

    def _audit_manager(self, issues: List[str]) -> bool:
        """Audit CollectorHealthManager execution, timeouts, circuit breaker, and profiles."""
        valid = True
        manager = CollectorHealthManager(default_timeout_seconds=0.1, max_consecutive_failures=2)

        # Test timeout execution
        def slow_fn() -> str:
            time.sleep(0.3)
            return "slow_success"

        res = manager.execute_collector("slow_collector", slow_fn, timeout_seconds=0.05)
        if res.health.status != CollectorStatus.TIMED_OUT:
            issues.append("Slow collector execution did not yield TIMED_OUT status")
            valid = False
        if not res.health.partial_data or PartialDataReason.TIMEOUT not in res.health.partial_reasons:
            issues.append("TIMED_OUT status did not set partial_data or PartialDataReason.TIMEOUT")
            valid = False

        # Second failure to trigger circuit breaker
        manager.execute_collector("slow_collector", slow_fn, timeout_seconds=0.05)
        res_cb = manager.execute_collector("slow_collector", slow_fn, timeout_seconds=0.05)
        if res_cb.health.status != CollectorStatus.CIRCUIT_BROKEN:
            issues.append("Consecutive failures did not trip CIRCUIT_BROKEN state")
            valid = False

        # Reset collector
        manager.reset_collector("slow_collector")
        if manager.get_consecutive_failures("slow_collector") != 0:
            issues.append("reset_collector did not clear consecutive_failures")
            valid = False

        # Audit mock profiles
        degraded = manager.collect_all_telemetry(use_mock=True, profile="degraded")
        if degraded.overall_status != CollectorStatus.DEGRADED or not degraded.partial_data_present:
            issues.append("Mock degraded profile failed validation")
            valid = False

        timeout_rep = manager.collect_all_telemetry(use_mock=True, profile="timeout")
        if timeout_rep.timed_out_count != 2:
            issues.append("Mock timeout profile failed validation")
            valid = False

        unsupported_rep = manager.collect_all_telemetry(use_mock=True, profile="unsupported")
        if unsupported_rep.overall_status != CollectorStatus.UNSUPPORTED:
            issues.append("Mock unsupported profile failed validation")
            valid = False

        return valid

    def _audit_cli(self, issues: List[str]) -> bool:
        """Verify developer CLI tool exists, is executable, and runs mock profiles."""
        if not self.cli_path.exists():
            issues.append(f"CLI tool not found at {self.cli_path}")
            return False

        if not self.cli_path.stat().st_mode & 0o111:
            issues.append(f"CLI tool at {self.cli_path} is not executable")
            return False

        try:
            res = subprocess.run(
                [sys.executable, str(self.cli_path), "--mock", "--profile", "degraded", "--json"],
                capture_output=True,
                text=True,
                timeout=15.0,
                check=False,
            )
            if res.returncode != 0:
                issues.append(f"CLI --mock --profile degraded failed: {res.stderr}")
                return False
            data = json.loads(res.stdout)
            if data.get("overall_status") != "DEGRADED" or not data.get("partial_data_present"):
                issues.append("CLI output payload validation failed")
                return False
        except Exception as e:
            issues.append(f"CLI execution error: {e}")
            return False

        return True

    def _audit_sensors(self, issues: List[str]) -> bool:
        """Audit native Rust sensor collector implementation."""
        sensor_path = self.root_dir / self.SENSOR_RUST_PATH
        if not sensor_path.exists():
            issues.append(f"Rust sensor collector missing at: {sensor_path}")
            return False

        content = sensor_path.read_text(encoding="utf-8")
        if "CompanionHealthReportSnapshot" not in content:
            issues.append("Rust sensor collector missing CompanionHealthReportSnapshot")
            return False
        if "scan_proves_safe" not in content:
            issues.append("Rust sensor collector missing scan_proves_safe")
            return False
        if "is_operational" not in content:
            issues.append("Rust sensor collector missing is_operational")
            return False

        return True

    def _audit_safety_invariants(self, issues: List[str]) -> bool:
        """Audit safety invariants SC-01 (Zero Ambient Shell) across collector health code."""
        targets = [
            self.root_dir / "src" / "system_mind" / "macos" / "collector_health_manager.py",
            self.root_dir / "src" / "system_mind" / "macos" / "collector_health_models.py",
            self.cli_path,
        ]

        valid = True
        for target in targets:
            if not target.exists():
                continue
            content = target.read_text(encoding="utf-8")
            try:
                tree = ast.parse(content, filename=str(target))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call):
                        if (
                            isinstance(node.func, ast.Attribute)
                            and isinstance(node.func.value, ast.Name)
                            and node.func.value.id == "os"
                            and node.func.attr == "system"
                        ):
                            issues.append(f"{target.name} uses prohibited os.system")
                            valid = False
                        for kw in node.keywords:
                            if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                                issues.append(f"{target.name} invokes subprocess with shell=True")
                                valid = False
            except SyntaxError as e:
                issues.append(f"{target.name} syntax error: {e}")
                valid = False

        return valid
