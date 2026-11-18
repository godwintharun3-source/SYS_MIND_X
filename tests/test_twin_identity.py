"""Unit and safety invariant test suite for Day 066 Digital Twin Stable Identifiers."""

from __future__ import annotations

import ast
import tempfile
import uuid
from pathlib import Path

import pytest
from system_mind.packaging.twin_identity import TwinIdentityValidator
from system_mind.twin.identity import (
    NAMESPACE_SYSTEM_MIND,
    DeviceIdentifierManager,
    EntityDomain,
    EntityUrn,
    StableEntityIdGenerator,
    validate_entity_urn,
)


def test_device_id_determinism_and_caching() -> None:
    """Verify that device ID resolution is deterministic and caches correctly."""
    anchor = "mock-hardware-anchor-12345"
    id1 = DeviceIdentifierManager.resolve_device_id(hardware_uuid=anchor, use_cache=False)
    id2 = DeviceIdentifierManager.resolve_device_id(hardware_uuid=anchor, use_cache=False)

    assert id1 == id2
    # Verify it is a valid UUIDv5 derived from NAMESPACE_SYSTEM_MIND
    parsed_uuid = uuid.UUID(id1)
    assert parsed_uuid.version == 5

    # Test disk caching
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = Path(tmpdir)
        cached_id = DeviceIdentifierManager.resolve_device_id(
            hardware_uuid=anchor, use_cache=True, cache_dir=cache_dir
        )
        assert cached_id == id1

        cache_file = cache_dir / DeviceIdentifierManager.CACHE_FILE_NAME
        assert cache_file.is_file()
        assert cache_file.read_text(encoding="utf-8").strip() == id1

        # Reading again with different anchor must still return cached value
        cached_id2 = DeviceIdentifierManager.resolve_device_id(
            hardware_uuid="different-anchor", use_cache=True, cache_dir=cache_dir
        )
        assert cached_id2 == id1

        # Corrupted cache must regenerate valid UUID
        cache_file.write_text("corrupted-not-a-uuid", encoding="utf-8")
        recovered_id = DeviceIdentifierManager.resolve_device_id(
            hardware_uuid=anchor, use_cache=True, cache_dir=cache_dir
        )
        assert recovered_id == id1


def test_canonical_urn_parsing_and_syntax() -> None:
    """Verify URN parsing and syntax validation across domains."""
    valid_urns = [
        "urn:systemmind:host:d5a1b3c9-4e2f-5a8b-9c1d-7e8f0a1b2c3d",
        "urn:systemmind:kernel:darwin:27.3.0:arm64",
        "urn:systemmind:cpu:arm64:a1b2c3d4e5f6:12",
        "urn:systemmind:mem:d5a1b3c9:17179869184",
        "urn:systemmind:vol:d5a1b3c9:4b1e8c228a2d4c2e",
        "urn:systemmind:net:d5a1b3c9:en0",
        "urn:systemmind:app:com.apple.safari",
        "urn:systemmind:proc:d5a1b3c9:1700000000:1234:8f9a2b1c",
        "urn:systemmind:svc:gui.501:com.systemmind.useragent",
        "urn:systemmind:file:d5a1b3c9:vol01:f4e3d2c1b0a9",
        "urn:systemmind:pkg:brew:openssl:3.2.1",
    ]

    for s in valid_urns:
        assert validate_entity_urn(s)
        parsed = EntityUrn.parse(s)
        assert parsed.scan_proves_safe is False
        assert str(parsed) == s

    invalid_urns = [
        "not:a:urn",
        "urn:systemmind",
        "urn:systemmind:",
        "urn:systemmind:unknown_domain:foo",
        "urn:systemmind:host:",
        "urn:othernamespace:host:1234",
    ]

    for inv in invalid_urns:
        assert not validate_entity_urn(inv)
        with pytest.raises(ValueError):
            EntityUrn.parse(inv)


def test_charter_invariant_scan_proves_safe_is_false() -> None:
    """Charter invariant SC-03: scan_proves_safe must be structurally False."""
    urn = EntityUrn(
        domain=EntityDomain.APPLICATION,
        qualifier="com.apple.terminal",
        urn="urn:systemmind:app:com.apple.terminal",
    )
    assert urn.scan_proves_safe is False

    with pytest.raises(ValueError, match="Charter invariant violation"):
        EntityUrn(
            domain=EntityDomain.APPLICATION,
            qualifier="com.apple.terminal",
            urn="urn:systemmind:app:com.apple.terminal",
            scan_proves_safe=True,  # type: ignore[arg-type]
        )


