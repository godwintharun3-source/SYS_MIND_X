"""Unit, contract, and safety test suite for the read-only macOS inventory API and aggregation engine."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import subprocess
import sys
import pytest

from system_mind.api.models import ApiRequest, ApiStatus, ErrorCode
from system_mind.governance.models import ActorIdentity, IdentityType
from system_mind.macos.inventory_api import MacOsInventoryApi
from system_mind.macos.inventory_models import (
    InventorySection,
    MacOsInventoryRequest,
    MacOsInventoryResponse,
    MacOsInventorySummary,
)
from system_mind.macos.privacy_models import PrivacyScrubbingLevel
from system_mind.packaging.macos_inventory import (
    MacOsInventoryAuditResult,
    MacOsInventoryValidator,
)

ROOT_DIR = Path(__file__).resolve().parent.parent
CLI_PATH = ROOT_DIR / "tools" / "detect_inventory.py"


def test_inventory_models_fidelity() -> None:
    """Verify data model construction, enum mappings, dictionary conversion, and Scan!=Safe invariant."""
    assert InventorySection.ALL.value == "ALL"
    assert InventorySection.IDENTITY.value == "IDENTITY"
    assert InventorySection.HARDWARE.value == "HARDWARE"
    assert InventorySection.STORAGE.value == "STORAGE"
    assert InventorySection.NETWORK.value == "NETWORK"
    assert InventorySection.APPLICATIONS.value == "APPLICATIONS"
    assert InventorySection.SECURITY.value == "SECURITY"
    assert InventorySection.PROCESSES.value == "PROCESSES"
    assert InventorySection.SERVICES.value == "SERVICES"

    req = MacOsInventoryRequest(
        sections=[InventorySection.HARDWARE, InventorySection.STORAGE],
        privacy_level=PrivacyScrubbingLevel.STRICT,
        use_mock=True,
    )
    req_dict = req.to_dict()
    assert req_dict["sections"] == ["HARDWARE", "STORAGE"]
    assert req_dict["privacy_level"] == "STRICT"
    assert req_dict["use_mock"] is True

    summary = MacOsInventorySummary(
        os_version="15.1.0",
        os_build="24B83",
        host_name="test-device.local",
        architecture="arm64",
        cpu_model="Apple M1",
        physical_cores=8,
        logical_cores=8,
        total_memory_bytes=16 * 1024 * 1024 * 1024,
        memory_pressure_pct=12.5,
        total_storage_bytes=500 * 1024 * 1024 * 1024,
        free_storage_bytes=250 * 1024 * 1024 * 1024,
        running_process_count=200,
        installed_app_count=75,
        mean_confidence=0.915,
        overall_health="HEALTHY",
    )
    s_dict = summary.to_dict()
    assert s_dict["os_version"] == "15.1.0"
    assert s_dict["architecture"] == "arm64"
    assert s_dict["physical_cores"] == 8
    assert s_dict["logical_cores"] == 8
    assert s_dict["overall_health"] == "HEALTHY"

    res = MacOsInventoryResponse(
        inventory_id="inv-test-fid-01",
        timestamp_utc="2026-11-17T12:00:00Z",
        summary=summary,
        sections={"hardware": {"cpu": "ok"}},
        partial_data=False,
        scan_proves_safe=False,
        is_mock=True,
    )
    res_dict = res.to_dict()
    assert res_dict["inventory_id"] == "inv-test-fid-01"
    assert res_dict["scan_proves_safe"] is False
    assert res_dict["is_mock"] is True

    res_json = res.to_json()
    assert '"inventory_id": "inv-test-fid-01"' in res_json
    assert '"scan_proves_safe": false' in res_json


def test_inventory_api_summary_computation() -> None:
    """Verify high-level summary generation across mock and platform profiles."""
    api = MacOsInventoryApi()

    summary_mock = api.get_summary(use_mock=True, profile="high_fidelity")
    assert summary_mock.architecture == "arm64"
    assert summary_mock.physical_cores > 0
    assert summary_mock.total_memory_bytes > 0
    assert summary_mock.total_storage_bytes > 0
    assert summary_mock.running_process_count > 0
    assert summary_mock.installed_app_count > 0
    assert 0.0 <= summary_mock.mean_confidence <= 1.0
    assert summary_mock.overall_health in ("HEALTHY", "DEGRADED", "FAILED")


def test_inventory_api_full_aggregation_and_privacy() -> None:
    """Verify full inventory collection aggregates all subsystems and applies privacy filters."""
    api = MacOsInventoryApi()

    req = MacOsInventoryRequest(
        sections=[InventorySection.ALL],
        privacy_level=PrivacyScrubbingLevel.BALANCED,
        use_mock=True,
        include_observations=True,
        include_audit=True,
    )

    inv = api.get_inventory(req)

    assert inv.is_mock is True
    assert inv.scan_proves_safe is False
    assert inv.summary is not None

    # Check that all 8 core inventory sections are aggregated
    assert "identity" in inv.sections
    assert "hardware" in inv.sections
    assert "storage" in inv.sections
    assert "network" in inv.sections
    assert "applications" in inv.sections
    assert "security" in inv.sections
    assert "processes" in inv.sections
    assert "services" in inv.sections

    # Check hardware breakdown
    hw = inv.sections["hardware"]
    assert "cpu" in hw
    assert "memory" in hw
    assert "gpu" in hw
    assert "usb" in hw
    assert "battery" in hw

    # Check observations batch inclusion
    assert inv.observations is not None
    assert "mean_confidence" in inv.observations

    # Check health report inclusion
    assert inv.health is not None
    assert "overall_status" in inv.health

    # Check privacy audit metrics
    assert inv.privacy_audit is not None
    assert inv.privacy_audit["level"] == "BALANCED"
    assert inv.privacy_audit["scan_proves_safe"] is False


def test_inventory_api_section_filtering() -> None:
    """Verify targeted section queries only collect and return requested subsystems."""
    api = MacOsInventoryApi()

    # Query only storage and network
    req = MacOsInventoryRequest(
        sections=[InventorySection.STORAGE, InventorySection.NETWORK],
        privacy_level=PrivacyScrubbingLevel.BALANCED,
        use_mock=True,
    )

    inv = api.get_inventory(req)

    assert len(inv.sections) == 2
    assert "storage" in inv.sections
    assert "network" in inv.sections
    assert "processes" not in inv.sections
    assert "hardware" not in inv.sections

    # Single isolated section helper
    ident = api.get_section(InventorySection.IDENTITY, use_mock=True)
    assert isinstance(ident, dict)
    assert "version_info" in ident


def test_wire_api_request_success() -> None:
    """Verify wire API request handling for inventory summary and get methods."""
    api = MacOsInventoryApi()
    actor = ActorIdentity(
        identity_id="test-operator",
        identity_type=IdentityType.LOCAL_CONSOLE_USER,
        principal_name="operator",
    )

    # 1. Summary method
    req_summary = ApiRequest(
        request_id="req-sum-01",
        api_version="1.0.0",
        method_urn="urn:systemmind:macos:inventory:summary",
        caller_identity=actor,
        params={"use_mock": True},
        is_mutating=False,
    )
    res_sum = api.handle_api_request(req_summary)
    assert res_sum.status == ApiStatus.SUCCESS
    assert res_sum.data["os_version"] is not None
    assert res_sum.error is None

    # 2. Get method
    req_get = ApiRequest(
        request_id="req-get-01",
        api_version="1.0.0",
        method_urn="urn:systemmind:macos:inventory:get",
        caller_identity=actor,
        params={"use_mock": True, "sections": ["IDENTITY", "HARDWARE"]},
        is_mutating=False,
    )
    res_get = api.handle_api_request(req_get)
    assert res_get.status == ApiStatus.SUCCESS
    assert res_get.data["inventory_id"] is not None
    assert "identity" in res_get.data["sections"]
    assert "hardware" in res_get.data["sections"]


def test_wire_api_request_rejection_of_mutating_calls() -> None:
    """Verify non-negotiable invariant that mutating calls to read-only API are rejected."""
    api = MacOsInventoryApi()
    actor = ActorIdentity(
        identity_id="test-operator",
        identity_type=IdentityType.LOCAL_CONSOLE_USER,
        principal_name="operator",
    )

    mut_req = ApiRequest(
        request_id="req-mut-01",
        api_version="1.0.0",
        method_urn="urn:systemmind:macos:inventory:get",
        caller_identity=actor,
        params={"use_mock": True},
        is_mutating=True,  # Prohibited!
    )
    res_mut = api.handle_api_request(mut_req)

    assert res_mut.status == ApiStatus.POLICY_REJECTED
    assert res_mut.data is None
    assert res_mut.error is not None
    assert res_mut.error.code == ErrorCode.E2001_CHARTER_INVARIANT_BREACH
    assert "strictly prohibited" in res_mut.error.message


def test_cli_execution_modes() -> None:
    """Verify developer CLI tool executes across --summary, --section, --mock, and --json flags."""
    assert CLI_PATH.exists()

    # 1. Summary mode
    res1 = subprocess.run(
        [sys.executable, str(CLI_PATH), "--mock", "--summary"],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert res1.returncode == 0
    assert "SYSTEM MIND X — macOS Inventory Executive Summary" in res1.stdout
    assert "Scan != Safe" in res1.stdout

    # 2. Summary JSON
    res2 = subprocess.run(
        [sys.executable, str(CLI_PATH), "--mock", "--summary", "--json"],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert res2.returncode == 0
    data2 = json.loads(res2.stdout)
    assert "os_version" in data2
    assert "architecture" in data2

    # 3. Full inventory table
    res3 = subprocess.run(
        [sys.executable, str(CLI_PATH), "--mock", "--section", "hardware"],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert res3.returncode == 0
    assert "Aggregated Inventory Sections:" in res3.stdout

    # 4. Full inventory JSON
    res4 = subprocess.run(
        [sys.executable, str(CLI_PATH), "--mock", "--json"],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert res4.returncode == 0
    data4 = json.loads(res4.stdout)
    assert data4["scan_proves_safe"] is False
    assert data4["is_mock"] is True
    assert "sections" in data4


def test_packaging_validator_audit() -> None:
    """Verify MacOsInventoryValidator passes with zero issues across all architectural checkpoints."""
    validator = MacOsInventoryValidator()
    result = validator.audit()

    assert result.valid is True, f"Validator failed with issues: {result.issues}"
    assert len(result.issues) == 0
    assert result.models_valid is True
    assert result.api_valid is True
    assert result.cli_valid is True
    assert result.sensors_valid is True
    assert result.safety_valid is True


def test_ast_safety_and_zero_ambient_shell() -> None:
    """Verify AST safety invariant SC-01 (no shell=True, no os.system)."""
    target_files = [
        ROOT_DIR / "src" / "system_mind" / "macos" / "inventory_models.py",
        ROOT_DIR / "src" / "system_mind" / "macos" / "inventory_api.py",
        CLI_PATH,
        ROOT_DIR / "src" / "system_mind" / "packaging" / "macos_inventory.py",
    ]

    for fpath in target_files:
        assert fpath.exists()
        tree = ast.parse(fpath.read_text(encoding="utf-8"), filename=str(fpath))

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # Verify no shell=True
                for kw in node.keywords:
                    if kw.arg == "shell" and isinstance(kw.value, ast.Constant):
                        assert kw.value.value is False, f"Forbidden shell=True at {fpath}:{node.lineno}"

                # Verify no os.system
                if isinstance(node.func, ast.Attribute) and node.func.attr == "system":
                    if isinstance(node.func.value, ast.Name) and node.func.value.id == "os":
                        pytest.fail(f"Forbidden os.system call at {fpath}:{node.lineno}")
