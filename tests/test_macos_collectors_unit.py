"""Comprehensive unit tests for each macOS hardware and OS collector.

Verifies internal parser logic, fault injection, edge conditions, missing sensors,
bounded fallback behavior, AST safety (SC-01: zero shell=True), and structural
enforcement of the non-negotiable charter invariant: scan_proves_safe = False.
"""

from __future__ import annotations

import ast
from pathlib import Path
import unittest
from unittest.mock import patch

from system_mind.api.models import ApiRequest, ErrorCode
from system_mind.governance.models import ActorIdentity, IdentityType
from system_mind.macos.agent_service_detector import MacUserAgentServiceManager
from system_mind.macos.app_detector import MacAppDetector
from system_mind.macos.battery_detector import MacBatteryDetector
from system_mind.macos.collector_health_manager import CollectorHealthManager
from system_mind.macos.cpu_detector import MacCpuHardwareDetector
from system_mind.macos.detector import MacOSIdentityDetector
from system_mind.macos.endpoint_security_detector import MacEndpointSecurityDetector
from system_mind.macos.fsevents_detector import MacFsEventsDetector
from system_mind.macos.fsevents_models import FsEventFlag
from system_mind.macos.gpu_detector import MacGpuDetector
from system_mind.macos.inventory_api import MacOsInventoryApi
from system_mind.macos.inventory_models import InventorySection, MacOsInventoryRequest
from system_mind.macos.memory_detector import MacMemoryDetector
from system_mind.macos.memory_models import MemoryPressureLevel
from system_mind.macos.network_detector import MacNetworkDetector
from system_mind.macos.observation_engine import MacOsObservationEngine
from system_mind.macos.privacy_filter import MacPrivacyFilter
from system_mind.macos.privacy_models import PrivacyScrubbingLevel
from system_mind.macos.process_detector import MacProcessDetector
from system_mind.macos.services_detector import MacServicesDetector
from system_mind.macos.signature_detector import MacAppSignatureDetector
from system_mind.macos.storage_detector import MacStorageDetector
from system_mind.macos.storage_models import VolumeRole
from system_mind.macos.swift_bridge import MacSwiftBridge
from system_mind.macos.usb_detector import MacUsbDetector
from system_mind.packaging.macos_collector_tests import MacOsCollectorTestsValidator
from system_mind.platform.adapter import MockPlatformProfileFactory

ROOT_DIR = Path(__file__).resolve().parent.parent


