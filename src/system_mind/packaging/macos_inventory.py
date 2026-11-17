"""Automated packaging validator auditing the read-only macOS inventory API architecture and contracts."""

from __future__ import annotations

import ast
from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
from typing import List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent

from system_mind.api.models import ApiRequest, ApiStatus, ErrorCode
from system_mind.governance.models import ActorIdentity, IdentityType
from system_mind.macos.inventory_api import MacOsInventoryApi
from system_mind.macos.inventory_models import (
    InventorySection,
    MacOsInventoryRequest,
    MacOsInventoryResponse,
    MacOsInventorySummary,
)
from system_mind.macos.privacy_models import PrivacyScrubbingLevel


@dataclass(frozen=True)
class MacOsInventoryAuditResult:
    """Outcome of auditing macOS inventory models, API service, CLI, sensors, and safety invariants."""

    valid: bool
    issues: tuple[str, ...]
    models_valid: bool
    api_valid: bool
    cli_valid: bool
    sensors_valid: bool
    safety_valid: bool


class MacOsInventoryValidator:
    """Programmatic validator verifying the read-only macOS inventory API and aggregation engine."""

    CLI_REL_PATH = Path("tools") / "detect_inventory.py"
    SENSOR_RUST_PATH = Path("crates") / "system-mind-sensors" / "src" / "macos_inventory.rs"

    REQUIRED_SUMMARY_FIELDS = [
        "os_version",
        "os_build",
        "host_name",
        "architecture",
        "cpu_model",
        "physical_cores",
        "logical_cores",
        "total_memory_bytes",
        "memory_pressure_pct",
        "total_storage_bytes",
        "free_storage_bytes",
        "running_process_count",
        "installed_app_count",
        "mean_confidence",
        "overall_health",
    ]

    REQUIRED_RESPONSE_FIELDS = [
        "inventory_id",
        "timestamp_utc",
        "summary",
        "sections",
        "observations",
        "health",
        "privacy_audit",
        "partial_data",
        "scan_proves_safe",
        "is_mock",
    ]

    def __init__(self, root_dir: Optional[Path] = None) -> None:
        self.root_dir = root_dir or ROOT_DIR
        self.cli_path = self.root_dir / self.CLI_REL_PATH

    def audit(self) -> MacOsInventoryAuditResult:
        """Execute comprehensive audit across inventory models, API service, CLI, sensors, and safety."""
        issues: List[str] = []

        models_valid = self._audit_models(issues)
        api_valid = self._audit_api(issues)
        cli_valid = self._audit_cli(issues)
        sensors_valid = self._audit_sensors(issues)
        safety_valid = self._audit_safety_invariants(issues)

        valid = (
            models_valid
            and api_valid
            and cli_valid
            and sensors_valid
            and safety_valid
            and len(issues) == 0
        )

        return MacOsInventoryAuditResult(
            valid=valid,
            issues=tuple(issues),
            models_valid=models_valid,
            api_valid=api_valid,
            cli_valid=cli_valid,
            sensors_valid=sensors_valid,
            safety_valid=safety_valid,
        )

    def audit_all(self) -> MacOsInventoryAuditResult:
        """Alias for audit()."""
        return self.audit()

    def _audit_models(self, issues: List[str]) -> bool:
        """Audit InventorySection enum, MacOsInventoryRequest, Summary, and Response models."""
        valid = True

        expected_sections = {
            "ALL", "IDENTITY", "HARDWARE", "STORAGE", "NETWORK",
            "APPLICATIONS", "SECURITY", "PROCESSES", "SERVICES",
        }
        actual_sections = {s.value for s in InventorySection}
        if expected_sections != actual_sections:
            issues.append(f"InventorySection mismatch: expected {expected_sections}, got {actual_sections}")
            valid = False

        summary = MacOsInventorySummary(
            os_version="14.4.1",
            os_build="23E224",
            host_name="test-host.local",
            architecture="arm64",
            cpu_model="Apple M1",
            physical_cores=8,
            logical_cores=8,
            total_memory_bytes=8589934592,
            memory_pressure_pct=15.5,
            total_storage_bytes=250000000000,
            free_storage_bytes=100000000000,
            running_process_count=150,
            installed_app_count=50,
            mean_confidence=0.925,
            overall_health="HEALTHY",
        )
        s_dict = summary.to_dict()
        for f in self.REQUIRED_SUMMARY_FIELDS:
            if f not in s_dict:
                issues.append(f"MacOsInventorySummary missing field: {f}")
                valid = False

        response = MacOsInventoryResponse(
            inventory_id="inv-test-01",
            timestamp_utc="2026-11-17T12:00:00Z",
            summary=summary,
            sections={"identity": {}},
            scan_proves_safe=False,
            is_mock=True,
        )
        r_dict = response.to_dict()
        for f in self.REQUIRED_RESPONSE_FIELDS:
            if f not in r_dict:
                issues.append(f"MacOsInventoryResponse missing field: {f}")
                valid = False

        if response.scan_proves_safe:
            issues.append("MacOsInventoryResponse.scan_proves_safe must be False")
            valid = False

        return valid

    def _audit_api(self, issues: List[str]) -> bool:
        """Audit MacOsInventoryApi aggregation, section queries, wire handler, and safety."""
        valid = True

        api = MacOsInventoryApi()

        # 1. Summary query
        summary = api.get_summary(use_mock=True)
        if not summary.os_version or summary.physical_cores <= 0:
            issues.append("MacOsInventoryApi.get_summary returned invalid mock data")
            valid = False

        # 2. Section query
        identity_sec = api.get_section(InventorySection.IDENTITY, use_mock=True)
        if not isinstance(identity_sec, dict) or "version_info" not in identity_sec:
            issues.append("MacOsInventoryApi.get_section(IDENTITY) did not return version_info")
            valid = False

        # 3. Full inventory aggregation
        req = MacOsInventoryRequest(
            sections=[InventorySection.ALL],
            privacy_level=PrivacyScrubbingLevel.BALANCED,
            use_mock=True,
        )
        inv = api.get_inventory(req)
        if not inv.is_mock or inv.scan_proves_safe is not False:
            issues.append("Inventory response violated mock or scan_proves_safe invariant")
            valid = False
        if len(inv.sections) < 8:
            issues.append(f"Inventory missing sections: got {len(inv.sections)} sections, expected >= 8")
            valid = False

        # 4. Wire API request handler: success
        actor = ActorIdentity(
            identity_id="dev-01",
            identity_type=IdentityType.LOCAL_CONSOLE_USER,
            principal_name="developer",
        )
        api_req = ApiRequest(
            request_id="req-inv-01",
            api_version="1.0.0",
            method_urn="urn:systemmind:macos:inventory:summary",
            caller_identity=actor,
            params={"use_mock": True},
            is_mutating=False,
        )
        res = api.handle_api_request(api_req)
        if res.status != ApiStatus.SUCCESS or res.data is None:
            issues.append(f"Wire API summary request failed with status {res.status}")
            valid = False

        # 5. Wire API request handler: rejection of mutating request
        mutating_req = ApiRequest(
            request_id="req-inv-02",
            api_version="1.0.0",
            method_urn="urn:systemmind:macos:inventory:get",
            caller_identity=actor,
            params={"use_mock": True},
            is_mutating=True,  # Prohibited!
        )
        mut_res = api.handle_api_request(mutating_req)
        if mut_res.status != ApiStatus.POLICY_REJECTED or mut_res.error is None:
            issues.append("Mutating request was not rejected with POLICY_REJECTED")
            valid = False
        elif mut_res.error.code != ErrorCode.E2001_CHARTER_INVARIANT_BREACH:
            issues.append("Mutating request error code mismatch (expected E2001_CHARTER_INVARIANT_BREACH)")
            valid = False

        return valid

    def _audit_cli(self, issues: List[str]) -> bool:
        """Verify developer CLI tool exists, is executable, and produces valid output."""
        if not self.cli_path.exists():
            issues.append(f"CLI tool not found: {self.CLI_REL_PATH}")
            return False

        try:
            cmd = [sys.executable, str(self.cli_path), "--mock", "--summary", "--json"]
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
            for f in self.REQUIRED_SUMMARY_FIELDS:
                if f not in data:
                    issues.append(f"CLI summary output missing field '{f}'")
                    return False

        except subprocess.TimeoutExpired:
            issues.append("CLI tool timed out (> 5s)")
            return False
        except Exception as exc:
            issues.append(f"CLI execution failed: {exc}")
            return False

        return True

    def _audit_sensors(self, issues: List[str]) -> bool:
        """Verify Rust sensor collector for macOS inventory exists and is registered."""
        sensor_path = self.root_dir / self.SENSOR_RUST_PATH
        if not sensor_path.exists():
            issues.append(f"Rust sensor file missing: {self.SENSOR_RUST_PATH}")
            return False

        lib_rs = self.root_dir / "crates" / "system-mind-sensors" / "src" / "lib.rs"
        if not lib_rs.exists():
            issues.append("crates/system-mind-sensors/src/lib.rs not found")
            return False

        lib_content = lib_rs.read_text(encoding="utf-8")
        if "macos_inventory" not in lib_content:
            issues.append("crates/system-mind-sensors/src/lib.rs does not declare pub mod macos_inventory")
            return False

        return True

    def _audit_safety_invariants(self, issues: List[str]) -> bool:
        """Audit zero ambient shell authority (SC-01) and scan_proves_safe invariants."""
        target_files = [
            self.root_dir / "src" / "system_mind" / "macos" / "inventory_models.py",
            self.root_dir / "src" / "system_mind" / "macos" / "inventory_api.py",
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
