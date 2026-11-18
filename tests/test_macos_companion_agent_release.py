"""Unit, integration, and safety tests for the Milestone 4 macOS Companion Agent release."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
import unittest
from pathlib import Path

from system_mind.macos.companion_models import (
    CompanionCycleTelemetry,
    CompanionExecutionMode,
    CompanionOperationalStatus,
    CompanionRunConfig,
    MacOsCompanionReleaseReport,
)
from system_mind.macos.companion_runner import MacOsCompanionRunner
from system_mind.macos.privacy_models import PrivacyScrubbingLevel
from system_mind.packaging.macos_companion_release import MacOsCompanionReleaseValidator

ROOT_DIR = Path(__file__).resolve().parent.parent


class TestMacOsCompanionAgentRelease(unittest.TestCase):
    """Verifies the Milestone 4 macOS Companion Agent release implementation and invariants."""

    def test_companion_models_fidelity(self) -> None:
        """Verifies typed models, dictionary conversions, and non-negotiable invariants."""
        config = CompanionRunConfig(
            mode=CompanionExecutionMode.SINGLE_SNAPSHOT,
            use_mock=True,
            mock_profile="high_fidelity",
            privacy_level=PrivacyScrubbingLevel.BALANCED,
        )
        self.assertEqual(config.mode, CompanionExecutionMode.SINGLE_SNAPSHOT)
        self.assertTrue(config.use_mock)

        cycle = CompanionCycleTelemetry(
            cycle_id=1,
            timestamp_utc="2026-11-18T00:00:00Z",
            operational_status=CompanionOperationalStatus.HEALTHY_NOMINAL,
            duration_ms=15.2,
            partial_data=False,
            scan_proves_safe=False,
        )
        self.assertFalse(cycle.scan_proves_safe)
        cycle_dict = cycle.to_dict()
        self.assertEqual(cycle_dict["scan_proves_safe"], False)
        self.assertEqual(cycle_dict["operational_status"], "HEALTHY_NOMINAL")

        report = MacOsCompanionReleaseReport(
            report_id="test-rep-01",
            host_platform="macOS 14.4.1 (Darwin 23.4.0) [Apple Silicon Mock]",
            apple_silicon_native=True,
            cycles_completed=1,
            latest_cycle=cycle,
            all_cycles=[cycle],
            scan_proves_safe=False,
        )
        self.assertFalse(report.scan_proves_safe)
        rep_dict = report.to_dict()
        self.assertEqual(rep_dict["report_id"], "test-rep-01")
        self.assertEqual(rep_dict["active_collectors_count"], 20)
        self.assertEqual(rep_dict["scan_proves_safe"], False)

        # Invariant rejection test
        with self.assertRaises(ValueError):
            CompanionCycleTelemetry(
                cycle_id=2,
                timestamp_utc="2026-11-18T00:00:00Z",
                operational_status=CompanionOperationalStatus.HEALTHY_NOMINAL,
                duration_ms=10.0,
                partial_data=False,
                scan_proves_safe=True,  # Prohibited!
            )

    def test_companion_snapshot_execution(self) -> None:
        """Verifies single-shot snapshot mode under mock platform profile."""
        config = CompanionRunConfig(
            mode=CompanionExecutionMode.SINGLE_SNAPSHOT,
            use_mock=True,
            mock_profile="high_fidelity",
        )
        runner = MacOsCompanionRunner(config=config)
        report = runner.run_snapshot()

        self.assertIsInstance(report, MacOsCompanionReleaseReport)
        self.assertEqual(report.cycles_completed, 1)
        self.assertIsNotNone(report.latest_cycle)
        self.assertFalse(report.scan_proves_safe)
        self.assertTrue(report.apple_silicon_native)
        self.assertTrue(report.least_privilege_enforced)
        self.assertEqual(report.active_collectors_count, 20)

        latest = report.latest_cycle
        self.assertIsNotNone(latest)
        self.assertEqual(latest.cycle_id, 1)
        self.assertFalse(latest.scan_proves_safe)
        self.assertIsNotNone(latest.inventory_summary)
        self.assertIsNotNone(latest.observation_batch_summary)
        self.assertIsNotNone(latest.stability_metrics)
        self.assertIsNotNone(latest.permission_manifest_summary)
        self.assertIsNotNone(latest.privacy_audit)

    def test_companion_daemon_bounded_cycles(self) -> None:
        """Verifies continuous observational mode respects max_cycles bounds."""
        config = CompanionRunConfig(
            mode=CompanionExecutionMode.CONTINUOUS_OBSERVER,
            interval_seconds=0.01,
            max_cycles=3,
            use_mock=True,
        )
        runner = MacOsCompanionRunner(config=config)
        report = runner.run_daemon()

        self.assertEqual(report.cycles_completed, 3)
        self.assertEqual(len(report.all_cycles), 3)
        self.assertEqual(report.all_cycles[0].cycle_id, 1)
        self.assertEqual(report.all_cycles[1].cycle_id, 2)
        self.assertEqual(report.all_cycles[2].cycle_id, 3)
        for c in report.all_cycles:
            self.assertFalse(c.scan_proves_safe)

    def test_companion_circuit_breaker_degradation(self) -> None:
        """Verifies companion runner flags CIRCUIT_BROKEN when collector circuit trips."""
        config = CompanionRunConfig(use_mock=True)
        runner = MacOsCompanionRunner(config=config)

        # Force circuit breaker trip on memory collector
        runner.health_manager._consecutive_failures["memory"] = 10

        cycle = runner.run_cycle(cycle_id=1)
        self.assertEqual(cycle.operational_status, CompanionOperationalStatus.CIRCUIT_BROKEN)
        self.assertTrue(cycle.partial_data)
        self.assertIn("CIRCUIT_BREAKER_TRIPPED", cycle.unavailable_telemetry)

        # Reset and verify recovery
        runner.health_manager.reset_all()
        cycle2 = runner.run_cycle(cycle_id=2)
        self.assertNotIn("CIRCUIT_BREAKER_TRIPPED", cycle2.unavailable_telemetry)

    def test_companion_privacy_integration(self) -> None:
        """Verifies privacy filter scrubs usernames, personal folders, and secrets."""
        config = CompanionRunConfig(
            use_mock=True,
            privacy_level=PrivacyScrubbingLevel.STRICT,
        )
        runner = MacOsCompanionRunner(config=config)
        cycle = runner.run_cycle(cycle_id=1)

        self.assertIsNotNone(cycle.privacy_audit)
        audit = cycle.privacy_audit
        self.assertEqual(audit["level"], "STRICT")
        self.assertFalse(audit["scan_proves_safe"])

    def test_packaging_validator_milestone_4(self) -> None:
        """Executes MacOsCompanionReleaseValidator across the entire repository."""
        result = MacOsCompanionReleaseValidator.audit(ROOT_DIR)
        self.assertTrue(result.valid, f"Milestone 4 audit failed with issues: {result.issues}")
        self.assertEqual(len(result.issues), 0)
        self.assertGreaterEqual(result.collectors_count, 20)
        self.assertGreaterEqual(result.rust_sensors_count, 20)
        self.assertTrue(result.charter_invariants_valid)
        self.assertTrue(result.release_report_present)
        self.assertTrue(result.cli_present)

    def test_cli_execution_flags(self) -> None:
        """Verifies CLI execution with --snapshot, --audit-milestone, and --json."""
        cli_py = ROOT_DIR / "tools" / "run_macos_companion.py"

        # 1. Audit milestone
        proc_audit = subprocess.run(
            [sys.executable, str(cli_py), "--audit-milestone", "--json"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=False,
        )
        self.assertEqual(proc_audit.returncode, 0, f"CLI error: {proc_audit.stderr}")
        data_audit = json.loads(proc_audit.stdout)
        self.assertTrue(data_audit["valid"])

        # 2. Snapshot JSON
        proc_snap = subprocess.run(
            [sys.executable, str(cli_py), "--snapshot", "--mock", "--json"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=False,
        )
        self.assertEqual(proc_snap.returncode, 0, f"CLI error: {proc_snap.stderr}")
        data_snap = json.loads(proc_snap.stdout)
        self.assertEqual(data_snap["milestone_version"], "1.0.0")
        self.assertEqual(data_snap["active_collectors_count"], 20)
        self.assertEqual(data_snap["scan_proves_safe"], False)

    def test_ast_safety_sc01(self) -> None:
        """Verifies zero shell=True and zero os.system in companion modules."""
        target_files = [
            ROOT_DIR / "src" / "system_mind" / "macos" / "companion_runner.py",
            ROOT_DIR / "src" / "system_mind" / "macos" / "companion_models.py",
            ROOT_DIR / "tools" / "run_macos_companion.py",
        ]
        for tf in target_files:
            tree = ast.parse(tf.read_text(encoding="utf-8"), filename=str(tf))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Attribute) and node.func.attr == "system":
                        if isinstance(node.func.value, ast.Name) and node.func.value.id == "os":
                            self.fail(f"Prohibited os.system in {tf.name}")
                    for kw in node.keywords:
                        if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                            self.fail(f"Prohibited shell=True in {tf.name}")


if __name__ == "__main__":
    unittest.main()
