"""Automated packaging validator auditing macOS telemetry privacy filters and metadata sanitization architecture."""

from __future__ import annotations

import ast
from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
from typing import List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent

from system_mind.macos.privacy_filter import (
    KEY_VAULT_PATTERNS,
    PERSONAL_FOLDERS,
    SECRET_PATTERNS,
    MacPrivacyFilter,
)
from system_mind.macos.privacy_models import (
    PrivacyFilterAuditRecord,
    PrivacyRuleCategory,
    PrivacyScrubbingLevel,
    SanitizedTelemetryEnvelope,
)


@dataclass(frozen=True)
class MacOsPrivacyAuditResult:
    """Outcome of auditing macOS privacy models, filter engine, CLI, sensors, and safety invariants."""

    valid: bool
    issues: tuple[str, ...]
    models_valid: bool
    filter_valid: bool
    cli_valid: bool
    sensors_valid: bool
    safety_valid: bool


class MacOsPrivacyValidator:
    """Programmatic validator verifying telemetry privacy filters, path masking, and metadata sanitization."""

    CLI_REL_PATH = Path("tools") / "detect_privacy_filter.py"
    SENSOR_RUST_PATH = Path("crates") / "system-mind-sensors" / "src" / "macos_privacy.rs"

    REQUIRED_AUDIT_FIELDS = [
        "sanitized_usernames_count",
        "sanitized_paths_count",
        "sanitized_metadata_count",
        "redacted_secrets_count",
        "total_redactions",
        "level",
        "rules_applied",
        "scan_proves_safe",
    ]

    REQUIRED_ENVELOPE_FIELDS = [
        "envelope_id",
        "collector_id",
        "payload",
        "audit",
        "scan_proves_safe",
        "is_mock",
    ]

    def __init__(self, root_dir: Optional[Path] = None) -> None:
        self.root_dir = root_dir or ROOT_DIR
        self.cli_path = self.root_dir / self.CLI_REL_PATH

    def audit(self) -> MacOsPrivacyAuditResult:
        """Execute comprehensive audit across privacy models, engine, CLI, sensors, and safety."""
        issues: List[str] = []

        models_valid = self._audit_models(issues)
        filter_valid = self._audit_filter(issues)
        cli_valid = self._audit_cli(issues)
        sensors_valid = self._audit_sensors(issues)
        safety_valid = self._audit_safety_invariants(issues)

        valid = (
            models_valid
            and filter_valid
            and cli_valid
            and sensors_valid
            and safety_valid
            and len(issues) == 0
        )

        return MacOsPrivacyAuditResult(
            valid=valid,
            issues=tuple(issues),
            models_valid=models_valid,
            filter_valid=filter_valid,
            cli_valid=cli_valid,
            sensors_valid=sensors_valid,
            safety_valid=safety_valid,
        )

    def audit_all(self) -> MacOsPrivacyAuditResult:
        """Alias for audit()."""
        return self.audit()

    def _audit_models(self, issues: List[str]) -> bool:
        """Audit PrivacyScrubbingLevel, PrivacyRuleCategory, and SanitizedTelemetryEnvelope models."""
        valid = True

        if PrivacyScrubbingLevel.STRICT.value != "STRICT":
            issues.append("PrivacyScrubbingLevel.STRICT value mismatch")
            valid = False
        if PrivacyScrubbingLevel.BALANCED.value != "BALANCED":
            issues.append("PrivacyScrubbingLevel.BALANCED value mismatch")
            valid = False
        if PrivacyScrubbingLevel.MINIMAL.value != "MINIMAL":
            issues.append("PrivacyScrubbingLevel.MINIMAL value mismatch")
            valid = False

        expected_categories = {"USERNAME", "PERSONAL_FOLDER", "PROTECTED_VAULT", "DOCUMENT_METADATA", "TOKEN_OR_SECRET"}
        actual_categories = {c.value for c in PrivacyRuleCategory}
        if expected_categories != actual_categories:
            issues.append(f"PrivacyRuleCategory values mismatch: expected {expected_categories}, got {actual_categories}")
            valid = False

        audit = PrivacyFilterAuditRecord(
            sanitized_usernames_count=2,
            sanitized_paths_count=3,
            sanitized_metadata_count=1,
            redacted_secrets_count=4,
            level=PrivacyScrubbingLevel.BALANCED,
            rules_applied=["R1", "R2"],
            scan_proves_safe=False,
        )
        if audit.total_redactions != 10:
            issues.append(f"total_redactions expected 10, got {audit.total_redactions}")
            valid = False

        audit_dict = audit.to_dict()
        for f in self.REQUIRED_AUDIT_FIELDS:
            if f not in audit_dict:
                issues.append(f"PrivacyFilterAuditRecord missing required field: {f}")
                valid = False

        env = SanitizedTelemetryEnvelope(
            envelope_id="sanitized-test-env",
            collector_id="fsevents",
            payload={"key": "val"},
            audit=audit,
            scan_proves_safe=False,
            is_mock=False,
        )
        env_dict = env.to_dict()
        for f in self.REQUIRED_ENVELOPE_FIELDS:
            if f not in env_dict:
                issues.append(f"SanitizedTelemetryEnvelope missing required field: {f}")
                valid = False

        if env.scan_proves_safe or audit.scan_proves_safe:
            issues.append("scan_proves_safe must be False")
            valid = False

        return valid

    def _audit_filter(self, issues: List[str]) -> bool:
        """Audit MacPrivacyFilter sanitization rules, pseudonymization, and payload handling."""
        valid = True

        filter_engine = MacPrivacyFilter(
            level=PrivacyScrubbingLevel.BALANCED,
            extra_usernames={"testdev"},
        )

        # Pseudonymization
        pseudo1 = filter_engine.pseudonymize_username("testdev")
        pseudo2 = filter_engine.pseudonymize_username("testdev")
        if pseudo1 != pseudo2 or not pseudo1.startswith("user_"):
            issues.append("Username pseudonymization not deterministic or invalid format")
            valid = False

        # Path sanitization
        clean_path, modified, reasons = filter_engine.sanitize_path("/Users/testdev/Documents/Secret.docx")
        if not modified or "<PROTECTED_DOCUMENTS>" not in clean_path:
            issues.append("Personal folder path not properly sanitized")
            valid = False

        clean_vault, v_mod, _ = filter_engine.sanitize_path("/Users/testdev/.ssh/id_rsa")
        if not v_mod or "<PROTECTED_KEY_VAULT>/ssh" not in clean_vault:
            issues.append("Key vault path not properly sanitized")
            valid = False

        # Preserve system paths
        clean_sys, sys_mod, _ = filter_engine.sanitize_path("/System/Library/CoreServices/SystemVersion.plist")
        if sys_mod or clean_sys != "/System/Library/CoreServices/SystemVersion.plist":
            issues.append("System path should not be modified by privacy filter")
            valid = False

        # Secrets redaction
        clean_sec, u, p, m, s = filter_engine.sanitize_string("Token: Bearer secret_access_token_12345678")
        if s == 0 or "Bearer <REDACTED_TOKEN>" not in clean_sec:
            issues.append("Secret token not redacted")
            valid = False

        # Payload sanitization
        sample_payload = {
            "path": "/Users/testdev/Desktop/plan.pdf",
            "auth": "AKIAIOSFODNN7EXAMPLE",
        }
        sanitized_dict, audit_rec = filter_engine.sanitize_payload(sample_payload)
        if audit_rec.total_redactions < 2:
            issues.append("Payload sanitization missed expected redactions")
            valid = False

        return valid

    def _audit_cli(self, issues: List[str]) -> bool:
        """Verify developer CLI tool exists, is executable, and produces valid output."""
        if not self.cli_path.exists():
            issues.append(f"CLI tool not found: {self.CLI_REL_PATH}")
            return False

        try:
            cmd = [sys.executable, str(self.cli_path), "--mock", "--json"]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if result.returncode != 0:
                issues.append(f"CLI returned non-zero exit code {result.returncode}: {result.stderr.strip()}")
                return False

            data = json.loads(result.stdout)
            for f in self.REQUIRED_ENVELOPE_FIELDS:
                if f not in data:
                    issues.append(f"CLI output missing envelope field '{f}'")
                    return False

            if data.get("scan_proves_safe") is not False:
                issues.append("CLI output scan_proves_safe is not False")
                return False

        except subprocess.TimeoutExpired:
            issues.append("CLI tool timed out (> 5s)")
            return False
        except Exception as exc:
            issues.append(f"CLI execution failed: {exc}")
            return False

        return True

    def _audit_sensors(self, issues: List[str]) -> bool:
        """Verify Rust sensor collector for macOS privacy filter exists and is registered."""
        sensor_path = self.root_dir / self.SENSOR_RUST_PATH
        if not sensor_path.exists():
            issues.append(f"Rust sensor file missing: {self.SENSOR_RUST_PATH}")
            return False

        lib_rs = self.root_dir / "crates" / "system-mind-sensors" / "src" / "lib.rs"
        if not lib_rs.exists():
            issues.append("crates/system-mind-sensors/src/lib.rs not found")
            return False

        lib_content = lib_rs.read_text(encoding="utf-8")
        if "macos_privacy" not in lib_content:
            issues.append("crates/system-mind-sensors/src/lib.rs does not declare pub mod macos_privacy")
            return False

        return True

    def _audit_safety_invariants(self, issues: List[str]) -> bool:
        """Audit zero ambient shell authority (SC-01) and scan_proves_safe invariants."""
        target_files = [
            self.root_dir / "src" / "system_mind" / "macos" / "privacy_models.py",
            self.root_dir / "src" / "system_mind" / "macos" / "privacy_filter.py",
            self.cli_path,
        ]

        valid = True
        for fpath in target_files:
            if not fpath.exists():
                issues.append(f"Target file not found for safety audit: {fpath}")
                valid = False
                continue

            try:
                tree = ast.parse(fpath.read_text(encoding="utf-8"), filename=str(fpath))
            except Exception as e:
                issues.append(f"Failed to parse AST for {fpath}: {e}")
                valid = False
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    # Check for shell=True
                    for kw in node.keywords:
                        if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                            issues.append(f"CRITICAL SAFETY VIOLATION: shell=True found in {fpath.name} line {node.lineno}")
                            valid = False

                    # Check for os.system
                    if isinstance(node.func, ast.Attribute) and node.func.attr == "system":
                        if isinstance(node.func.value, ast.Name) and node.func.value.id == "os":
                            issues.append(f"CRITICAL SAFETY VIOLATION: os.system call found in {fpath.name} line {node.lineno}")
                            valid = False

        return valid
