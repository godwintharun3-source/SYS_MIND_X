"""Packaging validator for the Milestone 4 macOS Companion Agent release."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent


@dataclass(frozen=True)
class MacOsCompanionReleaseAuditResult:
    """Outcome of auditing Milestone 4 macOS companion agent release components."""

    valid: bool
    issues: tuple[str, ...]
    collectors_count: int
    rust_sensors_count: int
    charter_invariants_valid: bool
    release_report_present: bool
    cli_present: bool


class MacOsCompanionReleaseValidator:
    """Audits the completeness, safety, and packaging of Milestone 4 release."""

    REQUIRED_PYTHON_COLLECTOR_MODULES = [
        "detector.py",
        "cpu_detector.py",
        "memory_detector.py",
        "storage_detector.py",
        "battery_detector.py",
        "network_detector.py",
        "gpu_detector.py",
        "usb_detector.py",
        "process_detector.py",
        "services_detector.py",
        "app_detector.py",
        "signature_detector.py",
        "fsevents_detector.py",
        "endpoint_security_detector.py",
        "swift_bridge.py",
        "agent_service_detector.py",
        "collector_health_manager.py",
        "observation_engine.py",
        "privacy_filter.py",
        "inventory_api.py",
        "collector_stability.py",
        "permission_inspector.py",
        "companion_runner.py",
    ]

    REQUIRED_RUST_SENSORS = [
        "macos_identity.rs",
        "macos_cpu.rs",
        "macos_memory.rs",
        "macos_storage.rs",
        "macos_battery.rs",
        "macos_network.rs",
        "macos_gpu.rs",
        "macos_usb.rs",
        "macos_process.rs",
        "macos_launchd.rs",
        "macos_apps.rs",
        "macos_signature.rs",
        "macos_fsevents.rs",
        "macos_endpoint_security.rs",
        "macos_swift_bridge.rs",
        "macos_user_agent.rs",
        "macos_collector_health.rs",
        "macos_observations.rs",
        "macos_privacy.rs",
        "macos_inventory.rs",
        "macos_stability.rs",
        "macos_permissions.rs",
    ]

    REQUIRED_DOCS = [
        Path("docs/design/DAY_065_MACOS_COMPANION_AGENT_RELEASE_MILESTONE.md"),
        Path("docs/records/MACOS_COMPANION_AGENT_MILESTONE_4_REPORT.md"),
    ]

    REQUIRED_TOOLS = [
        Path("tools/run_macos_companion.py"),
    ]

    @classmethod
    def audit(cls, root_dir: Optional[Path] = None) -> MacOsCompanionReleaseAuditResult:
        """Executes comprehensive audit across all Milestone 4 components."""
        base = root_dir or ROOT_DIR
        issues: List[str] = []

        # 1. Audit Python collector modules
        macos_dir = base / "src" / "system_mind" / "macos"
        found_collectors = 0
        for mod in cls.REQUIRED_PYTHON_COLLECTOR_MODULES:
            path = macos_dir / mod
            if not path.is_file():
                issues.append(f"Missing required Python module: src/system_mind/macos/{mod}")
            else:
                found_collectors += 1

        # 2. Audit Rust sensor modules
        sensors_dir = base / "crates" / "system-mind-sensors" / "src"
        found_rust = 0
        for rmod in cls.REQUIRED_RUST_SENSORS:
            rpath = sensors_dir / rmod
            if not rpath.is_file():
                issues.append(f"Missing required Rust sensor: crates/system-mind-sensors/src/{rmod}")
            else:
                found_rust += 1

        # 3. Audit Swift companion agent
        swift_main = base / "apps" / "macos-companion" / "Sources" / "SystemMindCompanion" / "main.swift"
        if not swift_main.is_file():
            issues.append(f"Missing Swift companion entrypoint: {swift_main}")

        # 4. Audit CLI and documentation
        for doc in cls.REQUIRED_DOCS:
            if not (base / doc).is_file():
                issues.append(f"Missing required documentation: {doc}")

        for tool in cls.REQUIRED_TOOLS:
            if not (base / tool).is_file():
                issues.append(f"Missing required tool: {tool}")

        # 5. AST Safety check across all Python macos modules (SC-01)
        invariants_ok = True
        for py_file in macos_dir.glob("*.py"):
            try:
                tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call):
                        # Detect os.system
                        if isinstance(node.func, ast.Attribute) and node.func.attr == "system":
                            if isinstance(node.func.value, ast.Name) and node.func.value.id == "os":
                                issues.append(f"Prohibited os.system in {py_file.name}")
                                invariants_ok = False
                        # Detect shell=True
                        for kw in node.keywords:
                            if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                                issues.append(f"Prohibited shell=True in {py_file.name}")
                                invariants_ok = False
            except Exception as e:
                issues.append(f"Failed to parse AST for {py_file.name}: {e}")
                invariants_ok = False

        # 6. Verify scan_proves_safe invariant on companion models (SC-03)
        try:
            from system_mind.macos.companion_models import (
                CompanionCycleTelemetry,
                MacOsCompanionReleaseReport,
            )

            test_cycle = CompanionCycleTelemetry(
                cycle_id=1,
                timestamp_utc="2026-11-18T00:00:00Z",
                operational_status=None,  # type: ignore
                duration_ms=10.0,
                partial_data=False,
            )
            if test_cycle.scan_proves_safe is not False:
                issues.append("CompanionCycleTelemetry does not default scan_proves_safe to False")
                invariants_ok = False

            test_rep = MacOsCompanionReleaseReport(
                report_id="test",
                host_platform="macOS",
                apple_silicon_native=True,
                cycles_completed=1,
                latest_cycle=test_cycle,
            )
            if test_rep.scan_proves_safe is not False:
                issues.append("MacOsCompanionReleaseReport does not default scan_proves_safe to False")
                invariants_ok = False
        except Exception as e:
            issues.append(f"Companion models import/verification failed: {e}")
            invariants_ok = False

        return MacOsCompanionReleaseAuditResult(
            valid=len(issues) == 0,
            issues=tuple(issues),
            collectors_count=found_collectors,
            rust_sensors_count=found_rust,
            charter_invariants_valid=invariants_ok,
            release_report_present=(base / cls.REQUIRED_DOCS[1]).is_file(),
            cli_present=(base / cls.REQUIRED_TOOLS[0]).is_file(),
        )
