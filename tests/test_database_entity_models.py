"""Unit, integration, and safety invariant test suite for Day 067 Database Entity Models."""

from __future__ import annotations

import ast
from pathlib import Path
import sqlite3
import pytest

from system_mind.core.types import ComponentOwnership
from system_mind.database.entity_models import (
    ApplicationEntityRecord,
    HardwareCategory,
    HardwareEntityRecord,
    OsKernelEntityRecord,
)
from system_mind.database.entity_repo import EntityRepository
from system_mind.database.migrator import DatabaseMigrator
from system_mind.packaging.database_entities import DatabaseEntitiesValidator
from system_mind.twin.identity import StableEntityIdGenerator


@pytest.fixture
def memory_db_conn() -> sqlite3.Connection:
    """Provides an in-memory SQLite connection with all migrations applied."""
    migrator = DatabaseMigrator(db_path=":memory:")
    conn = migrator._get_connection()
    migrator.apply_all(conn=conn)
    yield conn
    conn.close()


def test_migration_0003_up_and_down_lifecycle() -> None:
    """Verifies that migration 0003 creates expected tables and reverses cleanly."""
    migrator = DatabaseMigrator(db_path=":memory:")
    conn = migrator._get_connection()
    try:
        migrator.apply_all(conn=conn)

        # Verify tables exist
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table';"
            ).fetchall()
        ]
        assert "hardware_entities" in tables
        assert "os_kernel_entities" in tables
        assert "application_entities" in tables

        # Rollback migrations to version 2 (reversing migration 0003 and any later ones)
        rolled_back = migrator.rollback_to(target_version=2, conn=conn)
        assert any(r.version == 3 for r in rolled_back)

        # Verify tables dropped
        tables_after = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table';"
            ).fetchall()
        ]
        assert "hardware_entities" not in tables_after
        assert "os_kernel_entities" not in tables_after
        assert "application_entities" not in tables_after

        # Re-apply
        reapplied = migrator.apply_migration(3, conn=conn)
        assert reapplied.version == 3
    finally:
        conn.close()


