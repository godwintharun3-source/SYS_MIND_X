"""Unit, contract, and safety test suite for macOS telemetry collector health and timeouts."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import subprocess
import sys
import time
import pytest

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
from system_mind.packaging.macos_collector_health import (
    MacOsCollectorHealthAuditResult,
    MacOsCollectorHealthValidator,
)

ROOT_DIR = Path(__file__).resolve().parent.parent
CLI_PATH = ROOT_DIR / "tools" / "detect_collector_health.py"


def test_collector_health_models_fidelity() -> None:
    """Verify data model construction, enum mappings, dictionary conversion, and Scan!=Safe invariant."""
    assert CollectorStatus.HEALTHY.value == "HEALTHY"
    assert CollectorStatus.DEGRADED.value == "DEGRADED"
    assert CollectorStatus.TIMED_OUT.value == "TIMED_OUT"
    assert CollectorStatus.FAILED.value == "FAILED"
    assert CollectorStatus.UNSUPPORTED.value == "UNSUPPORTED"
    assert CollectorStatus.CIRCUIT_BROKEN.value == "CIRCUIT_BROKEN"

    assert PartialDataReason.HARDWARE_ABSENT.value == "HARDWARE_ABSENT"
    assert PartialDataReason.PERMISSION_DENIED.value == "PERMISSION_DENIED"
    assert PartialDataReason.TIMEOUT.value == "TIMEOUT"
    assert PartialDataReason.COMMAND_ERROR.value == "COMMAND_ERROR"
    assert PartialDataReason.PLATFORM_UNSUPPORTED.value == "PLATFORM_UNSUPPORTED"

    record = CollectorHealthRecord(
        collector_id="cpu",
        status=CollectorStatus.HEALTHY,
        latency_ms=12.4,
        timeout_seconds=2.0,
        consecutive_failures=0,
        last_success_timestamp="2026-11-17T11:00:00Z",
        last_error=None,
        partial_data=False,
    )
    assert record.is_operational is True

    rec_dict = record.to_dict()
    assert rec_dict["collector_id"] == "cpu"
    assert rec_dict["status"] == "HEALTHY"
    assert rec_dict["latency_ms"] == 12.4
    assert rec_dict["is_operational"] is True

    degraded_record = CollectorHealthRecord(
        collector_id="battery",
        status=CollectorStatus.DEGRADED,
        latency_ms=8.0,
        timeout_seconds=2.0,
        consecutive_failures=0,
        partial_data=True,
        partial_reasons=[PartialDataReason.HARDWARE_ABSENT],
        unavailable_fields=["no_battery"],
    )
    assert degraded_record.is_operational is True

    timed_out_record = CollectorHealthRecord(
        collector_id="fsevents",
        status=CollectorStatus.TIMED_OUT,
        latency_ms=2000.0,
        timeout_seconds=2.0,
        consecutive_failures=1,
        partial_data=True,
        partial_reasons=[PartialDataReason.TIMEOUT],
    )
    assert timed_out_record.is_operational is False

    report = CompanionHealthReport(
        timestamp="2026-11-17T11:00:00Z",
        host_platform="Darwin",
        total_collectors=2,
        healthy_count=1,
        degraded_count=1,
        failed_count=0,
        timed_out_count=0,
        unsupported_count=0,
        overall_status=CollectorStatus.DEGRADED,
        collectors={"cpu": record, "battery": degraded_record},
        partial_data_present=True,
        scan_proves_safe=False,
        is_mock=True,
    )

    # Invariant assertions
    assert report.scan_proves_safe is False
    rep_dict = report.to_dict()
    assert rep_dict["overall_status"] == "DEGRADED"
    assert rep_dict["scan_proves_safe"] is False

    json_str = report.to_json()
    parsed = json.loads(json_str)
    assert parsed["overall_status"] == "DEGRADED"
    assert parsed["scan_proves_safe"] is False


def test_collector_timeout_execution() -> None:
    """Verify timeout containment and fallback invocation when execution budget is exceeded."""
    manager = CollectorHealthManager(default_timeout_seconds=0.1)

    # Fast collector succeeds
    res_fast = manager.execute_collector("fast", lambda: "quick_result", timeout_seconds=0.5)
    assert res_fast.data == "quick_result"
    assert res_fast.health.status == CollectorStatus.HEALTHY
    assert res_fast.health.consecutive_failures == 0

    # Slow collector times out
    def slow_fn() -> str:
        time.sleep(0.3)
        return "too_slow"

    res_slow = manager.execute_collector(
        "slow",
        slow_fn,
        timeout_seconds=0.05,
        fallback_fn=lambda: "fallback_val",
    )
    assert res_slow.data == "fallback_val"
    assert res_slow.health.status == CollectorStatus.TIMED_OUT
    assert res_slow.health.partial_data is True
    assert PartialDataReason.TIMEOUT in res_slow.health.partial_reasons
    assert res_slow.health.consecutive_failures == 1


def test_circuit_breaker_transition_and_reset() -> None:
    """Verify circuit breaker trips after consecutive failures and resets cleanly."""
    manager = CollectorHealthManager(default_timeout_seconds=0.05, max_consecutive_failures=2)

    def failing_fn() -> None:
        raise RuntimeError("Sensor hardware bus error")

    # Failure 1
    res1 = manager.execute_collector("flake", failing_fn)
    assert res1.health.status == CollectorStatus.FAILED
    assert res1.health.consecutive_failures == 1

    # Failure 2 (reaches max_consecutive_failures=2)
    res2 = manager.execute_collector("flake", failing_fn)
    assert res2.health.status == CollectorStatus.FAILED
    assert res2.health.consecutive_failures == 2

    # Query 3: Should immediately return CIRCUIT_BROKEN without running failing_fn
    called = False

    def monitored_fn() -> str:
        nonlocal called
        called = True
        return "ran"

    res3 = manager.execute_collector("flake", monitored_fn, fallback_fn=lambda: "cached")
    assert called is False
    assert res3.data == "cached"
    assert res3.health.status == CollectorStatus.CIRCUIT_BROKEN
    assert res3.health.consecutive_failures == 2

    # Reset collector
    manager.reset_collector("flake")
    assert manager.get_consecutive_failures("flake") == 0

    # Query 4: Now executes normally
    res4 = manager.execute_collector("flake", monitored_fn)
    assert called is True
    assert res4.data == "ran"
    assert res4.health.status == CollectorStatus.HEALTHY


def test_partial_data_detection_and_reason_categorization() -> None:
    """Verify that partial data and unavailable telemetry are categorized into structured reasons."""
    manager = CollectorHealthManager()

    # Hardware absent
    class MockBatteryData:
        unavailable_telemetry = ["no_battery_hardware_present"]
        has_battery = False

    res_batt = manager.execute_collector("battery", lambda: MockBatteryData())
    assert res_batt.health.status == CollectorStatus.DEGRADED
    assert res_batt.health.partial_data is True
    assert PartialDataReason.HARDWARE_ABSENT in res_batt.health.partial_reasons

    # Permission denied
    class MockEsData:
        unavailable_telemetry = ["missing_endpoint_security_entitlement"]

    res_es = manager.execute_collector("endpoint_security", lambda: MockEsData())
    assert res_es.health.status == CollectorStatus.DEGRADED
    assert res_es.health.partial_data is True
    assert PartialDataReason.PERMISSION_DENIED in res_es.health.partial_reasons

    # Platform unsupported
    class MockLinuxData:
        unavailable_telemetry = ["unsupported_platform_linux"]

    res_lx = manager.execute_collector("platform", lambda: MockLinuxData())
    assert res_lx.health.status == CollectorStatus.DEGRADED
    assert PartialDataReason.PLATFORM_UNSUPPORTED in res_lx.health.partial_reasons


def test_mock_profiles_orchestration() -> None:
    """Verify mock profiles: healthy, degraded, timeout, unsupported."""
    manager = CollectorHealthManager()

    # Healthy
    healthy = manager.collect_all_telemetry(use_mock=True, profile="healthy")
    assert healthy.overall_status == CollectorStatus.HEALTHY
    assert healthy.total_collectors == len(CORE_COLLECTORS)
    assert healthy.healthy_count == len(CORE_COLLECTORS)
    assert healthy.partial_data_present is False
    assert healthy.scan_proves_safe is False
    assert healthy.is_mock is True

    # Degraded
    degraded = manager.collect_all_telemetry(use_mock=True, profile="degraded")
    assert degraded.overall_status == CollectorStatus.DEGRADED
    assert degraded.degraded_count == 2
    assert degraded.partial_data_present is True
    assert degraded.collectors["battery"].status == CollectorStatus.DEGRADED
    assert degraded.collectors["endpoint_security"].status == CollectorStatus.DEGRADED

    # Timeout
    timeout = manager.collect_all_telemetry(use_mock=True, profile="timeout")
    assert timeout.overall_status == CollectorStatus.DEGRADED
    assert timeout.timed_out_count == 2
    assert timeout.collectors["fsevents"].status == CollectorStatus.TIMED_OUT
    assert timeout.collectors["user_agent"].status == CollectorStatus.TIMED_OUT

    # Unsupported
    unsupported = manager.collect_all_telemetry(use_mock=True, profile="unsupported")
    assert unsupported.overall_status == CollectorStatus.UNSUPPORTED
    assert unsupported.unsupported_count == len(CORE_COLLECTORS)
    assert unsupported.healthy_count == 0


def test_cli_execution_and_flags() -> None:
    """Verify developer CLI tool supports --mock, --profile, --json, and --collector."""
    # Test --mock --json
    cmd_json = [sys.executable, str(CLI_PATH), "--mock", "--profile", "degraded", "--json"]
    proc = subprocess.run(cmd_json, capture_output=True, text=True, check=False)
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    assert data["overall_status"] == "DEGRADED"
    assert data["partial_data_present"] is True
    assert data["scan_proves_safe"] is False

    # Test --mock --collector battery
    cmd_single = [sys.executable, str(CLI_PATH), "--mock", "--profile", "degraded", "--collector", "battery"]
    proc = subprocess.run(cmd_single, capture_output=True, text=True, check=False)
    assert proc.returncode == 0
    assert "Collector ID:         battery" in proc.stdout
    assert "Status:               DEGRADED" in proc.stdout
    assert "HARDWARE_ABSENT" in proc.stdout

    # Test invalid collector
    cmd_invalid = [sys.executable, str(CLI_PATH), "--mock", "--collector", "nonexistent_sensor"]
    proc = subprocess.run(cmd_invalid, capture_output=True, text=True, check=False)
    assert proc.returncode == 1
    assert "Unknown collector" in proc.stderr

    # Test formatted table output
    cmd_table = [sys.executable, str(CLI_PATH), "--mock", "--profile", "healthy"]
    proc = subprocess.run(cmd_table, capture_output=True, text=True, check=False)
    assert proc.returncode == 0
    assert "Collector Health & Partial-Data Report" in proc.stdout
    assert "Nominal / Full Parity" in proc.stdout


def test_packaging_validator() -> None:
    """Verify MacOsCollectorHealthValidator reports valid=True and zero issues."""
    validator = MacOsCollectorHealthValidator()
    result = validator.audit()

    assert isinstance(result, MacOsCollectorHealthAuditResult)
    assert result.valid is True
    assert len(result.issues) == 0
    assert result.models_valid is True
    assert result.manager_valid is True
    assert result.cli_valid is True
    assert result.sensors_valid is True
    assert result.safety_valid is True


def test_zero_ambient_shell_authority_and_ast_safety() -> None:
    """Verify SC-01 zero ambient shell authority across collector health files."""
    targets = [
        ROOT_DIR / "src" / "system_mind" / "macos" / "collector_health_manager.py",
        ROOT_DIR / "src" / "system_mind" / "macos" / "collector_health_models.py",
        CLI_PATH,
    ]

    for target in targets:
        content = target.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(target))

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # Verify no os.system
                if (
                    isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "os"
                    and node.func.attr == "system"
                ):
                    pytest.fail(f"Banned os.system call found in {target.name} at line {node.lineno}")

                # Verify no shell=True
                for kw in node.keywords:
                    if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                        pytest.fail(f"Forbidden shell=True keyword found in {target.name} at line {node.lineno}")
