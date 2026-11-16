"""Automated packaging validator auditing macOS process inventory and resource telemetry."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
from typing import List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent

from system_mind.macos.process_detector import MacProcessDetector
from system_mind.macos.process_models import (
    MacProcessInfo,
    MacProcessReport,
    ProcessRole,
    ProcessState,
)
from system_mind.platform.adapter import MockPlatformProfileFactory


@dataclass(frozen=True)
class MacOsProcessAuditResult:
    """Outcome of auditing macOS companion agent process telemetry engine and CLI tooling."""

    valid: bool
    issues: tuple[str, ...]
    models_valid: bool
    detector_valid: bool
    cli_valid: bool
    safety_valid: bool


class MacOsProcessValidator:
    """Programmatic validator verifying macOS process data models, safety rules, and CLI tools."""

    CLI_REL_PATH = Path("tools") / "detect_processes.py"

    REQUIRED_REPORT_FIELDS = [
        "processes",
        "total_process_count",
        "running_count",
        "sleeping_count",
        "zombie_count",
        "system_core_count",
        "user_app_count",
        "total_cpu_percent",
        "total_rss_bytes",
        "collected_at_epoch_secs",
        "collection_method",
        "unavailable_telemetry",
        "warnings",
    ]

    REQUIRED_PROCESS_FIELDS = [
        "pid",
        "ppid",
        "uid",
        "user",
        "name",
        "command_path",
        "cpu_percent",
        "memory_percent",
        "rss_bytes",
        "vsz_bytes",
        "state",
        "state_raw",
        "role",
        "is_system_core",
        "is_user_app",
    ]

    def __init__(self, root_dir: Optional[Path] = None) -> None:
        self.root_dir = root_dir or ROOT_DIR
        self.cli_path = self.root_dir / self.CLI_REL_PATH

    @classmethod
    def audit(cls, root_dir: Optional[Path] = None) -> MacOsProcessAuditResult:
        """Execute comprehensive audit over macOS process telemetry components."""
        instance = cls(root_dir)
        return instance._audit_internal()

    def _audit_internal(self) -> MacOsProcessAuditResult:
        issues: List[str] = []

        models_valid = self._audit_models(issues)
        detector_valid, safety_valid = self._audit_detector(issues)
        cli_valid = self._audit_cli(issues)

        valid = models_valid and detector_valid and cli_valid and safety_valid
        return MacOsProcessAuditResult(
            valid=valid,
            issues=tuple(issues),
            models_valid=models_valid,
            detector_valid=detector_valid,
            cli_valid=cli_valid,
            safety_valid=safety_valid,
        )

    def _audit_models(self, issues: List[str]) -> bool:
        passed = True
        try:
            proc = MacProcessInfo(
                pid=1,
                ppid=0,
                uid=0,
                user="root",
                name="launchd",
                command_path="/sbin/launchd",
                cpu_percent=0.1,
                memory_percent=0.1,
                rss_bytes=1024 * 1024,
                vsz_bytes=100 * 1024 * 1024,
                state=ProcessState.SLEEPING,
                state_raw="Ss",
                role=ProcessRole.SYSTEM_CORE,
                is_system_core=True,
                is_user_app=False,
            )

            for field_name in self.REQUIRED_PROCESS_FIELDS:
                if not hasattr(proc, field_name):
                    issues.append(f"MacProcessInfo missing required field: {field_name}")
                    passed = False

            report = MacProcessReport(
                processes=[proc],
                total_process_count=1,
                running_count=0,
                sleeping_count=1,
                zombie_count=0,
                system_core_count=1,
                user_app_count=0,
                total_cpu_percent=0.1,
                total_rss_bytes=1024 * 1024,
            )

            for field_name in self.REQUIRED_REPORT_FIELDS:
                if not hasattr(report, field_name):
                    issues.append(f"MacProcessReport missing required field: {field_name}")
                    passed = False

            # Test helper query methods
            if len(report.get_top_cpu(1)) != 1:
                issues.append("MacProcessReport.get_top_cpu failed")
                passed = False
            if len(report.get_top_memory(1)) != 1:
                issues.append("MacProcessReport.get_top_memory failed")
                passed = False
            if len(report.filter_by_user("root")) != 1:
                issues.append("MacProcessReport.filter_by_user failed")
                passed = False
            if report.find_by_pid(1) is None:
                issues.append("MacProcessReport.find_by_pid failed")
                passed = False

        except Exception as exc:
            issues.append(f"Model instantiation failure: {exc}")
            passed = False

        return passed

    def _audit_detector(self, issues: List[str]) -> tuple[bool, bool]:
        detector_passed = True
        safety_passed = True

        try:
            detector = MacProcessDetector()
            mock = MockPlatformProfileFactory.create_macos_apple_silicon_mock()
            report = detector.detect(use_mock=True, mock_adapter=mock)

            if not report.processes:
                issues.append("Mock process report returned zero processes")
                detector_passed = False

            if report.collection_method != "MOCK_PLATFORM_ADAPTER":
                issues.append(f"Unexpected collection method for mock: {report.collection_method}")
                detector_passed = False

            # Safety audit: verify no mutating commands in detector methods (INV-PROC-04)
            detector_code = (self.root_dir / "src" / "system_mind" / "macos" / "process_detector.py").read_text()
            forbidden_patterns = ["os.kill", "signal.SIGKILL", "pkill", "killall", "renice"]
            for pat in forbidden_patterns:
                if pat in detector_code:
                    issues.append(f"Detector code contains prohibited mutating process pattern: '{pat}'")
                    safety_passed = False

            # Test parse_ps_line directly
            sample_line = "    1     0     0 root               0.2  0.1  13760 488724880 Ss   /sbin/launchd"
            parsed = detector.parse_ps_line(sample_line)
            if not parsed or parsed.pid != 1 or parsed.user != "root" or not parsed.is_system_core:
                issues.append("parse_ps_line output does not match expected fields")
                detector_passed = False

        except Exception as exc:
            issues.append(f"Detector audit failure: {exc}")
            detector_passed = False
            safety_passed = False

        return detector_passed, safety_passed

    def _audit_cli(self, issues: List[str]) -> bool:
        if not self.cli_path.is_file():
            issues.append(f"CLI tool missing at expected location: {self.cli_path}")
            return False

        try:
            proc = subprocess.run(
                [sys.executable, str(self.cli_path), "--mock", "--json"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if proc.returncode != 0:
                issues.append(f"CLI exited with non-zero code {proc.returncode}: {proc.stderr}")
                return False

            data = json.loads(proc.stdout)
            for field_name in self.REQUIRED_REPORT_FIELDS:
                if field_name not in data:
                    issues.append(f"CLI JSON output missing key: {field_name}")
                    return False

            if not data.get("processes"):
                issues.append("CLI JSON returned empty processes list")
                return False

            return True

        except subprocess.TimeoutExpired:
            issues.append("CLI invocation timed out after 5s")
            return False
        except json.JSONDecodeError as exc:
            issues.append(f"CLI did not return valid JSON: {exc}")
            return False
        except Exception as exc:
            issues.append(f"CLI audit failure: {exc}")
            return False
