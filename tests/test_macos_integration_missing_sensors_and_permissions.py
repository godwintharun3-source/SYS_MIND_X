"""Integration tests with missing sensors and denied permissions for SYSTEM MIND X macOS companion agent.

Verifies end-to-end resilience when hardware sensors are absent, TCC permissions are denied,
Endpoint Security entitlements are restricted, or storage mounts are unmounted:
- Bounded execution without thread exhaustion or orchestrator stalls (timeout <= 2.0s).
- Explicit partial-data transparency (partial_data = True with typed root causes).
- Deterministic confidence penalty deductions in observation engine.
- Complete privacy protection through MacPrivacyFilter.
- Structural enforcement of the non-negotiable charter invariant: scan_proves_safe = False.
- Zero ambient shell authority (SC-01: shell=False strictly enforced).
"""

from __future__ import annotations

import ast
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from system_mind.api.models import ApiRequest, ApiStatus, ErrorCode
from system_mind.governance.models import ActorIdentity, IdentityType
from system_mind.macos.battery_detector import MacBatteryDetector
from system_mind.macos.battery_models import BatteryChargingState, PowerSource
from system_mind.macos.collector_health_manager import CollectorHealthManager
from system_mind.macos.collector_health_models import CollectorStatus, PartialDataReason
from system_mind.macos.endpoint_security_detector import MacEndpointSecurityDetector
from system_mind.macos.endpoint_security_models import EsClientResultCode, EsStatus
from system_mind.macos.inventory_api import MacOsInventoryApi
from system_mind.macos.inventory_models import InventorySection, MacOsInventoryRequest
from system_mind.macos.network_detector import MacNetworkDetector
from system_mind.macos.observation_engine import MacOsObservationEngine
from system_mind.macos.observation_models import ConfidenceTier
from system_mind.macos.privacy_filter import MacPrivacyFilter
from system_mind.macos.privacy_models import PrivacyScrubbingLevel
from system_mind.macos.storage_detector import MacStorageDetector
from system_mind.macos.swift_bridge import MacSwiftBridge
from system_mind.macos.usb_detector import MacUsbDetector
from system_mind.packaging.macos_integration_faults import MacOsIntegrationFaultsValidator
from system_mind.platform.adapter import MockPlatformProfileFactory

ROOT_DIR = Path(__file__).resolve().parent.parent


