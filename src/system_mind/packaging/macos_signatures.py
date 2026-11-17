"""Automated packaging validator auditing macOS application signatures and Gatekeeper notarization telemetry."""

from __future__ import annotations

import ast
from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
from typing import List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent

from system_mind.macos.signature_detector import MacAppSignatureDetector
from system_mind.macos.signature_models import (
    MacAppSignatureInfo,
    MacAppSignatureReport,
    NotarizationStatus,
    SignatureStatus,
    SigningAuthorityType,
)


@dataclass(frozen=True)
class MacOsSignaturesAuditResult:
    """Outcome of auditing macOS application signature telemetry engine and CLI tooling."""

    valid: bool
    issues: tuple[str, ...]
    models_valid: bool
    detector_valid: bool
    cli_valid: bool
    safety_valid: bool


class MacOsSignaturesValidator:
    """Programmatic validator verifying macOS signature models, safety invariants, and CLI tools."""

    CLI_REL_PATH = Path("tools") / "detect_signatures.py"

    REQUIRED_SIGNATURE_FIELDS = [
        "bundle_id",
        "bundle_path",
        "executable_path",
        "signature_status",
        "notarization_status",
        "authority_type",
        "authorities",
        "team_id",
        "cdhash",
        "is_hardened_runtime",
        "is_apple",
        "is_valid",
        "scan_proves_safe",
    ]

    REQUIRED_REPORT_FIELDS = [
        "collection_method",
        "timestamp",
        "host_platform",
        "signatures",
        "inspected_apps_count",
        "validly_signed_count",
        "notarized_count",
        "apple_system_count",
        "unsigned_count",
        "warnings",
        "unavailable_telemetry",
    ]

    def __init__(self, root_dir: Optional[Path] = None) -> None:
        self.root_dir = root_dir or ROOT_DIR
        self.cli_path = self.root_dir / self.CLI_REL_PATH

    @classmethod
    def audit(cls, root_dir: Optional[Path] = None) -> MacOsSignaturesAuditResult:
        """Execute comprehensive audit over macOS application signature telemetry components."""
        instance = cls(root_dir)
        return instance._audit_internal()

    def _audit_internal(self) -> MacOsSignaturesAuditResult:
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

        return MacOsSignaturesAuditResult(
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
            # Check model fields
            test_info = MacAppSignatureInfo(
                bundle_id="com.test.App",
                bundle_path="/Applications/Test.app",
                signature_status=SignatureStatus.SIGNED_VALID,
                notarization_status=NotarizationStatus.APPLE_SYSTEM,
                authority_type=SigningAuthorityType.APPLE_SYSTEM,
            )
            as_dict = test_info.to_dict()
            for req in self.REQUIRED_SIGNATURE_FIELDS:
                if req not in as_dict:
                    issues.append(f"MacAppSignatureInfo missing required field '{req}'")
                    success = False

            # Verify Scan != Safe charter invariant
            if as_dict.get("scan_proves_safe") is not False:
                issues.append("MacAppSignatureInfo violated charter invariant: scan_proves_safe must be False")
                success = False

            test_report = MacAppSignatureReport(
                collection_method="MOCK",
                timestamp="2026-01-01T00:00:00Z",
                host_platform="Darwin",
                signatures=[test_info],
                inspected_apps_count=1,
            )
            rep_dict = test_report.to_dict()
            for req in self.REQUIRED_REPORT_FIELDS:
                if req not in rep_dict:
                    issues.append(f"MacAppSignatureReport missing required field '{req}'")
                    success = False

        except Exception as exc:
            issues.append(f"Exception during signature model validation: {exc}")
            success = False

        return success

    def _check_detector(self, issues: List[str]) -> bool:
        success = True
        try:
            detector = MacAppSignatureDetector()
            report = detector.detect(mock=True)

            if not isinstance(report, MacAppSignatureReport):
                issues.append("MacAppSignatureDetector.detect(mock=True) did not return MacAppSignatureReport")
                success = False

            if report.inspected_apps_count < 4:
                issues.append(f"Mock signature report insufficient application count: {report.inspected_apps_count}")
                success = False

            if not any(s.is_apple for s in report.signatures):
                issues.append("Mock report missing Apple first-party signed application")
                success = False

            if not any(s.signature_status == SignatureStatus.UNSIGNED for s in report.signatures):
                issues.append("Mock report missing unsigned application fixture")
                success = False

        except Exception as exc:
            issues.append(f"Exception during detector validation: {exc}")
            success = False

        return success

    def _check_cli(self, issues: List[str]) -> bool:
        success = True
        if not self.cli_path.exists():
            issues.append(f"Signature CLI tool missing at expected location: {self.cli_path}")
            return False

        try:
            cmd = [sys.executable, str(self.cli_path), "--mock", "--json"]
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if res.returncode != 0:
                issues.append(f"Signature CLI --mock --json exited with status {res.returncode}: {res.stderr}")
                success = False
            else:
                data = json.loads(res.stdout)
                if "signatures" not in data or "inspected_apps_count" not in data:
                    issues.append("Signature CLI JSON output missing required keys")
                    success = False
        except Exception as exc:
            issues.append(f"Failed to execute signature CLI tool: {exc}")
            success = False

        return success

    def _check_safety(self, issues: List[str]) -> bool:
        success = True
        files_to_check = [
            self.root_dir / "src" / "system_mind" / "macos" / "signature_detector.py",
            self.root_dir / "src" / "system_mind" / "macos" / "signature_models.py",
            self.cli_path,
        ]

        banned_calls = {"system", "popen"}
        prohibited_strings = [
            "shell=True",
            "codesign --sign",
            "codesign --remove-signature",
            "spctl --master-disable",
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
                        # Detect os.system / os.popen specifically
                        if (
                            isinstance(node.func, ast.Attribute)
                            and isinstance(node.func.value, ast.Name)
                            and node.func.value.id == "os"
                            and node.func.attr in banned_calls
                        ):
                            issues.append(f"Prohibited call os.{node.func.attr} in {fpath.name}:{node.lineno}")
                            success = False
                        # Detect shell=True
                        for kw in node.keywords:
                            if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                                issues.append(f"Prohibited shell=True in {fpath.name}:{node.lineno}")
                                success = False
            except Exception as exc:
                issues.append(f"Failed to perform AST safety scan on {fpath.name}: {exc}")
                success = False

        return success


# Aliases for singular/plural import compatibility
MacOsSignatureValidator = MacOsSignaturesValidator
MacOsSignatureAuditResult = MacOsSignaturesAuditResult
