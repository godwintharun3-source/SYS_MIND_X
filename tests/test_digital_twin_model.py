"""Unit and contract tests for the Digital Twin entity and relationship model."""

import pytest

from system_mind.core.types import ComponentOwnership
from system_mind.twin import (
    DigitalTwinGraph,
    TwinEntity,
    TwinEntityType,
    TwinEntityValidator,
    TwinRelationship,
    TwinRelationType,
)


def test_twin_entity_and_relation_enums_completeness():
    """Verify that all 10 entity types and 9 relationship types are cataloged."""
    assert len(TwinEntityType) == 10
    assert len(TwinRelationType) == 9

    expected_entities = {
        "HOST",
        "OS_KERNEL",
        "HARDWARE_DEVICE",
        "FILESYSTEM_NODE",
        "PACKAGE_DEPENDENCY",
        "APPLICATION",
        "PROCESS",
        "NETWORK_SOCKET",
        "SECURITY_POSTURE",
        "CONFIGURATION_SETTING",
    }
    assert {e.value for e in TwinEntityType} == expected_entities

    expected_relations = {
        "CONTAINS",
        "SPAWNED_BY",
        "DEPENDS_ON",
        "OWNS",
        "ENFORCES_POLICY",
        "COMMUNICATES_VIA",
        "WRITES_TO",
        "READS_FROM",
        "AFFECTS",
    }
    assert {r.value for r in TwinRelationType} == expected_relations


def test_entity_validation_success_and_failures():
    """Verify entity validation rules, mandatory ownership, provenance, and privacy safeguards."""
    # 1. Valid entity
    valid_host = TwinEntity(
        entity_id="urn:twin:host:main-node",
        entity_type=TwinEntityType.HOST,
        ownership=ComponentOwnership.SYSTEM_MANAGED,
        attributes={"hostname": "dev-m1", "cores": 8},
        created_at="2026-11-15T21:00:00Z",
        provenance_source="ENG-01:telemetry",
    )
    assert len(TwinEntityValidator.validate_entity(valid_host)) == 0

    # 2. Missing entity ID
    invalid_id = TwinEntity(
        entity_id="",
        entity_type=TwinEntityType.HOST,
        ownership=ComponentOwnership.SYSTEM_MANAGED,
        provenance_source="ENG-01:telemetry",
    )
    violations = TwinEntityValidator.validate_entity(invalid_id)
    assert any("Entity ID cannot be empty" in v for v in violations)

    # 3. Missing provenance source (Invariant 3)
    no_provenance = TwinEntity(
        entity_id="urn:twin:host:test",
        entity_type=TwinEntityType.HOST,
        ownership=ComponentOwnership.SYSTEM_MANAGED,
        provenance_source="",
    )
    v_prov = TwinEntityValidator.validate_entity(no_provenance)
    assert any("Provenance source cannot be empty" in v for v in v_prov)

    # 4. Privacy violation with secret key (Invariant 4)
    sensitive_entity = TwinEntity(
        entity_id="urn:twin:config:env",
        entity_type=TwinEntityType.CONFIGURATION_SETTING,
        ownership=ComponentOwnership.USER_MANAGED,
        attributes={"service": "github", "api_token_secret": "ghp_123456789"},
        provenance_source="ENG-03:app_context",
    )
    v_privacy = TwinEntityValidator.validate_entity(sensitive_entity)
    assert any("Privacy Violation" in v for v in v_privacy)


def test_relationship_validation():
    """Verify relationship schema and confidence constraints."""
    valid_rel = TwinRelationship(
        relation_id="rel-001",
        source_id="urn:twin:host:main",
        target_id="urn:twin:proc:1",
        relation_type=TwinRelationType.CONTAINS,
        confidence=1.0,
    )
    assert len(TwinEntityValidator.validate_relationship(valid_rel)) == 0

    invalid_conf = TwinRelationship(
        relation_id="rel-002",
        source_id="urn:twin:host:main",
        target_id="urn:twin:proc:1",
        relation_type=TwinRelationType.CONTAINS,
        confidence=1.5,
    )
    v_conf = TwinEntityValidator.validate_relationship(invalid_conf)
    assert any("Confidence score" in v for v in v_conf)


