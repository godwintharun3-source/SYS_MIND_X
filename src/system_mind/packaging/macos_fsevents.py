"""Automated packaging validator auditing macOS FSEvents filesystem change notification telemetry."""

from __future__ import annotations

import ast
from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
from typing import List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent

from system_mind.macos.fsevents_detector import MacFsEventsDetector
from system_mind.macos.fsevents_models import (
    FsEventFlag,
    FsEventNotification,
    FsEventSnapshotReport,
    FsEventStreamConfig,
)


@dataclass(frozen=True)
class MacOsFsEventsAuditResult:
    """Outcome of auditing macOS FSEvents telemetry engine and CLI tooling."""

    valid: bool
    issues: tuple[str, ...]
    models_valid: bool
    detector_valid: bool
    cli_valid: bool
    safety_valid: bool


class MacOsFsEventsValidator:
    """Programmatic validator verifying macOS FSEvents models, safety invariants, and CLI tools."""

    CLI_REL_PATH = Path("tools") / "detect_fsevents.py"

    REQUIRED_EVENT_FIELDS = [
        "event_id",
        "path",
        "flags",
        "raw_flags",
        "timestamp",
        "is_file",
        "is_dir",
        "is_symlink",
        "is_created",
        "is_removed",
        "is_modified",
        "is_renamed",
    ]

    REQUIRED_REPORT_FIELDS = [
        "collection_method",
        "timestamp",
        "host_platform",
        "monitored_paths",
        "events_count",
        "created_count",
        "modified_count",
        "removed_count",
        "renamed_count",
        "events",
        "warnings",
        "unavailable_telemetry",
    ]

    def __init__(self, root_dir: Optional[Path] = None) -> None:
        self.root_dir = root_dir or ROOT_DIR
        self.cli_path = self.root_dir / self.CLI_REL_PATH

    @classmethod
    def audit(cls, root_dir: Optional[Path] = None) -> MacOsFsEventsAuditResult:
        """Execute comprehensive audit over macOS FSEvents telemetry components."""
        instance = cls(root_dir)
        return instance._audit_internal()

    def _audit_internal(self) -> MacOsFsEventsAuditResult:
        issues: List[str] = []

        models_valid = self._check_models(issues)
        detector_valid = self._check_detector(issues)
        cli_valid = self._check_cli(issues)
        safety_valid = self._check_safety(issues)

        is_valid = (
            len(issues) == 0
            and models_valid
            and detector_valid
            and cli_valid
            and safety_valid
        )

        return MacOsFsEventsAuditResult(
            valid=is_valid,
            issues=tuple(issues),
            models_valid=models_valid,
            detector_valid=detector_valid,
            cli_valid=cli_valid,
            safety_valid=safety_valid,
        )

    def _check_models(self, issues: List[str]) -> bool:
        success = True
        try:
            test_ev = FsEventNotification(
                event_id=1,
                path="/Applications/Test.app",
                flags=[FsEventFlag.ITEM_CREATED, FsEventFlag.ITEM_IS_DIR],
                raw_flags=0x00020100,
                timestamp="2026-01-01T00:00:00Z",
                is_dir=True,
            )
            as_dict = test_ev.to_dict()
            for req in self.REQUIRED_EVENT_FIELDS:
                if req not in as_dict:
                    issues.append(f"FsEventNotification missing required field '{req}'")
                    success = False

            test_rep = FsEventSnapshotReport(
                collection_method="MOCK",
                timestamp="2026-01-01T00:00:00Z",
                host_platform="Darwin",
                monitored_paths=["/Applications"],
                events=[test_ev],
                events_count=1,
                created_count=1,
            )
            rep_dict = test_rep.to_dict()
            for req in self.REQUIRED_REPORT_FIELDS:
                if req not in rep_dict:
                    issues.append(f"FsEventSnapshotReport missing required field '{req}'")
                    success = False

        except Exception as exc:
            issues.append(f"Exception during FSEvents model validation: {exc}")
            success = False

        return success

    def _check_detector(self, issues: List[str]) -> bool:
        success = True
        try:
            detector = MacFsEventsDetector()
            report = detector.detect(mock=True)

            if not isinstance(report, FsEventSnapshotReport):
                issues.append("MacFsEventsDetector.detect(mock=True) did not return FsEventSnapshotReport")
                success = False

            if report.events_count < 3:
                issues.append(f"Mock FSEvents report insufficient event count: {report.events_count}")
                success = False

            if not any(e.is_created for e in report.events):
                issues.append("Mock report missing item creation event")
                success = False

            if not any(e.is_modified for e in report.events):
                issues.append("Mock report missing item modification event")
                success = False

            # Verify privacy path exclusion enforcement (INV-FS-02)
            if not detector.is_path_allowed("~/.ssh/id_rsa"):
                pass  # Correctly excluded
            else:
                issues.append("Privacy leak: detector allowed ~/.ssh path")
                success = False

        except Exception as exc:
            issues.append(f"Exception during detector validation: {exc}")
            success = False

        return success

    def _check_cli(self, issues: List[str]) -> bool:
        success = True
        if not self.cli_path.exists():
            issues.append(f"FSEvents CLI tool missing at expected location: {self.cli_path}")
            return False

        try:
            cmd = [sys.executable, str(self.cli_path), "--mock", "--json"]
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=15.0,
                check=False,
            )
            if res.returncode != 0:
                issues.append(f"FSEvents CLI --mock --json exited with status {res.returncode}: {res.stderr}")
                success = False
            else:
                data = json.loads(res.stdout)
                if "events" not in data or "events_count" not in data:
                    issues.append("FSEvents CLI JSON output missing required keys")
                    success = False
        except Exception as exc:
            issues.append(f"Failed to execute FSEvents CLI tool: {exc}")
            success = False

        return success

    def _check_safety(self, issues: List[str]) -> bool:
        success = True
        files_to_check = [
            self.root_dir / "src" / "system_mind" / "macos" / "fsevents_detector.py",
            self.root_dir / "src" / "system_mind" / "macos" / "fsevents_models.py",
            self.cli_path,
        ]

        banned_calls = {"system", "popen"}
        prohibited_strings = [
            "shell=True",
            "rm -rf",
            "shutil.rmtree",
            "os.remove",
        ]

        for fpath in files_to_check:
            if not fpath.exists():
                continue
            try:
                code_text = fpath.read_text(encoding="utf-8")
                for prob in prohibited_strings:
                    if prob in code_text:
                        issues.append(f"Prohibited pattern '{prob}' found in {fpath.name}")
                        success = False

                tree = ast.parse(code_text, filename=str(fpath))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call):
                        if (
                            isinstance(node.func, ast.Attribute)
                            and isinstance(node.func.value, ast.Name)
                            and node.func.value.id == "os"
                            and node.func.attr in banned_calls
                        ):
                            issues.append(f"Prohibited call os.{node.func.attr} in {fpath.name}:{node.lineno}")
                            success = False
                        for kw in node.keywords:
                            if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                                issues.append(f"Prohibited shell=True in {fpath.name}:{node.lineno}")
                                success = False
            except Exception as exc:
                issues.append(f"Failed to perform AST safety scan on {fpath.name}: {exc}")
                success = False

        return success


# Aliases for singular/plural import compatibility
MacOsFsEventValidator = MacOsFsEventsValidator
MacOsFsEventAuditResult = MacOsFsEventsAuditResult