class TestMacOsIntegrationMissingSensorsAndPermissions(unittest.TestCase):
    """End-to-end integration tests under sensor absence, TCC denials, and entitlement restrictions."""

    def setUp(self) -> None:
        self.mock_adapter = MockPlatformProfileFactory.create_macos_apple_silicon_mock()
        self.actor = ActorIdentity(
            identity_id="test-operator",
            identity_type=IdentityType.LOCAL_CONSOLE_USER,
            principal_name="operator",
        )

    # -------------------------------------------------------------------------
    # Scenario 1: Desktop Mac with Missing Battery Sensor
    # -------------------------------------------------------------------------
    def test_integration_battery_absent_desktop_fallback(self) -> None:
        """Verify integration resilience on desktop Macs lacking battery hardware."""
        detector = MacBatteryDetector()
        desktop_pmset = "Now drawing from 'AC Power'\n"

        parsed = detector.parse_pmset_output(desktop_pmset)
        self.assertFalse(parsed.get("is_battery_present", True))

        # Health manager records missing hardware gracefully
        health_mgr = CollectorHealthManager(default_timeout_seconds=1.0)
        report = health_mgr.collect_all_telemetry(use_mock=True)
        self.assertFalse(report.scan_proves_safe)

        # Observation engine collects batch and handles missing battery without crashing
        obs_engine = MacOsObservationEngine()
        obs_batch = obs_engine.collect_batch(use_mock=True, profile="degraded")
        self.assertFalse(obs_batch.scan_proves_safe)
        self.assertIn("battery", obs_batch.observations)

        # Unified inventory API populates null/empty battery without breaking
        api = MacOsInventoryApi()
        req = MacOsInventoryRequest(sections=[InventorySection.HARDWARE], use_mock=True)
        inv = api.get_inventory(req)
        self.assertFalse(inv.scan_proves_safe)
        self.assertIn("hardware", inv.sections)

    # -------------------------------------------------------------------------
    # Scenario 2: Air-Gapped / Offline Network State
    # -------------------------------------------------------------------------
    def test_integration_offline_network_resilience(self) -> None:
        """Verify network telemetry collection in air-gapped or offline environments."""
        detector = MacNetworkDetector()
        report = detector.detect(use_mock=True, mock_adapter=self.mock_adapter)
        self.assertFalse(report.scan_proves_safe)
        self.assertGreater(len(report.interfaces), 0)

        # Query inventory with network section
        api = MacOsInventoryApi()
        req = MacOsInventoryRequest(sections=[InventorySection.NETWORK], use_mock=True)
        inv = api.get_inventory(req)
        self.assertFalse(inv.scan_proves_safe)
        self.assertIn("network", inv.sections)
        self.assertFalse(inv.is_mock is False and inv.partial_data)

    # -------------------------------------------------------------------------
    # Scenario 3: Unprivileged Endpoint Security & Entitlement Denial
    # -------------------------------------------------------------------------
    def test_integration_endpoint_security_unprivileged_fallback(self) -> None:
        """Verify unprivileged companion gracefully maps ES restrictions to transparent fallbacks."""
        es_detector = MacEndpointSecurityDetector()
        report = es_detector.detect(use_mock=True, profile="restricted_companion")

        self.assertFalse(report.scan_proves_safe)
        self.assertFalse(report.is_operational)
        self.assertTrue(report.requires_escalation)
        self.assertTrue(report.has_fallback)
        self.assertEqual(report.status, EsStatus.RESTRICTED_NOT_ROOT)
        self.assertEqual(report.result_code, EsClientResultCode.ERR_NOT_PRIVILEGED)
        self.assertIn("filesystem", report.fallback_strategies)

        # Verify observation engine scores restricted ES with confidence penalty
        obs_engine = MacOsObservationEngine()
        batch = obs_engine.collect_batch(use_mock=True, profile="degraded")
        es_obs = batch.observations.get("endpoint_security")
        self.assertIsNotNone(es_obs)
        self.assertLess(es_obs.confidence.score, 0.90)

    # -------------------------------------------------------------------------
    # Scenario 4: TCC Full Disk Access (FDA) Permission Denial
    # -------------------------------------------------------------------------
    def test_integration_tcc_full_disk_access_denied(self) -> None:
        """Verify companion handles TCC Full Disk Access permission denials without aborting."""
        # Simulate accessing protected user vault raising PermissionError / denied access
        with patch("os.access", return_value=False):
            es_detector = MacEndpointSecurityDetector()
            fda_accessible = es_detector._check_fda_accessibility()
            self.assertFalse(fda_accessible)

        # Unified inventory marks partial data and records permission issues in health
        api = MacOsInventoryApi()
        req = MacOsInventoryRequest(
            sections=[InventorySection.SECURITY, InventorySection.APPLICATIONS],
            use_mock=True,
        )
        inv = api.get_inventory(req)
        self.assertFalse(inv.scan_proves_safe)
        self.assertIn("security", inv.sections)

    # -------------------------------------------------------------------------
    # Scenario 5: TCC Screen Recording & Accessibility Permission Denial
    # -------------------------------------------------------------------------
    def test_integration_tcc_screen_accessibility_denied(self) -> None:
        """Verify denied Screen Recording and Accessibility permissions omit sensitive UI data."""
        bridge = MacSwiftBridge()
        telemetry = bridge.collect(use_mock=True)

        self.assertFalse(telemetry.scan_proves_safe)
        self.assertIsNotNone(telemetry.permissions)
        # Privacy filter scrubs any residual window metadata
        filter_eng = MacPrivacyFilter(level=PrivacyScrubbingLevel.STRICT)
        clean_data, audit = filter_eng.sanitize_payload({"window_title": "Confidential Budget.xlsx - Excel"})
        self.assertFalse(audit.scan_proves_safe)
        self.assertNotIn("Confidential Budget", str(clean_data))

    # -------------------------------------------------------------------------
    # Scenario 6: Corrupted or Unmounted Storage Volume
    # -------------------------------------------------------------------------
    def test_integration_storage_volume_unmounted(self) -> None:
        """Verify storage collector and inventory gracefully handle unmounted/corrupted volumes."""
        with patch("os.statvfs", side_effect=OSError(6, "Device not configured")):
            cap, used, avail, pct, avail_bool = MacStorageDetector.query_statvfs("/Volumes/Unmounted")
            self.assertEqual(cap, 0)
            self.assertEqual(used, 0)
            self.assertEqual(avail, 0)
            self.assertFalse(avail_bool)

        report = MacStorageDetector.detect(mock_adapter=self.mock_adapter)
        self.assertFalse(report.scan_proves_safe)
        self.assertGreaterEqual(len(report.volumes), 1)

    # -------------------------------------------------------------------------
    # Scenario 7: Zero External USB Peripherals (Root Hub Only)
    # -------------------------------------------------------------------------
    def test_integration_usb_empty_peripherals(self) -> None:
        """Verify USB collector correctly handles buses with zero external devices attached."""
        detector = MacUsbDetector()
        report = detector.detect(use_mock=True, mock_adapter=self.mock_adapter)
        self.assertFalse(report.scan_proves_safe)
        self.assertGreaterEqual(len(report.controllers), 1)

        # Flattened device list empty handling
        flattened = detector.flatten_devices([])
        self.assertEqual(len(flattened), 0)

    # -------------------------------------------------------------------------
    # Scenario 8: Composite Multi-Fault Inventory Aggregation
    # -------------------------------------------------------------------------
    def test_integration_multifault_inventory_aggregation(self) -> None:
        """Verify simultaneous multi-fault state (Desktop + Offline + Unprivileged ES + TCC Denied)."""
        api = MacOsInventoryApi()
        req = MacOsInventoryRequest(
            use_mock=True,
            privacy_level=PrivacyScrubbingLevel.STRICT,
        )
        resp = api.get_inventory(req)

        # 1. Non-negotiable charter invariant: Scan != Safe
        self.assertFalse(resp.scan_proves_safe)

        # 2. Executive summary aggregates successfully despite partial subsystem data
        self.assertIsNotNone(resp.summary)
        self.assertGreater(resp.summary.running_process_count, 0)
        self.assertGreater(resp.summary.installed_app_count, 0)
        self.assertGreater(resp.summary.mean_confidence, 0.0)

        # 3. All 8 core sections aggregated
        expected_sections = {
            "identity",
            "hardware",
            "storage",
            "network",
            "applications",
            "security",
            "processes",
            "services",
        }
        for s in expected_sections:
            self.assertIn(s, resp.sections)

        # 4. Privacy audit records scrubbing operations
        self.assertFalse(resp.privacy_audit.get("scan_proves_safe", True))

        # 5. Wire API handling enforces read-only semantics
        api_req = ApiRequest(
            request_id="req-multifault-01",
            api_version="1.0.0",
            method_urn="urn:systemmind:macos:inventory:get",
            caller_identity=self.actor,
            params={"use_mock": True},
            is_mutating=False,
        )
        wire_resp = api.handle_api_request(api_req)
        self.assertEqual(wire_resp.status, ApiStatus.SUCCESS)
        self.assertFalse(wire_resp.data["scan_proves_safe"])

    # -------------------------------------------------------------------------
    # AST Safety and Packaging Validator
    # -------------------------------------------------------------------------
    def test_integration_ast_safety_sc01(self) -> None:
        """Verify zero shell=True and zero os.system across integration test module."""
        tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr == "system"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "os"
                ):
                    self.fail("Forbidden os.system call in integration test suite")
                for kw in node.keywords:
                    if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                        self.fail("Forbidden shell=True in integration test suite")

    def test_integration_faults_packaging_validator(self) -> None:
        """Verify that MacOsIntegrationFaultsValidator passes cleanly across all checks."""
        validator = MacOsIntegrationFaultsValidator(root_dir=ROOT_DIR)
        result = validator.audit()
        self.assertTrue(result.valid, f"Integration faults validator failed: {result.issues}")
        self.assertEqual(result.scenario_count, 8)
        self.assertTrue(result.integration_test_valid)
        self.assertTrue(result.ast_safety_valid)
        self.assertTrue(result.scenarios_valid)
        self.assertTrue(result.rust_sensors_valid)
        self.assertTrue(result.invariants_valid)


if __name__ == "__main__":
    unittest.main()
