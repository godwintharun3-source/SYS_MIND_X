"""Automated packaging validator auditing macOS telemetry observation timestamps and confidence architecture."""

from __future__ import annotations

import ast
from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
from typing import List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent

from system_mind.macos.collector_health_manager import CORE_COLLECTORS
from system_mind.macos.observation_engine import MacOsObservationEngine
from system_mind.macos.observation_models import (
    CompanionObservationBatch,
    ConfidenceTier,
    ObservationConfidence,
    ObservedTelemetryEnvelope,
    SourceTimestamp,
    compute_telemetry_digest,
)


@dataclass(frozen=True)
class MacOsObservationsAuditResult:
    """Outcome of auditing macOS observation models, engine, CLI, sensors, and safety invariants."""

    valid: bool
    issues: tuple[str, ...]
    models_valid: bool
    engine_valid: bool
    cli_valid: bool
    sensors_valid: bool
    safety_valid: bool


class MacOsObservationsValidator:
    """Programmatic validator verifying observation source timestamps, confidence scoring, and safety."""

    CLI_REL_PATH = Path("tools") / "detect_observations.py"
    SENSOR_RUST_PATH = Path("crates") / "system-mind-sensors" / "src" / "macos_observations.rs"

    REQUIRED_ENVELOPE_FIELDS = [
        "observation_id",
        "collector_id",
        "source_timestamp",
        "observed_at_utc",
        "latency_ms",
        "confidence",
        "payload_sha256",
        "payload",
        "unavailable_telemetry",
        "scan_proves_safe",
        "is_mock",
    ]

    REQUIRED_BATCH_FIELDS = [
        "batch_id",
        "timestamp_utc",
        "total_observations",
        "observations",
        "mean_confidence",
        "lowest_confidence_collector",
        "scan_proves_safe",
        "is_mock",
    ]

    def __init__(self, root_dir: Optional[Path] = None) -> None:
        self.root_dir = root_dir or ROOT_DIR
        self.cli_path = self.root_dir / self.CLI_REL_PATH

    def audit(self) -> MacOsObservationsAuditResult:
        """Execute comprehensive audit across observation models, engine, CLI, sensors, and safety."""
        issues: List[str] = []

        models_valid = self._audit_models(issues)
        engine_valid = self._audit_engine(issues)
        cli_valid = self._audit_cli(issues)
        sensors_valid = self._audit_sensors(issues)
        safety_valid = self._audit_safety_invariants(issues)

        valid = (
            models_valid
            and engine_valid
            and cli_valid
            and sensors_valid
            and safety_valid
            and len(issues) == 0
        )

        return MacOsObservationsAuditResult(
            valid=valid,
            issues=tuple(issues),
            models_valid=models_valid,
            engine_valid=engine_valid,
            cli_valid=cli_valid,
            sensors_valid=sensors_valid,
            safety_valid=safety_valid,
        )

    def audit_all(self) -> MacOsObservationsAuditResult:
        """Alias for audit()."""
        return self.audit()

    def _audit_models(self, issues: List[str]) -> bool:
        """Audit ConfidenceTier, SourceTimestamp, and ObservedTelemetryEnvelope models."""
        valid = True

        if ConfidenceTier.KERNEL_AUTHORITATIVE.value != "KERNEL_AUTHORITATIVE":
            issues.append("ConfidenceTier.KERNEL_AUTHORITATIVE value mismatch")
            valid = False
        if ConfidenceTier.ESTIMATED_MOCK.value != "ESTIMATED_MOCK":
            issues.append("ConfidenceTier.ESTIMATED_MOCK value mismatch")
            valid = False

        ts = SourceTimestamp(
            utc_iso="2026-11-17T12:00:00Z",
            epoch_ms=1794916800000,
            monotonic_ns=42000000,
            clock_source="mach_continuous_time",
        )
        conf = ObservationConfidence(
            score=0.98,
            tier=ConfidenceTier.KERNEL_AUTHORITATIVE,
            rationale="Syscall",
            penalty_factors=[],
        )
        env = ObservedTelemetryEnvelope(
            observation_id="obs-cpu-test",
            collector_id="cpu",
            source_timestamp=ts,
            observed_at_utc="2026-11-17T12:00:00Z",
            latency_ms=8.5,
            confidence=conf,
            payload_sha256="test-hash",
            payload={"cores": 8},
            scan_proves_safe=False,
            is_mock=False,
        )
        env_dict = env.to_dict()
        for f in self.REQUIRED_ENVELOPE_FIELDS:
            if f not in env_dict:
                issues.append(f"ObservedTelemetryEnvelope missing required field: {f}")
                valid = False

        engine = MacOsObservationEngine()
        batch = engine.collect_batch(use_mock=True, profile="high_fidelity")
        batch_dict = batch.to_dict()
        for f in self.REQUIRED_BATCH_FIELDS:
            if f not in batch_dict:
                issues.append(f"CompanionObservationBatch missing required field: {f}")
                valid = False

        if batch.scan_proves_safe is not False:
            issues.append("Mandatory charter invariant 'Scan != Safe' violated in CompanionObservationBatch")
            valid = False

        return valid

    def _audit_engine(self, issues: List[str]) -> bool:
        """Audit MacOsObservationEngine confidence calculations and mock batch profiles."""
        valid = True
        engine = MacOsObservationEngine()

        # Test confidence penalty calculation
        conf_mock = engine.calculate_confidence("cpu", {"metric": 1}, is_mock=True)
        if conf_mock.tier != ConfidenceTier.ESTIMATED_MOCK or conf_mock.score > 0.40:
            issues.append("Mock execution did not yield ESTIMATED_MOCK tier or low score")
            valid = False

        # Test degraded profile
        degraded = engine.collect_batch(use_mock=True, profile="degraded")
        if degraded.observations["battery"].confidence.tier != ConfidenceTier.HEURISTIC_PARSED:
            issues.append("Degraded battery did not reflect hardware absence penalty")
            valid = False

        # Test mock_simulation profile
        sim = engine.collect_batch(use_mock=True, profile="mock_simulation")
        if not sim.is_mock or sim.mean_confidence > 0.40:
            issues.append("Mock simulation batch did not flag is_mock=True or low confidence")
            valid = False

        return valid

    def _audit_cli(self, issues: List[str]) -> bool:
        """Verify developer CLI tool exists, is executable, and runs mock profiles."""
        if not self.cli_path.exists():
            issues.append(f"CLI tool not found at {self.cli_path}")
            return False

        if not self.cli_path.stat().st_mode & 0o111:
            issues.append(f"CLI tool at {self.cli_path} is not executable")
            return False

        try:
            res = subprocess.run(
                [sys.executable, str(self.cli_path), "--mock", "--profile", "degraded", "--json"],
                capture_output=True,
                text=True,
                timeout=5.0,
                check=False,
            )
            if res.returncode != 0:
                issues.append(f"CLI --mock --profile degraded failed: {res.stderr}")
                return False
            data = json.loads(res.stdout)
            if data.get("total_observations") != 16 or "mean_confidence" not in data:
                issues.append("CLI output payload validation failed")
                return False
        except Exception as e:
            issues.append(f"CLI execution error: {e}")
            return False

        return True

    def _audit_sensors(self, issues: List[str]) -> bool:
        """Audit native Rust sensor collector implementation."""
        sensor_path = self.root_dir / self.SENSOR_RUST_PATH
        if not sensor_path.exists():
            issues.append(f"Rust sensor collector missing at: {sensor_path}")
            return False

        content = sensor_path.read_text(encoding="utf-8")
        if "CompanionObservationBatchSnapshot" not in content:
            issues.append("Rust sensor collector missing CompanionObservationBatchSnapshot")
            return False
        if "scan_proves_safe" not in content:
            issues.append("Rust sensor collector missing scan_proves_safe")
            return False
        if "ConfidenceTierSnapshot" not in content:
            issues.append("Rust sensor collector missing ConfidenceTierSnapshot")
            return False

        return True

    def _audit_safety_invariants(self, issues: List[str]) -> bool:
        """Audit safety invariants SC-01 (Zero Ambient Shell) across observation code."""
        targets = [
            self.root_dir / "src" / "system_mind" / "macos" / "observation_engine.py",
            self.root_dir / "src" / "system_mind" / "macos" / "observation_models.py",
            self.cli_path,
        ]

        valid = True
        for target in targets:
            if not target.exists():
                continue
            content = target.read_text(encoding="utf-8")
            try:
                tree = ast.parse(content, filename=str(target))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call):
                        if (
                            isinstance(node.func, ast.Attribute)
                            and isinstance(node.func.value, ast.Name)
                            and node.func.value.id == "os"
                            and node.func.attr == "system"
                        ):
                            issues.append(f"{target.name} uses prohibited os.system")
                            valid = False
                        for kw in node.keywords:
                            if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                                issues.append(f"{target.name} invokes subprocess with shell=True")
                                valid = False
            except SyntaxError as e:
                issues.append(f"{target.name} syntax error: {e}")
                valid = False

        return valid
