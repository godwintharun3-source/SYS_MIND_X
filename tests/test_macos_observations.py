"""Unit, contract, and safety test suite for macOS observation timestamps and confidence scoring."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import subprocess
import sys
import pytest

from system_mind.macos.collector_health_manager import CORE_COLLECTORS
from system_mind.macos.observation_engine import (
    BASE_COLLECTOR_CONFIDENCE,
    MacOsObservationEngine,
)
from system_mind.macos.observation_models import (
    CompanionObservationBatch,
    ConfidenceTier,
    ObservationConfidence,
    ObservedTelemetryEnvelope,
    SourceTimestamp,
    compute_telemetry_digest,
)
from system_mind.packaging.macos_observations import (
    MacOsObservationsAuditResult,
    MacOsObservationsValidator,
)

ROOT_DIR = Path(__file__).resolve().parent.parent
CLI_PATH = ROOT_DIR / "tools" / "detect_observations.py"


def test_observation_models_fidelity() -> None:
    """Verify data model construction, enum mappings, dictionary conversion, and Scan!=Safe invariant."""
    assert ConfidenceTier.KERNEL_AUTHORITATIVE.value == "KERNEL_AUTHORITATIVE"
    assert ConfidenceTier.SUBSYSTEM_VERIFIED.value == "SUBSYSTEM_VERIFIED"
    assert ConfidenceTier.HEURISTIC_PARSED.value == "HEURISTIC_PARSED"
    assert ConfidenceTier.DEGRADED_PARTIAL.value == "DEGRADED_PARTIAL"
    assert ConfidenceTier.ESTIMATED_MOCK.value == "ESTIMATED_MOCK"

    ts = SourceTimestamp(
        utc_iso="2026-11-17T12:00:00Z",
        epoch_ms=1794916800000,
        monotonic_ns=55000000,
        clock_source="mach_continuous_time",
    )
    ts_dict = ts.to_dict()
    assert ts_dict["utc_iso"] == "2026-11-17T12:00:00Z"
    assert ts_dict["epoch_ms"] == 1794916800000
    assert ts_dict["clock_source"] == "mach_continuous_time"

    conf = ObservationConfidence(
        score=0.98,
        tier=ConfidenceTier.KERNEL_AUTHORITATIVE,
        rationale="Darwin sysctl",
        penalty_factors=[],
    )
    conf_dict = conf.to_dict()
    assert conf_dict["score"] == 0.98
    assert conf_dict["tier"] == "KERNEL_AUTHORITATIVE"
    assert conf_dict["rationale"] == "Darwin sysctl"

    env = ObservedTelemetryEnvelope(
        observation_id="obs-cpu-123",
        collector_id="cpu",
        source_timestamp=ts,
        observed_at_utc="2026-11-17T12:00:00Z",
        latency_ms=10.5,
        confidence=conf,
        payload_sha256="test-sha256-digest",
        payload={"cores": 8, "frequency_mhz": 3200},
        unavailable_telemetry=[],
        scan_proves_safe=False,
        is_mock=False,
    )

    # Invariant assertions
    assert env.scan_proves_safe is False
    env_dict = env.to_dict()
    assert env_dict["collector_id"] == "cpu"
    assert env_dict["scan_proves_safe"] is False
    assert env_dict["payload_sha256"] == "test-sha256-digest"

    json_str = env.to_json()
    parsed = json.loads(json_str)
    assert parsed["collector_id"] == "cpu"
    assert parsed["scan_proves_safe"] is False

    batch = CompanionObservationBatch(
        batch_id="batch-001",
        timestamp_utc="2026-11-17T12:00:00Z",
        total_observations=1,
        observations={"cpu": env},
        mean_confidence=0.98,
        lowest_confidence_collector="cpu",
        scan_proves_safe=False,
        is_mock=False,
    )
    assert batch.scan_proves_safe is False
    batch_dict = batch.to_dict()
    assert batch_dict["batch_id"] == "batch-001"
    assert batch_dict["scan_proves_safe"] is False


def test_confidence_scoring_and_penalty_deductions() -> None:
    """Verify base scores and deterministic penalty deductions across hardware and permission conditions."""
    engine = MacOsObservationEngine()

    # 1. Authoritative kernel read (no penalties)
    conf_cpu = engine.calculate_confidence("cpu", {"metric": 100}, is_mock=False)
    assert conf_cpu.score == 0.98
    assert conf_cpu.tier == ConfidenceTier.KERNEL_AUTHORITATIVE
    assert len(conf_cpu.penalty_factors) == 0

    # 2. Hardware absent penalty (-0.20) on desktop battery
    class MockDesktopBattery:
        has_battery = False
        unavailable_telemetry = ["no_battery_hardware_desktop"]

    conf_batt = engine.calculate_confidence("battery", MockDesktopBattery(), is_mock=False)
    assert conf_batt.score == 0.75  # 0.95 base - 0.20
    assert conf_batt.tier == ConfidenceTier.HEURISTIC_PARSED
    assert "hardware_absent_desktop" in conf_batt.penalty_factors

    # 3. Missing entitlement penalty (-0.35) on Endpoint Security
    class MockRestrictedEs:
        unavailable_telemetry = ["endpoint_security_missing_entitlement"]

    conf_es = engine.calculate_confidence("endpoint_security", MockRestrictedEs(), is_mock=False)
    assert conf_es.score == 0.50  # 0.85 base - 0.35
    assert conf_es.tier == ConfidenceTier.DEGRADED_PARTIAL
    assert "missing_permission_or_entitlement" in conf_es.penalty_factors

    # 4. Synthetic mock penalty (-0.60)
    conf_mock = engine.calculate_confidence("storage", {"metric": 100}, is_mock=True)
    assert conf_mock.score == 0.32  # 0.92 base - 0.60
    assert conf_mock.tier == ConfidenceTier.ESTIMATED_MOCK
    assert "synthetic_mock_fixture" in conf_mock.penalty_factors


def test_source_timestamp_fidelity_and_clock_sources() -> None:
    """Verify clock source identification and timestamp generation."""
    engine = MacOsObservationEngine()

    # Live timestamp
    ts_live = engine.capture_source_timestamp(is_mock=False)
    assert ts_live.epoch_ms > 0
    assert "T" in ts_live.utc_iso
    assert ts_live.clock_source in ("mach_continuous_time", "system_clock_utc")

    # Mock timestamp
    ts_mock = engine.capture_source_timestamp(is_mock=True)
    assert ts_mock.clock_source == "mock_clock"


def test_payload_hashing_determinism_and_sensitivity() -> None:
    """Verify deterministic SHA-256 payload digests and sensitivity to payload mutations."""
    payload_a = {"service": "launchd", "active": True, "count": 42}
    payload_b = {"count": 42, "service": "launchd", "active": True}
    payload_c = {"service": "launchd", "active": False, "count": 42}

    digest_a = compute_telemetry_digest(payload_a)
    digest_b = compute_telemetry_digest(payload_b)
    digest_c = compute_telemetry_digest(payload_c)

    # Key order invariance (canonical JSON)
    assert digest_a == digest_b
    assert len(digest_a) == 64

    # Sensitivity to attribute mutations
    assert digest_a != digest_c


def test_mock_batch_profiles() -> None:
    """Verify high_fidelity, degraded, mock_simulation, and unsupported mock batch profiles."""
    engine = MacOsObservationEngine()

    # High fidelity
    high = engine.collect_batch(use_mock=True, profile="high_fidelity")
    assert high.total_observations == len(CORE_COLLECTORS)
    assert high.mean_confidence >= 0.90
    assert high.scan_proves_safe is False
    assert high.is_mock is False

    # Degraded
    degraded = engine.collect_batch(use_mock=True, profile="degraded")
    assert degraded.total_observations == len(CORE_COLLECTORS)
    assert degraded.observations["battery"].confidence.tier == ConfidenceTier.HEURISTIC_PARSED
    assert degraded.observations["endpoint_security"].confidence.tier == ConfidenceTier.HEURISTIC_PARSED

    # Mock simulation
    sim = engine.collect_batch(use_mock=True, profile="mock_simulation")
    assert sim.is_mock is True
    assert sim.mean_confidence <= 0.40
    assert sim.observations["cpu"].confidence.tier == ConfidenceTier.ESTIMATED_MOCK

    # Unsupported
    unsupported = engine.collect_batch(use_mock=True, profile="unsupported")
    assert unsupported.is_mock is True
    assert unsupported.mean_confidence <= 0.20


def test_cli_execution_and_flags() -> None:
    """Verify developer CLI tool supports --mock, --profile, --json, and --collector."""
    # Test --mock --json
    cmd_json = [sys.executable, str(CLI_PATH), "--mock", "--profile", "high_fidelity", "--json"]
    proc = subprocess.run(cmd_json, capture_output=True, text=True, check=False)
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    assert data["total_observations"] == 16
    assert data["mean_confidence"] >= 0.90
    assert data["scan_proves_safe"] is False

    # Test --mock --collector cpu
    cmd_single = [sys.executable, str(CLI_PATH), "--mock", "--profile", "high_fidelity", "--collector", "cpu"]
    proc = subprocess.run(cmd_single, capture_output=True, text=True, check=False)
    assert proc.returncode == 0
    assert "Collector ID:          cpu" in proc.stdout
    assert "KERNEL_AUTHORITATIVE" in proc.stdout
    assert "Scan Proves Safe:      False" in proc.stdout

    # Test invalid collector
    cmd_invalid = [sys.executable, str(CLI_PATH), "--mock", "--collector", "nonexistent"]
    proc = subprocess.run(cmd_invalid, capture_output=True, text=True, check=False)
    assert proc.returncode == 1
    assert "Unknown collector" in proc.stderr

    # Test formatted table output
    cmd_table = [sys.executable, str(CLI_PATH), "--mock", "--profile", "degraded"]
    proc = subprocess.run(cmd_table, capture_output=True, text=True, check=False)
    assert proc.returncode == 0
    assert "Observation Provenance & Confidence Report" in proc.stdout
    assert "mach_continuous_time" in proc.stdout


def test_packaging_validator() -> None:
    """Verify MacOsObservationsValidator reports valid=True and zero issues."""
    validator = MacOsObservationsValidator()
    result = validator.audit()

    assert isinstance(result, MacOsObservationsAuditResult)
    assert result.valid is True
    assert len(result.issues) == 0
    assert result.models_valid is True
    assert result.engine_valid is True
    assert result.cli_valid is True
    assert result.sensors_valid is True
    assert result.safety_valid is True


def test_zero_ambient_shell_authority_and_ast_safety() -> None:
    """Verify SC-01 zero ambient shell authority across observation engine and models."""
    targets = [
        ROOT_DIR / "src" / "system_mind" / "macos" / "observation_engine.py",
        ROOT_DIR / "src" / "system_mind" / "macos" / "observation_models.py",
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
