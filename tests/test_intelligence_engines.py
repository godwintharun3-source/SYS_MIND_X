"""Unit and contract tests for the fourteen SYSTEM MIND X intelligence engines."""

import pytest

from system_mind.engines.contracts import (
    EngineFunctionalRequirement,
    EngineId,
    EngineMaturityTier,
    EngineRegistry,
    EngineSpecification,
)
from system_mind.engines.validator import (
    EngineContractValidator,
    EngineValidationReport,
)


def test_engine_registry_contains_all_fourteen_engines():
    """Verify that all fourteen intelligence engines are formally registered."""
    engines = EngineRegistry.get_all()
    assert len(engines) == 14

    registered_ids = {spec.engine_id for spec in engines}
    for expected_id in EngineId:
        assert expected_id in registered_ids, f"Engine {expected_id} missing from registry"

    for spec in engines:
        assert spec.name.strip(), f"Engine {spec.engine_id} has empty name"
        assert spec.phase.strip(), f"Engine {spec.engine_id} has empty phase"
        assert spec.summary.strip(), f"Engine {spec.engine_id} has empty summary"
        assert spec.primary_safety_boundary.strip(), f"Engine {spec.engine_id} has empty safety boundary"
        assert len(spec.input_schema_types) > 0, f"Engine {spec.engine_id} has no input schemas"
        assert len(spec.output_schema_types) > 0, f"Engine {spec.engine_id} has no output schemas"


def test_all_engine_functional_requirements_complete():
    """Verify that every engine defines complete functional requirements with inputs, outputs, errors, and safety."""
    engines = EngineRegistry.get_all()
    total_requirements = 0

    for spec in engines:
        assert len(spec.functional_requirements) > 0, f"Engine {spec.engine_id} has no requirements"
        for req in spec.functional_requirements:
            total_requirements += 1
            assert req.req_id.startswith("FR-ENG"), f"Invalid requirement ID: {req.req_id}"
            assert req.title.strip(), f"Requirement {req.req_id} has empty title"
            assert req.description.strip(), f"Requirement {req.req_id} has empty description"
            assert req.input_contract.strip(), f"Requirement {req.req_id} has empty input contract"
            assert req.output_contract.strip(), f"Requirement {req.req_id} has empty output contract"
            assert len(req.error_states) > 0, f"Requirement {req.req_id} defines no error states"
            assert len(req.permission_requirements) > 0, f"Requirement {req.req_id} defines no permission requirements"
            assert req.unsupported_platform_behavior.strip(), f"Requirement {req.req_id} has no platform fallback"
            assert len(req.safety_constraints) > 0, f"Requirement {req.req_id} defines no safety constraints"

    assert total_requirements >= 15


def test_engine_maturity_tiers_distribution():
    """Verify that all four maturity tiers are represented across the fourteen engines."""
    for tier in EngineMaturityTier:
        filtered = EngineRegistry.filter_by_maturity_tier(tier)
        assert len(filtered) > 0, f"Maturity tier {tier} has no registered engines"

    core_engines = EngineRegistry.filter_by_maturity_tier(EngineMaturityTier.CORE_FOUNDATION)
    assert len(core_engines) == 2  # ENG-01 (Twin) and ENG-03 (Sensors)


def test_engine_registry_lookup_by_string_and_enum():
    """Verify engine lookups using EngineId enum and raw string identifiers."""
    by_enum = EngineRegistry.get(EngineId.ENG_01_TEMPORAL_DIGITAL_TWIN)
    by_str = EngineRegistry.get("ENG-01")
    assert by_enum == by_str
    assert by_str.engine_id == EngineId.ENG_01_TEMPORAL_DIGITAL_TWIN
    assert by_str.name == "Persistent Temporal Digital Twin"

    with pytest.raises(KeyError):
        EngineRegistry.get("ENG-999")


def test_engine_contract_validator_audit_success():
    """Verify that EngineContractValidator passes cleanly with 14 engines and 0 violations."""
    report = EngineContractValidator.validate_all_engines()
    assert report.is_valid is True
    assert report.total_engines_checked == 14
    assert report.pipeline_connections_valid is True
    assert len(report.violations) == 0


def test_pipeline_transitions_enforce_topology():
    """Verify that only authorized inter-engine dataflow transitions are permitted."""
    # Permitted transitions
    assert EngineContractValidator.is_pipeline_transition_permitted(
        EngineId.ENG_03_SENSOR_AWARENESS, EngineId.ENG_01_TEMPORAL_DIGITAL_TWIN
    ) is True
    assert EngineContractValidator.is_pipeline_transition_permitted(
        EngineId.ENG_04_GOVERNANCE_POLICY, EngineId.ENG_10_VERIFIED_EXECUTION_BROKER
    ) is True
    assert EngineContractValidator.is_pipeline_transition_permitted(
        EngineId.ENG_10_VERIFIED_EXECUTION_BROKER, EngineId.ENG_07_CONTROLLED_SANDBOXING
    ) is True

    # Forbidden direct transitions (bypassing governance / topology)
    assert EngineContractValidator.is_pipeline_transition_permitted(
        EngineId.ENG_05_AUTONOMOUS_MAINTENANCE, EngineId.ENG_10_VERIFIED_EXECUTION_BROKER
    ) is False  # Must route through ENG-04 Governance Policy
    assert EngineContractValidator.is_pipeline_transition_permitted(
        EngineId.ENG_01_TEMPORAL_DIGITAL_TWIN, EngineId.ENG_07_CONTROLLED_SANDBOXING
    ) is False
