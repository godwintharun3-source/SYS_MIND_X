"""Automated packaging validator auditing collector stability under sustained event volume."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Set

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent


@dataclass(frozen=True)
class MacOsCollectorStabilityAuditResult:
    """Outcome of auditing macOS collector stability tests, AST safety, and charter invariants."""

    valid: bool
    issues: tuple[str, ...]
    stability_test_valid: bool
    ast_safety_valid: bool
    scenarios_valid: bool
    rust_sensors_valid: bool
    invariants_valid: bool
    cli_valid: bool
    scenario_count: int


class MacOsCollectorStabilityValidator:
    """Programmatic validator verifying collector stability under sustained event volume."""

    STABILITY_TEST_PATH = Path("tests") / "test_macos_collector_stability_sustained_volume.py"
    CLI_REL_PATH = Path("tools") / "detect_collector_stability.py"

    REQUIRED_SCENARIOS = [
        "burst_fsevents",
        "drop_newest",
        "event_coalescing",
        "process_storm",
        "drain_latency",
        "multithreaded_concurrency",
        "memory_stability",
        "pressure_level_transitions",
    ]

    RUST_SENSOR_FILE = "macos_stability.rs"

    def __init__(self, root_dir: Optional[Path] = None) -> None:
        self.root_dir = root_dir or ROOT_DIR
        self.stability_test_file = self.root_dir / self.STABILITY_TEST_PATH
        self.cli_file = self.root_dir / self.CLI_REL_PATH
        self.sensors_dir = self.root_dir / "crates" / "system-mind-sensors" / "src"

    def audit(self) -> MacOsCollectorStabilityAuditResult:
        """Execute comprehensive audit across collector stability tests, AST safety, and invariants."""
        issues: List[str] = []

        # 1. Verify stability test file presence
        stability_test_valid = False
        if not self.stability_test_file.exists():
            issues.append(f"Missing stability test suite: {self.STABILITY_TEST_PATH}")
        else:
            stability_test_valid = True

        # 2. Verify developer CLI tool presence
        cli_valid = False
        if not self.cli_file.exists():
            issues.append(f"Missing developer CLI tool: {self.CLI_REL_PATH}")
        else:
            cli_valid = True

        # 3. AST safety checks (zero shell=True, zero os.system across stability implementation and test)
        ast_safety_valid = True
        target_python_files = [
            self.root_dir / "src" / "system_mind" / "macos" / "collector_stability.py",
            self.root_dir / "src" / "system_mind" / "macos" / "collector_stability_models.py",
            self.stability_test_file,
        ]

        for py_file in target_python_files:
            if not py_file.exists():
                issues.append(f"File missing for AST safety check: {py_file.name}")
                ast_safety_valid = False
                continue

            try:
                content = py_file.read_text(encoding="utf-8")
                tree = ast.parse(content, filename=str(py_file))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call):
                        if (
                            isinstance(node.func, ast.Attribute)
                            and node.func.attr == "system"
                            and isinstance(node.func.value, ast.Name)
                            and node.func.value.id == "os"
                        ):
                            issues.append(f"Forbidden os.system in {py_file.name}:{node.lineno}")
                            ast_safety_valid = False

                        for kw in node.keywords:
                            if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                                issues.append(f"Forbidden shell=True in {py_file.name}:{node.lineno}")
                                ast_safety_valid = False
            except Exception as e:
                issues.append(f"Failed to parse AST for {py_file.name}: {e}")
                ast_safety_valid = False

        # 4. Verify all required stability stress scenarios exist
        scenarios_valid = True
        scenario_count = 0
        if stability_test_valid:
            try:
                test_content = self.stability_test_file.read_text(encoding="utf-8")
                for scenario in self.REQUIRED_SCENARIOS:
                    if scenario not in test_content:
                        issues.append(f"Missing stability stress scenario in tests: {scenario}")
                        scenarios_valid = False
                    else:
                        scenario_count += 1
            except Exception as e:
                issues.append(f"Failed to inspect test content: {e}")
                scenarios_valid = False

        # 5. Verify native Rust sensor implementation
        rust_sensors_valid = True
        rust_sensor_path = self.sensors_dir / self.RUST_SENSOR_FILE
        if not rust_sensor_path.exists():
            issues.append(f"Missing Rust sensor implementation: {self.RUST_SENSOR_FILE}")
            rust_sensors_valid = False
        else:
            # Check lib.rs re-export
            lib_rs = self.sensors_dir / "lib.rs"
            if lib_rs.exists():
                lib_content = lib_rs.read_text(encoding="utf-8")
                if "pub mod macos_stability;" not in lib_content:
                    issues.append("Rust lib.rs missing pub mod macos_stability;")
                    rust_sensors_valid = False
            else:
                issues.append("Rust sensors lib.rs missing")
                rust_sensors_valid = False

        # 6. Verify non-negotiable charter invariant (scan_proves_safe = False)
        invariants_valid = True
        try:
            from system_mind.macos.collector_stability_models import (
                BufferCapacityMetrics,
                CollectorStabilityReport,
                TelemetryEvent,
            )

            ev = TelemetryEvent("ev", "fsevents", "created", "/tmp/t", scan_proves_safe=True)
            if ev.scan_proves_safe is not False:
                issues.append("TelemetryEvent allowed scan_proves_safe = True")
                invariants_valid = False

            metrics = BufferCapacityMetrics(
                max_capacity=10,
                current_depth=0,
                high_water_mark=0,
                total_ingested=0,
                total_emitted=0,
                total_dropped=0,
                total_coalesced=0,
                scan_proves_safe=True,
            )
            if metrics.scan_proves_safe is not False:
                issues.append("BufferCapacityMetrics allowed scan_proves_safe = True")
                invariants_valid = False

            from system_mind.macos.collector_stability_models import CollectorOperationalStatus

            rep = CollectorStabilityReport(
                collector_name="test",
                status=CollectorOperationalStatus.HEALTHY,
                scan_proves_safe=True,
            )
            if rep.scan_proves_safe is not False:
                issues.append("CollectorStabilityReport allowed scan_proves_safe = True")
                invariants_valid = False
        except Exception as e:
            issues.append(f"Invariant check failed with error: {e}")
            invariants_valid = False

        valid = (
            stability_test_valid
            and ast_safety_valid
            and scenarios_valid
            and rust_sensors_valid
            and invariants_valid
            and cli_valid
            and len(issues) == 0
        )

        return MacOsCollectorStabilityAuditResult(
            valid=valid,
            issues=tuple(issues),
            stability_test_valid=stability_test_valid,
            ast_safety_valid=ast_safety_valid,
            scenarios_valid=scenarios_valid,
            rust_sensors_valid=rust_sensors_valid,
            invariants_valid=invariants_valid,
            cli_valid=cli_valid,
            scenario_count=scenario_count,
        )
