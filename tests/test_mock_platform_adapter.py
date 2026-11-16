"""Comprehensive unit, integration, and contract tests for the Mock Platform Adapter subsystem."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import pytest

from system_mind.core.types import (
    ActionContract,
    ApprovalRequirement,
    ComponentOwnership,
    FileExecutionContainment,
    HostEnvironmentReport,
    OperationRiskTier,
    PlatformTier,
    Reversibility,
)
from system_mind.packaging.mock_platform import (
    MockPlatformAuditResult,
    MockPlatformValidator,
)
from system_mind.platform.adapter import (
    FileProvenanceSnapshot,
    FsEventSnapshot,
    HardwareTelemetrySnapshot,
    MockPlatformAdapter,
    MockPlatformProfileFactory,
    PlatformAdapter,
    ProcessTelemetrySnapshot,
    RollbackResult,
    SecurityStateSnapshot,
    SnapshotResult,
    UpdateStageResult,
)
from system_mind.platform.matrix import (
    PlatformMatrixRegistry,
    PlatformTargetId,
)


def test_platform_adapter_abc_contract():
    """Verify PlatformAdapter cannot be instantiated directly and requires concrete implementations."""
    with pytest.raises(TypeError):
        PlatformAdapter()  # type: ignore


def test_mock_platform_adapter_instantiation_all_targets():
    """Verify MockPlatformAdapter can be instantiated for all 4 supported first-release targets."""
    for target in PlatformTargetId:
        adapter = MockPlatformProfileFactory.create_mock(target)
        assert adapter.get_target_id() == target

        host = adapter.get_host_report()
        assert isinstance(host, HostEnvironmentReport)
        assert host.is_supported_host is True
        assert host.cpu_cores >= 2
        assert host.memory_bytes >= 4 * 1024 * 1024 * 1024

        sec = adapter.get_security_state()
        assert isinstance(sec, SecurityStateSnapshot)
        assert sec.target_id == target


def test_mock_security_state_inspection():
    """Verify detailed security state properties across platforms."""
    # macOS Apple Silicon
    mac_adapter = MockPlatformProfileFactory.create_macos_apple_silicon_mock()
    mac_sec = mac_adapter.get_security_state()
    assert mac_sec.sip_enabled is True
    assert mac_sec.gatekeeper_enabled is True
    assert mac_sec.disk_encryption_enabled is True
    assert mac_sec.secure_boot_enabled is True

    # Windows 11
    win_adapter = MockPlatformProfileFactory.create_windows_11_mock()
    win_sec = win_adapter.get_security_state()
    assert win_sec.sip_enabled is None
    assert win_sec.secure_boot_enabled is True
    assert win_sec.disk_encryption_enabled is True

    # Ubuntu LTS
    ubu_adapter = MockPlatformProfileFactory.create_ubuntu_lts_mock()
    ubu_sec = ubu_adapter.get_security_state()
    assert ubu_sec.selinux_or_apparmor_status is not None
    assert "AppArmor" in ubu_sec.selinux_or_apparmor_status

    # NixOS VM
    nix_adapter = MockPlatformProfileFactory.create_nixos_vm_mock()
    nix_sec = nix_adapter.get_security_state()
    assert nix_sec.disk_encryption_enabled is False


def test_mock_hardware_telemetry_and_mutators():
    """Verify hardware telemetry collection and pure in-memory mutators."""
    adapter = MockPlatformProfileFactory.create_macos_apple_silicon_mock()
    telemetry = adapter.get_hardware_telemetry()

    assert telemetry.cpu_usage_pct == 12.5
    assert telemetry.thermal_state == "NOMINAL"
    assert telemetry.power_source == "AC_POWER"

    # Mutate thermal state
    adapter.set_thermal_state("SERIOUS")
    assert adapter.get_hardware_telemetry().thermal_state == "SERIOUS"

    with pytest.raises(ValueError, match="Invalid thermal state"):
        adapter.set_thermal_state("SUPER_HOT")

    # Mutate power source
    adapter.set_power_source("BATTERY", battery_pct=35.0, is_charging=False)
    updated_telemetry = adapter.get_hardware_telemetry()
    assert updated_telemetry.power_source == "BATTERY"
    assert updated_telemetry.battery_pct == 35.0
    assert updated_telemetry.is_charging is False

    # Mutate disk space
    adapter.set_disk_available(5 * 1024 * 1024 * 1024)
    assert adapter.get_hardware_telemetry().disk_available_bytes == 5 * 1024 * 1024 * 1024


def test_mock_process_telemetry_and_injection():
    """Verify process telemetry query and process injection."""
    adapter = MockPlatformProfileFactory.create_macos_apple_silicon_mock()
    procs = adapter.get_process_telemetry()
    assert len(procs) >= 3

    pids = [p.pid for p in procs]
    assert 1 in pids
    assert 501 in pids

    # Inject mock suspicious process
    injected_proc = ProcessTelemetrySnapshot(
        pid=9999,
        name="cryptominer_mock",
        ppid=1,
        uid=501,
        gid=20,
        cpu_pct=98.5,
        memory_bytes=1024 * 1024 * 500,
        signature_valid=False,
        is_system_core=False,
        is_user_app=False,
    )
    adapter.add_simulated_process(injected_proc)
    updated_procs = adapter.get_process_telemetry()
    assert any(p.pid == 9999 for p in updated_procs)


def test_mock_filesystem_events_and_filtering():
    """Verify filesystem event injection and path filtering."""
    adapter = MockPlatformProfileFactory.create_macos_apple_silicon_mock()
    assert len(adapter.get_filesystem_events()) == 0

    event1 = FsEventSnapshot(
        event_id="evt_001",
        path="/etc/hosts",
        event_type="MODIFIED",
        is_directory=False,
    )
    event2 = FsEventSnapshot(
        event_id="evt_002",
        path="/Users/developer/Downloads/sample.pkg",
        event_type="CREATED",
        is_directory=False,
    )
    adapter.add_simulated_fs_event(event1)
    adapter.add_simulated_fs_event(event2)

    assert len(adapter.get_filesystem_events()) == 2
    assert len(adapter.get_filesystem_events("/etc")) == 1
    assert adapter.get_filesystem_events("/etc")[0].event_id == "evt_001"
    assert len(adapter.get_filesystem_events("/Users/developer/Downloads")) == 1


def test_mock_file_provenance_and_quarantine():
    """Verify file provenance, quarantine tracking, and custom injection."""
    adapter = MockPlatformProfileFactory.create_macos_apple_silicon_mock()

    # Query normal file
    normal_prov = adapter.get_file_provenance("/usr/local/bin/my_tool")
    assert normal_prov.is_quarantined is False
    assert normal_prov.zone_identifier == 0
    assert normal_prov.sha256_hash != ""

    # Query download folder file (should detect quarantine synthetic flag)
    quarantine_prov = adapter.get_file_provenance("/Users/developer/Downloads/untrusted_agent.py")
    assert quarantine_prov.is_quarantined is True
    assert quarantine_prov.zone_identifier == 3
    assert quarantine_prov.quarantine_xattr is not None

    # Inject specific provenance record
    custom = FileProvenanceSnapshot(
        path="/custom/payload.bin",
        sha256_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        file_size_bytes=100,
        quarantine_xattr="CustomSecurityTag",
        zone_identifier=4,
        origin_url="https://malicious.example.com",
        is_quarantined=True,
    )
    adapter.add_simulated_provenance(custom)
    retrieved = adapter.get_file_provenance("/custom/payload.bin")
    assert retrieved == custom


def test_mock_snapshot_and_rollback_lifecycle():
    """Verify system snapshot creation, audit logging, and safe rollback."""
    adapter = MockPlatformProfileFactory.create_macos_apple_silicon_mock()

    snap_result = adapter.create_system_snapshot("pre_maintenance_baseline")
    assert snap_result.success is True
    assert snap_result.snapshot_id.startswith("snap_")
    assert snap_result.size_bytes > 0

    # Revert to snapshot
    rollback_result = adapter.rollback_system_snapshot(snap_result.snapshot_id)
    assert rollback_result.success is True
    assert rollback_result.snapshot_id == snap_result.snapshot_id
    assert "Successfully rolled back" in rollback_result.details

    # Revert to nonexistent snapshot fails safely
    missing_result = adapter.rollback_system_snapshot("snap_nonexistent_9999")
    assert missing_result.success is False
    assert "not found" in (missing_result.error_message or "")


def test_mock_system_update_staging_and_user_app_protection():
    """Verify system updates can be staged for system components but strictly rejected for user apps."""
    adapter = MockPlatformProfileFactory.create_macos_apple_silicon_mock()

    # System core update succeeds
    sys_result = adapter.stage_system_update("OS_SECURITY_PATCH_2026_11", ComponentOwnership.SYSTEM_MANAGED)
    assert sys_result.staged is True
    assert sys_result.component_ownership == ComponentOwnership.SYSTEM_MANAGED

    # Vendor driver update succeeds
    vendor_result = adapter.stage_system_update("VENDOR_WIFI_DRIVER_v2", ComponentOwnership.VENDOR_MANAGED)
    assert vendor_result.staged is True

    # User app update is strictly prohibited (SC-02)
    with pytest.raises(PermissionError, match="USER_MANAGED"):
        adapter.stage_system_update("com.brave.Browser", ComponentOwnership.USER_MANAGED)


def test_mock_action_execution_safety_guards():
    """Verify action contract execution adheres to user application protection and approval gates."""
    adapter = MockPlatformProfileFactory.create_macos_apple_silicon_mock()

    # Valid low risk system action
    valid_contract = ActionContract(
        action_id="act_prune_temp_cache",
        action_type="PRUNE_CACHE",
        target_component="system_cache",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        risk_tier=OperationRiskTier.LOW_IMPACT,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.NONE,
    )
    result = adapter.execute_contained_action(valid_contract)
    assert result["status"] == "COMPLETED"
    assert result["action_id"] == "act_prune_temp_cache"

    # Autonomous maintenance on user-managed application fails (SC-02)
    user_app_contract = ActionContract(
        action_id="act_auto_update_chrome",
        action_type="UPDATE_APP",
        target_component="Google Chrome",
        target_ownership=ComponentOwnership.USER_MANAGED,
        risk_tier=OperationRiskTier.MEDIUM_IMPACT,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.NONE,
        is_autonomous_maintenance=True,
    )
    with pytest.raises(PermissionError, match="SC-02"):
        adapter.execute_contained_action(user_app_contract)

    # Critical action without approval fails (SC-03)
    critical_contract = ActionContract(
        action_id="act_format_drive",
        action_type="WIPE_PARTITION",
        target_component="disk0s2",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        risk_tier=OperationRiskTier.CRITICAL_PRIVILEGED,
        reversibility=Reversibility.IRREVERSIBLE,
        approval_requirement=ApprovalRequirement.USER_EXPLICIT,
        user_approved=False,
    )
    with pytest.raises(PermissionError, match="requires explicit user approval"):
        adapter.execute_contained_action(critical_contract)

    # Critical action with approval succeeds
    approved_critical = ActionContract(
        action_id="act_format_drive_approved",
        action_type="WIPE_PARTITION",
        target_component="disk0s2",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        risk_tier=OperationRiskTier.CRITICAL_PRIVILEGED,
        reversibility=Reversibility.IRREVERSIBLE,
        approval_requirement=ApprovalRequirement.USER_EXPLICIT,
        user_approved=True,
    )
    approved_result = adapter.execute_contained_action(approved_critical)
    assert approved_result["status"] == "COMPLETED"


def test_mock_error_fault_injection():
    """Verify fault injection via simulate_error and clearing."""
    adapter = MockPlatformProfileFactory.create_macos_apple_silicon_mock()

    adapter.simulate_error("get_hardware_telemetry", IOError("Simulated IOKit hardware sensor bus failure"))
    with pytest.raises(IOError, match="Simulated IOKit hardware sensor bus failure"):
        adapter.get_hardware_telemetry()

    adapter.clear_simulated_errors()
    telemetry = adapter.get_hardware_telemetry()
    assert telemetry.thermal_state == "NOMINAL"


def test_mock_profile_factory_presets():
    """Verify all convenience factory preset profiles."""
    battery_mock = MockPlatformProfileFactory.create_constrained_battery_mock()
    assert battery_mock.get_hardware_telemetry().power_source == "BATTERY"
    assert battery_mock.get_hardware_telemetry().battery_pct == 14.0

    thermal_mock = MockPlatformProfileFactory.create_critical_thermal_mock()
    assert thermal_mock.get_hardware_telemetry().thermal_state == "CRITICAL"

    insecure_mock = MockPlatformProfileFactory.create_insecure_host_mock()
    assert insecure_mock.get_security_state().sip_enabled is False
    assert insecure_mock.get_security_state().gatekeeper_enabled is False


def test_mock_platform_validator_audits_clean():
    """Verify programmatic validator passes clean audit of the mock platform adapter subsystem."""
    audit_result = MockPlatformValidator.audit()
    assert audit_result.valid is True, f"Validation failed with issues: {audit_result.issues}"
    assert audit_result.adapter_interface_valid is True
    assert audit_result.mock_profiles_valid is True
    assert audit_result.safety_invariants_valid is True
    assert audit_result.cli_runner_valid is True
    assert len(audit_result.issues) == 0


def test_mock_platform_cli_subcommands():
    """Verify tools/mock_platform_cli.py executes correctly across subcommands and JSON output."""
    cli_path = Path(__file__).resolve().parent.parent / "tools" / "mock_platform_cli.py"

    # inspect
    p_inspect = subprocess.run(
        [sys.executable, str(cli_path), "inspect", "--target", "UBUNTU_LTS_X64", "--json"],
        capture_output=True,
        text=True,
        check=True,
    )
    inspect_data = json.loads(p_inspect.stdout)
    assert inspect_data["target_id"] == "UBUNTU_LTS_X64"
    assert inspect_data["host_report"]["os_name"] == "Linux"

    # telemetry
    p_telem = subprocess.run(
        [sys.executable, str(cli_path), "telemetry", "--target", "MACOS_APPLE_SILICON", "--json"],
        capture_output=True,
        text=True,
        check=True,
    )
    telem_data = json.loads(p_telem.stdout)
    assert telem_data["target_id"] == "MACOS_APPLE_SILICON"
    assert telem_data["hardware_telemetry"]["thermal_state"] == "NOMINAL"

    # audit-matrix
    p_audit = subprocess.run(
        [sys.executable, str(cli_path), "audit-matrix", "--json"],
        capture_output=True,
        text=True,
        check=True,
    )
    audit_data = json.loads(p_audit.stdout)
    assert audit_data["overall_valid"] is True
    assert len(audit_data["targets"]) == 4