def test_graph_add_get_update_remove_entity():
    """Verify entity CRUD operations and attribute updates in the graph."""
    graph = DigitalTwinGraph()

    entity = TwinEntity(
        entity_id="urn:twin:app:chrome",
        entity_type=TwinEntityType.APPLICATION,
        ownership=ComponentOwnership.USER_MANAGED,
        attributes={"app_name": "Google Chrome", "version": "120.0"},
        provenance_source="ENG-03:app_context",
    )

    graph.add_entity(entity)
    assert graph.entity_count == 1
    assert graph.get_entity("urn:twin:app:chrome") == entity

    # Update entity attributes
    updated = graph.update_entity_attributes(
        "urn:twin:app:chrome",
        {"version": "121.0", "active_tab_count": 5},
        updated_at="2026-11-15T21:05:00Z",
    )
    assert updated.attributes["version"] == "121.0"
    assert updated.attributes["active_tab_count"] == 5
    assert updated.attributes["app_name"] == "Google Chrome"

    # Remove entity
    removed = graph.remove_entity("urn:twin:app:chrome")
    assert removed is True
    assert graph.entity_count == 0
    assert graph.get_entity("urn:twin:app:chrome") is None


def test_graph_referential_integrity_and_cascade_removal():
    """Verify referential integrity enforcement and cascading deletion of relationships."""
    graph = DigitalTwinGraph()

    host = TwinEntity(
        entity_id="urn:twin:host:main",
        entity_type=TwinEntityType.HOST,
        ownership=ComponentOwnership.SYSTEM_MANAGED,
        provenance_source="ENG-01:telemetry",
    )
    proc = TwinEntity(
        entity_id="urn:twin:proc:1",
        entity_type=TwinEntityType.PROCESS,
        ownership=ComponentOwnership.SYSTEM_MANAGED,
        provenance_source="ENG-01:telemetry",
    )

    graph.add_entity(host)
    graph.add_entity(proc)

    # 1. Invalid source/target raises KeyError
    with pytest.raises(KeyError) as exc_source:
        graph.add_relationship(
            TwinRelationship(
                relation_id="rel-bad-source",
                source_id="urn:twin:host:nonexistent",
                target_id="urn:twin:proc:1",
                relation_type=TwinRelationType.CONTAINS,
            )
        )
    assert "Source entity" in str(exc_source.value)

    with pytest.raises(KeyError) as exc_target:
        graph.add_relationship(
            TwinRelationship(
                relation_id="rel-bad-target",
                source_id="urn:twin:host:main",
                target_id="urn:twin:proc:999",
                relation_type=TwinRelationType.CONTAINS,
            )
        )
    assert "Target entity" in str(exc_target.value)

    # 2. Valid relationship
    rel = TwinRelationship(
        relation_id="rel-host-proc",
        source_id="urn:twin:host:main",
        target_id="urn:twin:proc:1",
        relation_type=TwinRelationType.CONTAINS,
    )
    graph.add_relationship(rel)
    assert graph.relationship_count == 1

    # 3. Cascading deletion: removing proc cascades to remove rel-host-proc
    graph.remove_entity("urn:twin:proc:1")
    assert graph.entity_count == 1
    assert graph.relationship_count == 0
    assert graph.get_relationship("rel-host-proc") is None


def test_graph_indexing_and_filtering():
    """Verify entity lookups by type, ownership, and relationship adjacency filtering."""
    graph = DigitalTwinGraph()

    sys_file = TwinEntity(
        entity_id="urn:twin:file:/etc/hosts",
        entity_type=TwinEntityType.FILESYSTEM_NODE,
        ownership=ComponentOwnership.SYSTEM_MANAGED,
        provenance_source="ENG-09:fsevents",
    )
    user_file = TwinEntity(
        entity_id="urn:twin:file:/Users/dev/project/main.py",
        entity_type=TwinEntityType.FILESYSTEM_NODE,
        ownership=ComponentOwnership.USER_MANAGED,
        provenance_source="ENG-09:fsevents",
    )
    app = TwinEntity(
        entity_id="urn:twin:app:code",
        entity_type=TwinEntityType.APPLICATION,
        ownership=ComponentOwnership.USER_MANAGED,
        provenance_source="ENG-03:app_context",
    )

    graph.add_entity(sys_file)
    graph.add_entity(user_file)
    graph.add_entity(app)

    # Filter by type
    files = graph.get_entities_by_type(TwinEntityType.FILESYSTEM_NODE)
    assert len(files) == 2

    apps = graph.get_entities_by_type(TwinEntityType.APPLICATION)
    assert len(apps) == 1
    assert apps[0].entity_id == "urn:twin:app:code"

    # Filter by component ownership
    sys_entities = graph.get_entities_by_ownership(ComponentOwnership.SYSTEM_MANAGED)
    assert len(sys_entities) == 1
    assert sys_entities[0].entity_id == "urn:twin:file:/etc/hosts"

    user_entities = graph.get_entities_by_ownership(ComponentOwnership.USER_MANAGED)
    assert len(user_entities) == 2