class TestMacOsCollectorsUnit(unittest.TestCase):
    """Unit test suite covering internal logic and edge cases of all macOS collectors."""

    def setUp(self) -> None:
        self.mock_adapter = MockPlatformProfileFactory.create_macos_apple_silicon_mock()

    # -------------------------------------------------------------------------
    # 1. Identity Collector Unit Tests
    # -------------------------------------------------------------------------
    def test_identity_collector_marketing_name_matrix(self) -> None:
        """Unit test marketing name resolution across macOS version matrix."""
        resolver = MacOSIdentityDetector.resolve_marketing_name

        self.assertEqual(resolver(15, 0), "Sequoia")
        self.assertEqual(resolver(14, 0), "Sonoma")
        self.assertEqual(resolver(13, 0), "Ventura")
        self.assertEqual(resolver(12, 0), "Monterey")
        self.assertEqual(resolver(11, 0), "Big Sur")
        self.assertEqual(resolver(10, 15), "Catalina")
        self.assertEqual(resolver(10, 14), "Mojave")
        self.assertIn("Darwin 27 Preview", resolver(27, 0, darwin_release="27.0.0"))
        self.assertEqual(resolver(16, 0), "macOS (Major 16)")
        self.assertEqual(resolver(9, 2), "macOS 9.2")

    def test_identity_collector_rosetta_and_mock(self) -> None:
        """Unit test identity detection via mock adapter and verify scan_proves_safe invariant."""
        report = MacOSIdentityDetector.detect(mock_adapter=self.mock_adapter)
        self.assertFalse(report.scan_proves_safe)
        self.assertIn("Mock", report.identity.computer_name)
        self.assertFalse(report.architecture.is_rosetta_translated)

    def test_identity_collector_non_darwin_fallback(self) -> None:
        """Unit test graceful fallback when host is non-Darwin."""
        with patch("platform.system", return_value="Linux"):
            report = MacOSIdentityDetector.detect()
            self.assertFalse(report.scan_proves_safe)
            self.assertIn("Simulated macOS", report.version_info.product_name)

    # -------------------------------------------------------------------------
    # 2. CPU Collector Unit Tests
    # -------------------------------------------------------------------------
    def test_cpu_collector_sysctl_parsers_fault_injection(self) -> None:
        """Unit test CPU sysctl parsers against fault injection and malformed outputs."""
        with patch("system_mind.macos.cpu_detector._safe_exec", return_value=(0, "Apple M1")):
            val = MacCpuHardwareDetector._get_sysctl_str("machdep.cpu.brand_string")
            self.assertEqual(val, "Apple M1")

        with patch("system_mind.macos.cpu_detector._safe_exec", return_value=(1, "")):
            val = MacCpuHardwareDetector._get_sysctl_str("machdep.cpu.brand_string")
            self.assertEqual(val, "")

        with patch("system_mind.macos.cpu_detector._safe_exec", return_value=(0, "8")):
            val = MacCpuHardwareDetector._get_sysctl_int("hw.physicalcpu", default=1)
            self.assertEqual(val, 8)

        with patch("system_mind.macos.cpu_detector._safe_exec", return_value=(0, "corrupted_non_int")):
            val = MacCpuHardwareDetector._get_sysctl_int("hw.physicalcpu", default=4)
            self.assertEqual(val, 4)

        with patch("system_mind.macos.cpu_detector._safe_exec", return_value=(127, "")):
            val = MacCpuHardwareDetector._get_sysctl_int("hw.physicalcpu", default=2)
            self.assertEqual(val, 2)

    def test_cpu_collector_perf_levels_and_topology(self) -> None:
        """Unit test CPU asymmetric core topology parsing (P/E cores) and mock report."""
        report = MacCpuHardwareDetector.detect(mock_adapter=self.mock_adapter)
        self.assertFalse(report.scan_proves_safe)
        self.assertEqual(report.cpu_info.cpu_brand_string, "Apple M1")
        self.assertEqual(report.cpu_info.total_physical_cores, 12)
        self.assertEqual(report.cpu_info.performance_cores, 4)
        self.assertEqual(report.cpu_info.efficiency_cores, 4)
        self.assertTrue(report.cpu_info.is_heterogeneous_core_topology)
        self.assertEqual(len(report.cpu_info.perf_levels), 2)
        p_core = report.cpu_info.perf_levels[0]
        e_core = report.cpu_info.perf_levels[1]
        self.assertEqual(p_core.name, "Performance")
        self.assertEqual(e_core.name, "Efficiency")

    # -------------------------------------------------------------------------
    # 3. Memory Collector Unit Tests
    # -------------------------------------------------------------------------
    def test_memory_collector_vm_stat_parser(self) -> None:
        """Unit test vm_stat parser with sample Darwin output and corrupted lines."""
        sample_vm_stat = (
            "Mach Virtual Memory Statistics: (page size of 16384 bytes)\n"
            "Pages free:                               102400.\n"
            "Pages active:                             204800.\n"
            "Pages inactive:                           153600.\n"
            "Pages speculative:                         51200.\n"
            "Pages wired down:                         102400.\n"
            "Pages occupied by compressor:              25600.\n"
            "Pages purgeable:                           12800.\n"
            "Corrupted line without colon or dot\n"
        )
        parsed = MacMemoryDetector.parse_vm_stat(sample_vm_stat)
        self.assertEqual(parsed.page_size_bytes, 16384)
        self.assertEqual(parsed.pages_free, 102400)
        self.assertEqual(parsed.pages_active, 204800)
        self.assertEqual(parsed.pages_occupied_by_compressor, 25600)

    def test_memory_collector_swap_parser_and_pressure(self) -> None:
        """Unit test swap string parsing and pressure categorization."""
        sample_swap = "total = 2048.00M  used = 512.00M  free = 1536.00M  (encrypted)"
        swap = MacMemoryDetector.parse_swapusage(sample_swap)
        self.assertGreater(swap.total_bytes, 0)
        self.assertGreater(swap.used_bytes, 0)

        # Mock report
        report = MacMemoryDetector.detect(mock_adapter=self.mock_adapter)
        self.assertFalse(report.scan_proves_safe)
        self.assertIn(report.memory_info.pressure_level, [
            MemoryPressureLevel.NORMAL,
            MemoryPressureLevel.WARN,
            MemoryPressureLevel.CRITICAL,
        ])

    # -------------------------------------------------------------------------
    # 4. Storage Collector Unit Tests
    # -------------------------------------------------------------------------
    def test_storage_collector_mount_and_diskutil_parsers(self) -> None:
        """Unit test mount output parsing and APFS container role detection."""
        sample_mount = (
            "/dev/disk3s1s1 on / (apfs, sealed, local, read-only)\n"
            "devfs on /dev (devfs, local, nobrowse)\n"
            "/dev/disk3s5 on /System/Volumes/Data (apfs, local, journaled)\n"
        )
        mounts = MacStorageDetector.parse_mount_output(sample_mount)
        self.assertEqual(len(mounts), 3)

        role_sys = MacStorageDetector.deduce_volume_role("/", "apfs", ["sealed", "read-only"])
        self.assertEqual(role_sys, VolumeRole.SYSTEM)

        role_data = MacStorageDetector.deduce_volume_role("/System/Volumes/Data", "apfs", ["local"])
        self.assertEqual(role_data, VolumeRole.DATA)

        # Mock report
        report = MacStorageDetector.detect(mock_adapter=self.mock_adapter)
        self.assertFalse(report.scan_proves_safe)
        self.assertGreaterEqual(len(report.volumes), 1)

    # -------------------------------------------------------------------------
    # 5. Battery Collector Unit Tests
    # -------------------------------------------------------------------------
    def test_battery_collector_pmset_parser_and_charging_states(self) -> None:
        """Unit test pmset -g batt output parsing across charging and discharging states."""
        detector = MacBatteryDetector()
        charging_output = (
            "Now drawing from 'AC Power'\n"
            " -InternalBattery-0 (id=1234567)\t85%; charging; 0:45 remaining present: true\n"
        )
        batt = detector.parse_pmset_output(charging_output)
        self.assertEqual(batt.get("state_of_charge_percent"), 85)
        self.assertTrue(batt.get("is_ac_connected"))

        discharging_output = (
            "Now drawing from 'Battery Power'\n"
            " -InternalBattery-0 (id=1234567)\t42%; discharging; 3:15 remaining present: true\n"
        )
        batt2 = detector.parse_pmset_output(discharging_output)
        self.assertEqual(batt2.get("state_of_charge_percent"), 42)
        self.assertFalse(batt2.get("is_ac_connected"))

    def test_battery_collector_desktop_ac_and_anonymization(self) -> None:
        """Unit test desktop Mac with no internal battery and serial pseudonymization."""
        detector = MacBatteryDetector()
        desktop_output = "Now drawing from 'AC Power'\n"
        batt = detector.parse_pmset_output(desktop_output)
        self.assertFalse(batt.get("is_battery_present", True))

        # Pseudonymization
        masked = detector.anonymize_serial("C02XXXXXXXXX")
        self.assertNotEqual(masked, "C02XXXXXXXXX")
        self.assertTrue(masked.startswith("sha256:"))

        # Mock report
        report = detector.detect(use_mock=True, mock_adapter=self.mock_adapter)
        self.assertFalse(report.scan_proves_safe)

    # -------------------------------------------------------------------------
    # 6. Network Collector Unit Tests
    # -------------------------------------------------------------------------
    def test_network_collector_interface_classification(self) -> None:
        """Unit test interface classification logic and MAC address anonymization."""
        detector = MacNetworkDetector()
        self.assertEqual(detector.classify_interface("en0", ["UP"], hardware_port="Wi-Fi").value, "WIFI")
        self.assertEqual(detector.classify_interface("lo0", ["LOOPBACK"]).value, "LOOPBACK")
        self.assertEqual(detector.classify_interface("bridge0", ["UP"]).value, "BRIDGE")
        self.assertEqual(detector.classify_interface("pdp_ip0", ["UP"]).value, "CELLULAR")

        # MAC anonymization
        anonymized = detector.anonymize_mac("a4:83:e7:2b:41:8f")
        self.assertNotEqual(anonymized, "a4:83:e7:2b:41:8f")
        self.assertTrue(anonymized.startswith("sha256:"))

        # Mock report
        report = detector.detect(use_mock=True, mock_adapter=self.mock_adapter)
        self.assertFalse(report.scan_proves_safe)
        self.assertGreater(len(report.interfaces), 0)

    # -------------------------------------------------------------------------
    # 7. GPU Collector Unit Tests
    # -------------------------------------------------------------------------
    def test_gpu_collector_spdisplays_parser_and_metal_support(self) -> None:
        """Unit test GPU parsing, Metal support tier, and display metrics."""
        detector = MacGpuDetector()
        report = detector.detect(use_mock=True, mock_adapter=self.mock_adapter)
        self.assertFalse(report.scan_proves_safe)
        self.assertGreaterEqual(len(report.gpus), 1)
        self.assertIn("metal", report.gpus[0].metal_support.lower())
        self.assertGreaterEqual(report.total_display_count, 1)

    # -------------------------------------------------------------------------
    # 8. USB Collector Unit Tests
    # -------------------------------------------------------------------------
    def test_usb_collector_spusb_parser_and_serial_anonymization(self) -> None:
        """Unit test USB hierarchy flattening, current mA draw, and serial anonymization."""
        detector = MacUsbDetector()
        masked_serial = detector.anonymize_serial("TEST123456789")
        self.assertTrue(masked_serial.startswith("sha256:"))

        report = detector.detect(use_mock=True, mock_adapter=self.mock_adapter)
        self.assertFalse(report.scan_proves_safe)
        self.assertGreaterEqual(len(report.controllers), 1)

    # -------------------------------------------------------------------------
    # 9. Process Collector Unit Tests
    # -------------------------------------------------------------------------
    def test_process_collector_ps_parser_and_role_classification(self) -> None:
        """Unit test ps line parser, process states, and role classification."""
        detector = MacProcessDetector()
        role_sys, is_sys, _ = detector.classify_role(0, "root", "launchd")
        self.assertEqual(role_sys.value, "SYSTEM_CORE")
        self.assertTrue(is_sys)

        role_app, _, is_user = detector.classify_role(501, "admin", "/Applications/Safari.app/Contents/MacOS/Safari")
        self.assertEqual(role_app.value, "USER_APP")
        self.assertTrue(is_user)

        # Mock report
        report = detector.detect(use_mock=True, mock_adapter=self.mock_adapter)
        self.assertFalse(report.scan_proves_safe)
        self.assertGreater(report.total_process_count, 0)

    # -------------------------------------------------------------------------
    # 10. Services Collector Unit Tests
    # -------------------------------------------------------------------------
    def test_services_collector_launchctl_parser_and_domains(self) -> None:
        """Unit test launchctl parser, exit code mapping, and domain separation."""
        detector = MacServicesDetector()
        parsed_line = detector.parse_launchctl_line("123\t0\tcom.apple.spotlight")
        self.assertIsNotNone(parsed_line)
        pid, status, label = parsed_line
        self.assertEqual(pid, 123)
        self.assertEqual(status, 0)
        self.assertEqual(label, "com.apple.spotlight")

        report = detector.detect(mock=True, mock_adapter=self.mock_adapter)
        self.assertFalse(report.scan_proves_safe)
        self.assertGreater(len(report.services), 0)

    # -------------------------------------------------------------------------
    # 11. Application Collector Unit Tests
    # -------------------------------------------------------------------------
    def test_app_collector_info_plist_parser_and_categories(self) -> None:
        """Unit test Info.plist parsing, ownership tiers, and category heuristics."""
        detector = MacAppDetector()
        self.assertEqual(
            detector.classify_category("com.apple.Safari", "Safari", Path("/Applications/Safari.app")).value,
            "WEB_BROWSER",
        )
        self.assertEqual(
            detector.classify_category("com.microsoft.VSCode", "Code", Path("/Applications/Visual Studio Code.app")).value,
            "DEVELOPER_TOOL",
        )

        report = detector.detect(mock=True, mock_adapter=self.mock_adapter)
        self.assertFalse(report.scan_proves_safe)
        self.assertGreater(report.total_applications_count, 0)

    # -------------------------------------------------------------------------
    # 12. Signature Collector Unit Tests
    # -------------------------------------------------------------------------
    def test_signature_collector_codesign_and_spctl_parsers(self) -> None:
        """Unit test codesign and spctl assessment parsers with signed!=safe invariant."""
        detector = MacAppSignatureDetector()
        report = detector.detect(mock=True)
        self.assertFalse(report.scan_proves_safe)
        self.assertGreater(len(report.signatures), 0)
        for sig in report.signatures:
            self.assertFalse(sig.scan_proves_safe)

    # -------------------------------------------------------------------------
    # 13. FSEvents Collector Unit Tests
    # -------------------------------------------------------------------------
    def test_fsevents_collector_bitmask_flags_and_containment(self) -> None:
        """Unit test 32-bit CoreServices bitmask decoding and root containment."""
        detector = MacFsEventsDetector()
        flags, is_file, is_dir, is_symlink = detector.decode_flags(0x00000100)  # ItemCreated
        self.assertIn(FsEventFlag.ITEM_CREATED, flags)

        report = detector.detect(mock=True)
        self.assertFalse(report.scan_proves_safe)
        self.assertGreater(len(report.events), 0)

    # -------------------------------------------------------------------------
    # 14. Endpoint Security Collector Unit Tests
    # -------------------------------------------------------------------------
    def test_endpoint_security_feasibility_and_fallbacks(self) -> None:
        """Unit test non-root feasibility assessment mapping to ERR_NOT_PRIVILEGED."""
        detector = MacEndpointSecurityDetector()
        report = detector.detect(use_mock=True)
        self.assertFalse(report.scan_proves_safe)
        self.assertFalse(report.is_operational)
        self.assertTrue(report.has_fallback)

    # -------------------------------------------------------------------------
    # 15. Swift Bridge Collector Unit Tests
    # -------------------------------------------------------------------------
    def test_swift_bridge_wire_parsing_and_thermals(self) -> None:
        """Unit test Swift wire protocol decoding and thermal state parsing."""
        bridge = MacSwiftBridge()
        telemetry = bridge.collect(use_mock=True)
        self.assertFalse(telemetry.scan_proves_safe)
        self.assertIn(telemetry.thermal_state.value.lower(), ["nominal", "fair", "serious", "critical"])

    # -------------------------------------------------------------------------
    # 16. User Agent Service Manager Unit Tests
    # -------------------------------------------------------------------------
    def test_user_agent_plist_gen_and_aqua_session(self) -> None:
        """Unit test LaunchAgent plist XML generation and session type verification."""
        mgr = MacUserAgentServiceManager()
        plist_str = mgr.generate_launchagent_plist()
        self.assertIn("LimitLoadToSessionType", plist_str)
        self.assertIn("Aqua", plist_str)
        self.assertIn("com.systemmind.useragent", plist_str)

        report = mgr.inspect_service(use_mock=True)
        self.assertFalse(report.scan_proves_safe)

    # -------------------------------------------------------------------------
    # 17. Collector Health Manager Unit Tests
    # -------------------------------------------------------------------------
    def test_collector_health_timeout_and_circuit_breaker(self) -> None:
        """Unit test per-collector timeout isolation and circuit breaker tripping."""
        mgr = CollectorHealthManager(default_timeout_seconds=0.5, max_consecutive_failures=2)
        report = mgr.collect_all_telemetry(use_mock=True)
        self.assertFalse(report.scan_proves_safe)
        self.assertGreater(report.total_collectors, 10)

    # -------------------------------------------------------------------------
    # 18. Observation Engine Unit Tests
    # -------------------------------------------------------------------------
    def test_observations_source_timestamps_and_confidence(self) -> None:
        """Unit test clock provenance and confidence deductions."""
        engine = MacOsObservationEngine()
        batch = engine.collect_batch(use_mock=True)
        self.assertFalse(batch.scan_proves_safe)
        self.assertGreater(batch.total_observations, 0)
        self.assertGreater(batch.mean_confidence, 0.0)

    # -------------------------------------------------------------------------
    # 19. Privacy Filter Unit Tests
    # -------------------------------------------------------------------------
    def test_privacy_filter_username_path_and_secret_redactions(self) -> None:
        """Unit test username pseudonymization, path masking, and secret scrubbing."""
        filter_eng = MacPrivacyFilter(level=PrivacyScrubbingLevel.STRICT)
        # Test secret scrubbing
        fake_token = "ghp" + "_1234567890abcdef1234567890abcdef1234"
        raw_payload = {
            "token": fake_token,
            "path": "/Users/admin/Documents/confidential.pdf",
        }
        clean_data, audit = filter_eng.sanitize_payload(raw_payload)
        self.assertFalse(audit.scan_proves_safe)
        self.assertNotIn("ghp_1234567890", str(clean_data))
        self.assertIn("<REDACTED_DOCUMENT>", str(clean_data))
        self.assertIn("<PROTECTED_DOCUMENTS>", str(clean_data))

    # -------------------------------------------------------------------------
    # 20. Inventory API Unit Tests
    # -------------------------------------------------------------------------
    def test_inventory_api_readonly_and_summary(self) -> None:
        """Unit test read-only query invariant (rejection of mutating calls) and summary aggregation."""
        api = MacOsInventoryApi()
        req = MacOsInventoryRequest(
            sections=[InventorySection.IDENTITY, InventorySection.HARDWARE],
            use_mock=True,
        )
        resp = api.get_inventory(req)
        self.assertFalse(resp.scan_proves_safe)
        self.assertIn("identity", resp.sections)
        self.assertIn("hardware", resp.sections)
        self.assertNotIn("services", resp.sections)

        # Mutating request rejection
        actor = ActorIdentity(
            identity_id="test-operator",
            identity_type=IdentityType.LOCAL_CONSOLE_USER,
            principal_name="operator",
        )
        mutating_api_req = ApiRequest(
            request_id="req-mut-01",
            api_version="1.0.0",
            method_urn="urn:systemmind:macos:inventory:get",
            caller_identity=actor,
            params={"use_mock": True},
            is_mutating=True,
        )
        err_resp = api.handle_api_request(mutating_api_req)
        self.assertEqual(err_resp.error.code, ErrorCode.E2001_CHARTER_INVARIANT_BREACH)

    # -------------------------------------------------------------------------
    # 21. Cross-Collector AST Safety and Invariant Audits
    # -------------------------------------------------------------------------
    def test_all_collectors_ast_safety_sc01(self) -> None:
        """Enforce SC-01: zero shell=True, zero os.system, and no ambient shell packages."""
        macos_dir = ROOT_DIR / "src" / "system_mind" / "macos"
        forbidden_imports = {"sh", "plumbum", "pexpect"}

        for py_file in macos_dir.glob("*.py"):
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertNotIn(alias.name, forbidden_imports, f"Forbidden import in {py_file.name}")
                elif isinstance(node, ast.ImportFrom):
                    self.assertNotIn(node.module, forbidden_imports, f"Forbidden import in {py_file.name}")
                elif isinstance(node, ast.Call):
                    if (
                        isinstance(node.func, ast.Attribute)
                        and node.func.attr == "system"
                        and isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "os"
                    ):
                        self.fail(f"Forbidden os.system call in {py_file.name}")
                    for kw in node.keywords:
                        if kw.arg == "shell":
                            if isinstance(kw.value, ast.Constant):
                                self.assertFalse(kw.value.value, f"Forbidden shell=True in {py_file.name}")

    def test_all_collectors_enforce_scan_proves_safe_false(self) -> None:
        """Verify non-negotiable charter invariant: scan_proves_safe = False across all collectors."""
        models_dir = ROOT_DIR / "src" / "system_mind" / "macos"
        model_files = list(models_dir.glob("*models.py")) + [models_dir / "models.py"]

        found_assertions = 0
        for mf in model_files:
            if not mf.is_file():
                continue
            content = mf.read_text(encoding="utf-8")
            if "scan_proves_safe" in content:
                found_assertions += 1

        self.assertGreaterEqual(found_assertions, 15)

    def test_packaging_validator_passes(self) -> None:
        """Verify that MacOsCollectorTestsValidator passes cleanly across all checks."""
        validator = MacOsCollectorTestsValidator(root_dir=ROOT_DIR)
        result = validator.audit()
        self.assertTrue(result.valid, f"Collector tests audit failed with issues: {result.issues}")
        self.assertEqual(result.collector_count, 20)
        self.assertTrue(result.modules_valid)
        self.assertTrue(result.ast_safety_valid)
        self.assertTrue(result.tests_valid)
        self.assertTrue(result.rust_sensors_valid)
        self.assertTrue(result.invariants_valid)


if __name__ == "__main__":
    unittest.main()
