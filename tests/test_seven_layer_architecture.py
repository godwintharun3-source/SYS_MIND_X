"""Unit and contract tests for the seven-layer system architecture and component boundaries."""

import pytest

from system_mind.architecture.layers import (
    ArchitectureBoundaryEnforcer,
    ArchitectureLayerId,
    DataflowDirection,
    LayerSpecification,
    SevenLayerArchitectureRegistry,
)


def test_seven_layer_registry_completeness():
    """Verify that all seven architectural layers are registered in sequential order."""
    layers = SevenLayerArchitectureRegistry.get_all()
    assert len(layers) == 7

    for idx, layer in enumerate(layers, start=1):
        assert layer.layer_number == idx, f"Expected layer number {idx}, got {layer.layer_number}"
        assert layer.name.strip(), f"Layer {layer.layer_id} has empty name"
        assert layer.description.strip(), f"Layer {layer.layer_id} has empty description"
        assert len(layer.primary_engines) > 0, f"Layer {layer.layer_id} defines no primary engines"
        assert layer.privilege_envelope.strip(), f"Layer {layer.layer_id} has empty privilege envelope"
        assert len(layer.boundary_invariants) > 0, f"Layer {layer.layer_id} defines no boundary invariants"


def test_layer_registry_lookups():
    """Verify layer retrieval by enum, string name, and layer number."""
    by_enum = SevenLayerArchitectureRegistry.get(ArchitectureLayerId.L1_PRESENTATION)
    by_str = SevenLayerArchitectureRegistry.get("L1_PRESENTATION")
    by_num = SevenLayerArchitectureRegistry.get_by_number(1)

    assert by_enum == by_str == by_num
    assert by_num.layer_id == ArchitectureLayerId.L1_PRESENTATION

    l7 = SevenLayerArchitectureRegistry.get_by_number(7)
    assert l7.layer_id == ArchitectureLayerId.L7_KERNEL_HARDWARE

    with pytest.raises(KeyError):
        SevenLayerArchitectureRegistry.get("L99_UNKNOWN")

    with pytest.raises(KeyError):
        SevenLayerArchitectureRegistry.get_by_number(8)


def test_valid_downward_execution_transitions():
    """Verify that authorized step-by-step downward execution transitions pass boundary validation."""
    valid_downward_steps = [
        (ArchitectureLayerId.L1_PRESENTATION, ArchitectureLayerId.L2_COGNITIVE_PLANE),
        (ArchitectureLayerId.L2_COGNITIVE_PLANE, ArchitectureLayerId.L3_POLICY_ENGINE),
        (ArchitectureLayerId.L3_POLICY_ENGINE, ArchitectureLayerId.L5_EXECUTION_BROKER),
        (ArchitectureLayerId.L5_EXECUTION_BROKER, ArchitectureLayerId.L6_PLATFORM_ADAPTERS),
        (ArchitectureLayerId.L6_PLATFORM_ADAPTERS, ArchitectureLayerId.L7_KERNEL_HARDWARE),
    ]

    for src, dst in valid_downward_steps:
        is_valid, err = ArchitectureBoundaryEnforcer.validate_transition(
            source=src, target=dst, direction=DataflowDirection.DOWNWARD_EXECUTION
        )
        assert is_valid is True, f"Valid step {src.value} -> {dst.value} failed: {err}"
        assert err is None


def test_forbidden_downward_execution_bypasses():
    """Verify that unauthorized layer bypasses are blocked by the architecture enforcer."""
    forbidden_bypasses = [
        # Layer 2 AI Planner bypassing Layer 3 Policy Engine directly to Broker
        (ArchitectureLayerId.L2_COGNITIVE_PLANE, ArchitectureLayerId.L5_EXECUTION_BROKER),
        # Layer 2 AI Planner bypassing Policy and Broker to Adapters
        (ArchitectureLayerId.L2_COGNITIVE_PLANE, ArchitectureLayerId.L6_PLATFORM_ADAPTERS),
        # Layer 2 AI Planner directly invoking Kernel
        (ArchitectureLayerId.L2_COGNITIVE_PLANE, ArchitectureLayerId.L7_KERNEL_HARDWARE),
        # Layer 1 UI directly invoking Broker
        (ArchitectureLayerId.L1_PRESENTATION, ArchitectureLayerId.L5_EXECUTION_BROKER),
        # Inverted downward execution (moving upward)
        (ArchitectureLayerId.L5_EXECUTION_BROKER, ArchitectureLayerId.L2_COGNITIVE_PLANE),
    ]

    for src, dst in forbidden_bypasses:
        is_valid, err = ArchitectureBoundaryEnforcer.validate_transition(
            source=src, target=dst, direction=DataflowDirection.DOWNWARD_EXECUTION
        )
        assert is_valid is False, f"Forbidden bypass {src.value} -> {dst.value} was unexpectedly permitted"
        assert err is not None
        assert "Architecture" in err or "Bypass Blocked" in err


def test_valid_upward_observation_flow():
    """Verify that telemetry and event observations flow upward to the digital twin and cognitive plane."""
    # Observations targeting Layer 4 (Digital Twin)
    valid_upward = [
        (ArchitectureLayerId.L7_KERNEL_HARDWARE, ArchitectureLayerId.L4_DIGITAL_TWIN),
        (ArchitectureLayerId.L6_PLATFORM_ADAPTERS, ArchitectureLayerId.L4_DIGITAL_TWIN),
    ]

    for src, dst in valid_upward:
        is_valid, err = ArchitectureBoundaryEnforcer.validate_transition(
            source=src, target=dst, direction=DataflowDirection.UPWARD_OBSERVATION
        )
        assert is_valid is True, f"Upward observation {src.value} -> {dst.value} failed: {err}"


def test_lateral_state_queries():
    """Verify that lateral state queries are authorized against Layer 4 and blocked elsewhere."""
    # Queries targeting Layer 4 (Digital Twin)
    for caller in [
        ArchitectureLayerId.L1_PRESENTATION,
        ArchitectureLayerId.L2_COGNITIVE_PLANE,
        ArchitectureLayerId.L3_POLICY_ENGINE,
        ArchitectureLayerId.L5_EXECUTION_BROKER,
    ]:
        is_valid, err = ArchitectureBoundaryEnforcer.validate_transition(
            source=caller, target=ArchitectureLayerId.L4_DIGITAL_TWIN, direction=DataflowDirection.LATERAL_QUERY
        )
        assert is_valid is True, f"Lateral query from {caller.value} to Digital Twin failed: {err}"

    # Lateral query targeting non-Twin layer (e.g. Layer 2 calling Layer 5 laterally) is blocked
    is_valid_bad, err_bad = ArchitectureBoundaryEnforcer.validate_transition(
        source=ArchitectureLayerId.L2_COGNITIVE_PLANE,
        target=ArchitectureLayerId.L5_EXECUTION_BROKER,
        direction=DataflowDirection.LATERAL_QUERY,
    )
    assert is_valid_bad is False
    assert err_bad is not None
    assert "Lateral queries are permitted only against Layer 4" in err_bad