def test_graph_process_hierarchy_traversal():
    """Verify ascending process ancestry traversal via SPAWNED_BY edges."""
    graph = DigitalTwinGraph()

    p_init = TwinEntity(
        entity_id="urn:twin:proc:1",
        entity_type=TwinEntityType.PROCESS,
        ownership=ComponentOwnership.SYSTEM_MANAGED,
        attributes={"command": "launchd"},
        provenance_source="ENG-01:telemetry",
    )
    p_shell = TwinEntity(
        entity_id="urn:twin:proc:100",
        entity_type=TwinEntityType.PROCESS,
        ownership=ComponentOwnership.USER_MANAGED,
        attributes={"command": "zsh"},
        provenance_source="ENG-01:telemetry",
    )
    p_worker = TwinEntity(
        entity_id="urn:twin:proc:200",
        entity_type=TwinEntityType.PROCESS,
        ownership=ComponentOwnership.USER_MANAGED,
        attributes={"command": "python3 worker.py"},
        provenance_source="ENG-01:telemetry",
    )

    graph.add_entity(p_init)
    graph.add_entity(p_shell)
    graph.add_entity(p_worker)

    # Worker SPAWNED_BY Shell
    graph.add_relationship(
        TwinRelationship(
            relation_id="rel-spawn-worker",
            source_id="urn:twin:proc:200",
            target_id="urn:twin:proc:100",
            relation_type=TwinRelationType.SPAWNED_BY,
        )
    )
    # Shell SPAWNED_BY Init
    graph.add_relationship(
        TwinRelationship(
            relation_id="rel-spawn-shell",
            source_id="urn:twin:proc:100",
            target_id="urn:twin:proc:1",
            relation_type=TwinRelationType.SPAWNED_BY,
        )
    )

    ancestors = graph.get_process_ancestors("urn:twin:proc:200")
    assert len(ancestors) == 2
    assert ancestors[0].entity_id == "urn:twin:proc:100"
    assert ancestors[1].entity_id == "urn:twin:proc:1"


def test_graph_dependency_traversal():
    """Verify outward functional dependency traversal via DEPENDS_ON edges."""
    graph = DigitalTwinGraph()

    app = TwinEntity(
        entity_id="urn:twin:app:editor",
        entity_type=TwinEntityType.APPLICATION,
        ownership=ComponentOwnership.USER_MANAGED,
        provenance_source="ENG-03:app_context",
    )
    pkg_runtime = TwinEntity(
        entity_id="urn:twin:pkg:python3",
        entity_type=TwinEntityType.PACKAGE_DEPENDENCY,
        ownership=ComponentOwnership.SYSTEM_MANAGED,
        provenance_source="ENG-12:developer_toolchain",
    )
    pkg_lib = TwinEntity(
        entity_id="urn:twin:pkg:openssl",
        entity_type=TwinEntityType.PACKAGE_DEPENDENCY,
        ownership=ComponentOwnership.SYSTEM_MANAGED,
        provenance_source="ENG-12:developer_toolchain",
    )

    graph.add_entity(app)
    graph.add_entity(pkg_runtime)
    graph.add_entity(pkg_lib)

    # App DEPENDS_ON python3
    graph.add_relationship(
        TwinRelationship(
            relation_id="rel-dep-1",
            source_id="urn:twin:app:editor",
            target_id="urn:twin:pkg:python3",
            relation_type=TwinRelationType.DEPENDS_ON,
        )
    )
    # python3 DEPENDS_ON openssl
    graph.add_relationship(
        TwinRelationship(
            relation_id="rel-dep-2",
            source_id="urn:twin:pkg:python3",
            target_id="urn:twin:pkg:openssl",
            relation_type=TwinRelationType.DEPENDS_ON,
        )
    )

    deps = graph.get_dependencies("urn:twin:app:editor")
    assert len(deps) == 2
    dep_ids = {d.entity_id for d in deps}
    assert dep_ids == {"urn:twin:pkg:python3", "urn:twin:pkg:openssl"}


def test_graph_validate_integrity():
    """Verify graph integrity validation catches dangling or corrupt relationships."""
    graph = DigitalTwinGraph()

    host = TwinEntity(
        entity_id="urn:twin:host:main",
        entity_type=TwinEntityType.HOST,
        ownership=ComponentOwnership.SYSTEM_MANAGED,
        provenance_source="ENG-01:telemetry",
    )
    graph.add_entity(host)

    is_valid, violations = graph.validate_integrity()
    assert is_valid is True
    assert len(violations) == 0

    # Manually inject a dangling relationship to test error detection
    corrupt_rel = TwinRelationship(
        relation_id="rel-corrupt",
        source_id="urn:twin:host:main",
        target_id="urn:twin:host:ghost",
        relation_type=TwinRelationType.CONTAINS,
    )
    graph._relationships[corrupt_rel.relation_id] = corrupt_rel

    is_valid_after, violations_after = graph.validate_integrity()
    assert is_valid_after is False
    assert any("Dangling Relationship" in v for v in violations_after)