def test_hardware_entity_record_validation_and_serialization(memory_db_conn: sqlite3.Connection) -> None:
    """Verifies HardwareEntityRecord validation, serialization, and check constraints."""
    device_id = "d5a1b3c9"
    urn = str(StableEntityIdGenerator.generate_host_urn(device_id))

    record = HardwareEntityRecord(
        entity_urn=urn,
        device_id=device_id,
        category=HardwareCategory.HOST,
        model_name="Apple Silicon Virtual Host",
        vendor="Apple Inc.",
        serial_hash=StableEntityIdGenerator.hash_token("MOCK-SERIAL"),
        attributes={"arch": "arm64", "cores": 8},
        provenance_source="native_sensor",
    )

    # Invariant: scan_proves_safe is strictly False
    assert record.scan_proves_safe is False
    with pytest.raises(ValueError, match="Charter invariant violation"):
        HardwareEntityRecord(
            entity_urn=urn,
            device_id=device_id,
            category=HardwareCategory.HOST,
            model_name="Apple Silicon Host",
            scan_proves_safe=True,  # type: ignore[arg-type]
        )

    # Rejection of invalid URN
    with pytest.raises(ValueError, match="Invalid canonical entity URN"):
        HardwareEntityRecord(
            entity_urn="not-a-urn",
            device_id=device_id,
            category=HardwareCategory.HOST,
            model_name="Apple Silicon Host",
        )

    # Test roundtrip dict serialization
    d = record.to_dict()
    assert d["entity_urn"] == urn
    assert d["category"] == "HOST"
    assert d["scan_proves_safe"] is False
    from_d = HardwareEntityRecord.from_dict(d)
    assert from_d == record

    # Database level check constraint verification (SC-03)
    with pytest.raises(sqlite3.IntegrityError):
        memory_db_conn.execute(
            """
            INSERT INTO hardware_entities (
                entity_urn, device_id, category, model_name, observed_at,
                provenance_source, scan_proves_safe
            ) VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (urn, device_id, "HOST", "Host", "2026-11-18T00:00:00Z", "sensor", 1),
        )


def test_os_kernel_entity_record_validation_and_serialization() -> None:
    """Verifies OsKernelEntityRecord validation and round-trip serialization."""
    device_id = "d5a1b3c9"
    urn = str(StableEntityIdGenerator.generate_kernel_urn("Darwin", "24.0.0", "arm64"))

    record = OsKernelEntityRecord(
        entity_urn=urn,
        device_id=device_id,
        os_family="Darwin",
        product_version="15.0",
        build_version="24A348",
        kernel_release="24.0.0",
        architecture="arm64",
        security_posture={"sip_enabled": True, "gatekeeper_enabled": True},
        provenance_source="native_sysctl",
    )

    assert record.scan_proves_safe is False
    with pytest.raises(ValueError, match="Charter invariant violation"):
        OsKernelEntityRecord(
            entity_urn=urn,
            device_id=device_id,
            os_family="Darwin",
            product_version="15.0",
            build_version="24A348",
            kernel_release="24.0.0",
            architecture="arm64",
            scan_proves_safe=True,  # type: ignore[arg-type]
        )

    d = record.to_dict()
    assert d["os_family"] == "Darwin"
    assert d["security_posture"]["sip_enabled"] is True
    from_d = OsKernelEntityRecord.from_dict(d)
    assert from_d == record


def test_application_entity_record_and_ownership() -> None:
    """Verifies ApplicationEntityRecord and ComponentOwnership classification."""
    device_id = "d5a1b3c9"
    urn = str(StableEntityIdGenerator.generate_app_urn("com.google.chrome"))

    record = ApplicationEntityRecord(
        entity_urn=urn,
        device_id=device_id,
        bundle_id="com.google.Chrome",
        app_name="Google Chrome",
        version="130.0",
        install_path="/Applications/Google Chrome.app",
        ownership=ComponentOwnership.VENDOR_MANAGED,
        code_signature={"signed": True, "notarized": True},
        provenance_source="app_detector",
    )

    assert record.ownership == ComponentOwnership.VENDOR_MANAGED
    assert record.ownership != ComponentOwnership.SYSTEM_MANAGED
    assert record.scan_proves_safe is False

    with pytest.raises(ValueError, match="Charter invariant violation"):
        ApplicationEntityRecord(
            entity_urn=urn,
            device_id=device_id,
            bundle_id="com.google.Chrome",
            app_name="Google Chrome",
            version="130.0",
            install_path="/Applications/Google Chrome.app",
            ownership=ComponentOwnership.VENDOR_MANAGED,
            scan_proves_safe=True,  # type: ignore[arg-type]
        )

    d = record.to_dict()
    assert d["ownership"] == "VENDOR_MANAGED"
    from_d = ApplicationEntityRecord.from_dict(d)
    assert from_d == record


def test_entity_repository_crud_hardware(memory_db_conn: sqlite3.Connection) -> None:
    """Verifies EntityRepository CRUD operations on hardware entities."""
    repo = EntityRepository(memory_db_conn)
    device_id = "d5a1b3c9"
    urn_cpu = str(StableEntityIdGenerator.generate_cpu_urn("arm64", "Apple M1", 8))
    urn_mem = str(StableEntityIdGenerator.generate_memory_urn(device_id, 17179869184))

    cpu = HardwareEntityRecord(
        entity_urn=urn_cpu,
        device_id=device_id,
        category=HardwareCategory.CPU,
        model_name="Apple M1",
        vendor="Apple Inc.",
        attributes={"cores": 8},
    )
    mem = HardwareEntityRecord(
        entity_urn=urn_mem,
        device_id=device_id,
        category=HardwareCategory.MEMORY,
        model_name="Unified Memory",
        attributes={"bytes": 17179869184},
    )

    repo.save_hardware_entity(cpu)
    repo.save_hardware_entity(mem)

    # Fetch
    fetched_cpu = repo.get_hardware_entity(urn_cpu)
    assert fetched_cpu is not None
    assert fetched_cpu.model_name == "Apple M1"
    assert fetched_cpu.category == HardwareCategory.CPU
    assert fetched_cpu.scan_proves_safe is False

    # List with filtering
    all_hw = repo.list_hardware_entities(device_id=device_id)
    assert len(all_hw) == 2

    cpu_only = repo.list_hardware_entities(category=HardwareCategory.CPU)
    assert len(cpu_only) == 1
    assert cpu_only[0].entity_urn == urn_cpu

    # Delete
    deleted = repo.delete_hardware_entity(urn_cpu)
    assert deleted is True
    assert repo.get_hardware_entity(urn_cpu) is None
    assert len(repo.list_hardware_entities(device_id=device_id)) == 1


def test_entity_repository_crud_os_kernel(memory_db_conn: sqlite3.Connection) -> None:
    """Verifies EntityRepository CRUD operations on OS kernel entities."""
    repo = EntityRepository(memory_db_conn)
    device_id = "d5a1b3c9"
    urn = str(StableEntityIdGenerator.generate_kernel_urn("Darwin", "24.0.0", "arm64"))

    kernel = OsKernelEntityRecord(
        entity_urn=urn,
        device_id=device_id,
        os_family="Darwin",
        product_version="15.0",
        build_version="24A348",
        kernel_release="24.0.0",
        architecture="arm64",
        security_posture={"sip_enabled": True},
    )

    repo.save_os_kernel_entity(kernel)
    fetched = repo.get_os_kernel_entity(urn)
    assert fetched is not None
    assert fetched.product_version == "15.0"
    assert fetched.security_posture["sip_enabled"] is True

    kernels = repo.list_os_kernel_entities(device_id=device_id)
    assert len(kernels) == 1
    assert kernels[0].entity_urn == urn

    assert repo.delete_os_kernel_entity(urn) is True
    assert repo.get_os_kernel_entity(urn) is None


def test_entity_repository_crud_application(memory_db_conn: sqlite3.Connection) -> None:
    """Verifies EntityRepository CRUD and component ownership isolation on applications."""
    repo = EntityRepository(memory_db_conn)
    device_id = "d5a1b3c9"

    app_sys = ApplicationEntityRecord(
        entity_urn=str(StableEntityIdGenerator.generate_app_urn("com.apple.finder")),
        device_id=device_id,
        bundle_id="com.apple.finder",
        app_name="Finder",
        version="15.0",
        install_path="/System/Library/CoreServices/Finder.app",
        ownership=ComponentOwnership.SYSTEM_MANAGED,
    )

    app_user = ApplicationEntityRecord(
        entity_urn=str(StableEntityIdGenerator.generate_app_urn("com.user.localapp")),
        device_id=device_id,
        bundle_id="com.user.localapp",
        app_name="Local App",
        version="1.0.0",
        install_path="/Users/user/Applications/LocalApp.app",
        ownership=ComponentOwnership.USER_MANAGED,
    )

    repo.save_application_entity(app_sys)
    repo.save_application_entity(app_user)

    # Filter by USER_MANAGED
    user_apps = repo.list_application_entities(ownership=ComponentOwnership.USER_MANAGED)
    assert len(user_apps) == 1
    assert user_apps[0].bundle_id == "com.user.localapp"
    assert user_apps[0].ownership == ComponentOwnership.USER_MANAGED

    # Filter by SYSTEM_MANAGED
    sys_apps = repo.list_application_entities(ownership=ComponentOwnership.SYSTEM_MANAGED)
    assert len(sys_apps) == 1
    assert sys_apps[0].bundle_id == "com.apple.finder"

    assert repo.delete_application_entity(app_user.entity_urn) is True
    assert repo.get_application_entity(app_user.entity_urn) is None


def test_entity_repository_counts(memory_db_conn: sqlite3.Connection) -> None:
    """Verifies aggregate entity counts across categories."""
    repo = EntityRepository(memory_db_conn)
    device_id = "d5a1b3c9"

    counts_empty = repo.count_entities()
    assert counts_empty["total"] == 0

    # Add 1 hw, 1 os, 1 app
    repo.save_hardware_entity(
        HardwareEntityRecord(
            entity_urn=str(StableEntityIdGenerator.generate_host_urn(device_id)),
            device_id=device_id,
            category=HardwareCategory.HOST,
            model_name="Host 1",
        )
    )
    repo.save_os_kernel_entity(
        OsKernelEntityRecord(
            entity_urn=str(StableEntityIdGenerator.generate_kernel_urn("Darwin", "24.0.0", "arm64")),
            device_id=device_id,
            os_family="Darwin",
            product_version="15.0",
            build_version="24A348",
            kernel_release="24.0.0",
            architecture="arm64",
        )
    )
    repo.save_application_entity(
        ApplicationEntityRecord(
            entity_urn=str(StableEntityIdGenerator.generate_app_urn("com.example.app")),
            device_id=device_id,
            bundle_id="com.example.app",
            app_name="Example",
            version="1.0",
            install_path="/Applications/Example.app",
            ownership=ComponentOwnership.VENDOR_MANAGED,
        )
    )

    counts = repo.count_entities(device_id=device_id)
    assert counts["hardware"] == 1
    assert counts["os_kernel"] == 1
    assert counts["applications"] == 1
    assert counts["total"] == 3


def test_database_entities_packaging_validator() -> None:
    """Verifies that DatabaseEntitiesValidator audits cleanly."""
    result = DatabaseEntitiesValidator.audit()
    assert result.valid is True
    assert result.issues == ()
    assert result.migration_present is True
    assert result.models_present is True
    assert result.repository_present is True
    assert result.design_note_present is True
    assert result.tool_present is True
    assert result.ast_safety_valid is True
    assert result.charter_invariants_valid is True
    assert result.lifecycle_roundtrip_valid is True


def test_ast_safety_sc01_zero_ambient_shell() -> None:
    """SC-01 AST check: zero ambient shell authority across all database entity files."""
    root = Path(__file__).resolve().parent.parent
    files_to_check = [
        root / "src/system_mind/database/entity_models.py",
        root / "src/system_mind/database/entity_repo.py",
        root / "src/system_mind/packaging/database_entities.py",
        root / "tools/detect_database_entities.py",
    ]

    for f in files_to_check:
        assert f.is_file()
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    if isinstance(node.func.value, ast.Name) and node.func.value.id == "os":
                        assert node.func.attr not in ("system", "popen")
                for kw in node.keywords:
                    if kw.arg == "shell" and isinstance(kw.value, ast.Constant):
                        assert kw.value.value is False