def test_process_temporal_qualification_prevents_pid_recycling() -> None:
    """Verify that process entities avoid PID recycling collisions via start timestamps."""
    device_id = "d5a1b3c9-4e2f-5a8b"
    pid = 4242
    bin_path = "/usr/bin/python3"

    urn_epoch_1 = StableEntityIdGenerator.generate_process_urn(
        device_id=device_id,
        pid=pid,
        start_time_epoch_ms=1700000000000,
        binary_path=bin_path,
    )

    urn_epoch_2 = StableEntityIdGenerator.generate_process_urn(
        device_id=device_id,
        pid=pid,
        start_time_epoch_ms=1700005000000,
        binary_path=bin_path,
    )

    assert urn_epoch_1 != urn_epoch_2
    assert str(urn_epoch_1) != str(urn_epoch_2)
    assert "1700000000000:4242" in str(urn_epoch_1)
    assert "1700005000000:4242" in str(urn_epoch_2)

    # Identical PID and timestamp but different binaries also yield distinct URNs
    urn_bin_diff = StableEntityIdGenerator.generate_process_urn(
        device_id=device_id,
        pid=pid,
        start_time_epoch_ms=1700000000000,
        binary_path="/usr/bin/node",
    )
    assert urn_epoch_1 != urn_bin_diff


def test_privacy_preservation_invariants() -> None:
    """Verify that sensitive user paths and unhashed personal strings are masked in URNs."""
    device_id = "d5a1b3c9-4e2f-5a8b"
    private_path = "/Users/alice_smith/Confidential/ProjectX/keys.pem"

    file_urn = StableEntityIdGenerator.generate_file_urn(
        device_id=device_id,
        volume_id="vol-primary",
        canonical_path=private_path,
    )

    # Raw username or confidential path name must NOT appear in the URN
    urn_str = str(file_urn)
    assert "alice_smith" not in urn_str
    assert "Confidential" not in urn_str
    assert "keys.pem" not in urn_str
    assert urn_str.startswith("urn:systemmind:file:")


def test_all_entity_domain_generators() -> None:
    """Verify all 11 entity domain generators produce valid canonical URNs."""
    dev_id = "d5a1b3c9-4e2f-5a8b"

    generators = [
        StableEntityIdGenerator.generate_host_urn(dev_id),
        StableEntityIdGenerator.generate_kernel_urn("Darwin", "24.0.0", "arm64"),
        StableEntityIdGenerator.generate_cpu_urn("arm64", "Apple M3 Max", 16),
        StableEntityIdGenerator.generate_memory_urn(dev_id, 34359738368),
        StableEntityIdGenerator.generate_storage_volume_urn(dev_id, "disk3s1"),
        StableEntityIdGenerator.generate_network_interface_urn(dev_id, "en0"),
        StableEntityIdGenerator.generate_app_urn("com.systemmind.desktop"),
        StableEntityIdGenerator.generate_process_urn(dev_id, 1, 1000, "/sbin/launchd"),
        StableEntityIdGenerator.generate_service_urn("system", "com.apple.syslogd"),
        StableEntityIdGenerator.generate_file_urn(dev_id, "vol1", "/bin/zsh"),
        StableEntityIdGenerator.generate_package_urn("npm", "react", "18.2.0"),
    ]

    for urn in generators:
        assert isinstance(urn, EntityUrn)
        assert validate_entity_urn(str(urn))
        assert urn.scan_proves_safe is False


def test_twin_identity_packaging_validator() -> None:
    """Verify that TwinIdentityValidator passes all packaging and invariant checks."""
    result = TwinIdentityValidator.audit()
    assert result.valid is True
    assert result.issues == ()
    assert result.python_identity_present is True
    assert result.rust_identity_present is True
    assert result.design_note_present is True
    assert result.tool_present is True
    assert result.ast_safety_valid is True
    assert result.charter_invariants_valid is True
    assert result.domains_count == 11


def test_ast_safety_sc01_zero_ambient_shell() -> None:
    """SC-01 AST check: zero ambient shell authority in twin identity and developer tool."""
    root = Path(__file__).resolve().parent.parent
    files_to_check = [
        root / "src/system_mind/twin/identity.py",
        root / "src/system_mind/packaging/twin_identity.py",
        root / "tools/detect_stable_identity.py",
    ]

    for f in files_to_check:
        assert f.is_file()
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # Verify no os.system
                if isinstance(node.func, ast.Attribute):
                    if isinstance(node.func.value, ast.Name) and node.func.value.id == "os":
                        assert node.func.attr not in ("system", "popen")
                # Verify no shell=True in subprocess
                for kw in node.keywords:
                    if kw.arg == "shell" and isinstance(kw.value, ast.Constant):
                        assert kw.value.value is False
