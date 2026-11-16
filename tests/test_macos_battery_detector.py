"""Comprehensive unit, contract, and integration tests for macOS battery state and health telemetry."""

from __future__ import annotations

import json
from pathlib import Path
import platform
import subprocess
import sys
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent

from system_mind.macos.battery_detector import MacBatteryDetector
from system_mind.macos.battery_models import (
    BatteryChargingState,
    BatteryHealthCondition,
    MacBatteryHealthInfo,
    MacBatteryTelemetryReport,
    PowerSource,
)
from system_mind.packaging.macos_battery import (
    MacOsBatteryAuditResult,
    MacOsBatteryValidator,
)
from system_mind.platform.adapter import MockPlatformProfileFactory


def test_macos_battery_detector_mock_mode():
    """Verify battery detection using MockPlatformAdapter generates consistent battery telemetry."""
    detector = MacBatteryDetector()
    mock = MockPlatformProfileFactory.create_macos_apple_silicon_mock()
    report = detector.detect(use_mock=True, mock_adapter=mock)

    assert isinstance(report, MacBatteryTelemetryReport)
    assert report.collection_method == "MOCK_PLATFORM_ADAPTER"
    assert report.is_battery_present is True
    assert report.current_power_source == PowerSource.AC_POWER
    assert report.state_of_charge_percent == 100
    assert report.charging_state == BatteryChargingState.CHARGED
    assert report.is_fully_charged is True
    assert report.is_ac_connected is True
    assert report.is_below_warning_level is False

    assert report.health is not None
    health = report.health
    assert isinstance(health, MacBatteryHealthInfo)
    assert health.cycle_count == 182
    assert health.condition == BatteryHealthCondition.NORMAL
    assert health.maximum_capacity_percent == 95
    assert health.anonymized_serial_hash is not None
    assert health.anonymized_serial_hash.startswith("sha256:")
    assert len(health.anonymized_serial_hash) == 23  # "sha256:" + 16 chars


def test_macos_battery_detector_live_on_darwin():
    """Verify live detection executes safely and gathers valid facts on native macOS Darwin host."""
    if platform.system() != "Darwin":
        pytest.skip("Test requires native macOS Darwin host")

    detector = MacBatteryDetector()
    report = detector.detect()

    assert isinstance(report, MacBatteryTelemetryReport)
    assert report.collection_method.startswith("NATIVE_DARWIN")
    assert isinstance(report.is_battery_present, bool)
    assert isinstance(report.current_power_source, PowerSource)
    assert isinstance(report.is_ac_connected, bool)

    if report.is_battery_present:
        assert report.state_of_charge_percent is not None
        assert 0 <= report.state_of_charge_percent <= 100
        assert isinstance(report.charging_state, BatteryChargingState)
        assert isinstance(report.is_charging, bool)
        assert isinstance(report.is_fully_charged, bool)
        if report.health is not None:
            assert isinstance(report.health.condition, BatteryHealthCondition)
            if report.health.cycle_count is not None:
                assert report.health.cycle_count >= 0
            if report.health.maximum_capacity_percent is not None:
                assert 0 <= report.health.maximum_capacity_percent <= 100


def test_battery_serial_privacy_anonymization():
    """Verify raw battery serial number is strictly hashed and never exposed in plaintext (INV-BAT-02)."""
    detector = MacBatteryDetector()
    raw_serial = "D86214300D4GD54AY"

    hashed_serial = detector.anonymize_serial(raw_serial)
    assert hashed_serial is not None
    assert raw_serial not in hashed_serial
    assert hashed_serial.startswith("sha256:")
    assert len(hashed_serial) == 23

    # Determinism with same salt
    assert detector.anonymize_serial(raw_serial) == hashed_serial

    # Different salt produces different digest
    detector_custom = MacBatteryDetector(salt="custom-salt:")
    assert detector_custom.anonymize_serial(raw_serial) != hashed_serial

    # Empty serial returns None
    assert detector.anonymize_serial(None) is None
    assert detector.anonymize_serial("   ") is None


def test_battery_condition_parsing():
    """Verify categorical condition mapping from Darwin pmset / system_profiler strings."""
    detector = MacBatteryDetector()

    assert detector.parse_condition_string("Normal") == BatteryHealthCondition.NORMAL
    assert detector.parse_condition_string("Good") == BatteryHealthCondition.NORMAL
    assert detector.parse_condition_string("Replace Soon") == BatteryHealthCondition.REPLACE_SOON
    assert detector.parse_condition_string("Fair") == BatteryHealthCondition.REPLACE_SOON
    assert detector.parse_condition_string("Replace Now") == BatteryHealthCondition.REPLACE_NOW
    assert detector.parse_condition_string("Poor") == BatteryHealthCondition.REPLACE_NOW
    assert detector.parse_condition_string("Service Battery") == BatteryHealthCondition.SERVICE_BATTERY
    assert detector.parse_condition_string("Check Battery") == BatteryHealthCondition.SERVICE_BATTERY
    assert detector.parse_condition_string("UnknownState") == BatteryHealthCondition.UNKNOWN
    assert detector.parse_condition_string(None) == BatteryHealthCondition.UNKNOWN


def test_macos_battery_validator_clean_audit():
    """Verify programmatic packaging validator audits battery components with zero issues."""
    audit = MacOsBatteryValidator.audit()

    assert audit.valid is True, f"Validator found issues: {audit.issues}"
    assert audit.models_valid is True
    assert audit.detector_valid is True
    assert audit.cli_valid is True
    assert audit.privacy_valid is True
    assert len(audit.issues) == 0


def test_detect_battery_cli_execution():
    """Verify developer CLI tool executes cleanly in mock and JSON modes."""
    cli_path = ROOT_DIR / "tools" / "detect_battery.py"
    assert cli_path.exists()

    # 1. Test mock with JSON
    proc = subprocess.run(
        [sys.executable, str(cli_path), "--mock", "--json"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=False,
        timeout=5,
    )
    assert proc.returncode == 0, f"CLI mock failed: {proc.stderr}"
    data = json.loads(proc.stdout)
    assert data["collection_method"] == "MOCK_PLATFORM_ADAPTER"
    assert data["is_battery_present"] is True
    assert data["current_power_source"] == "AC_POWER"
    assert data["state_of_charge_percent"] == 100
    assert data["health"]["condition"] == "NORMAL"
    assert data["health"]["maximum_capacity_percent"] == 95

    # 2. Test mock human-readable output
    proc_human = subprocess.run(
        [sys.executable, str(cli_path), "--mock"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=False,
        timeout=5,
    )
    assert proc_human.returncode == 0
    assert "SYSTEM MIND X — macOS Battery State & Health Telemetry" in proc_human.stdout
    assert "MOCK_PLATFORM_ADAPTER" in proc_human.stdout
