"""Seven-layer system architecture models, component boundaries, and transition enforcement."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple


class ArchitectureLayerId(str, Enum):
    """The seven formal architectural layers of SYSTEM MIND X."""

    L1_PRESENTATION = "L1_PRESENTATION"
    L2_COGNITIVE_PLANE = "L2_COGNITIVE_PLANE"
    L3_POLICY_ENGINE = "L3_POLICY_ENGINE"
    L4_DIGITAL_TWIN = "L4_DIGITAL_TWIN"
    L5_EXECUTION_BROKER = "L5_EXECUTION_BROKER"
    L6_PLATFORM_ADAPTERS = "L6_PLATFORM_ADAPTERS"
    L7_KERNEL_HARDWARE = "L7_KERNEL_HARDWARE"


class DataflowDirection(str, Enum):
    """Directionality of inter-layer communication."""

    DOWNWARD_EXECUTION = "DOWNWARD_EXECUTION"
    UPWARD_OBSERVATION = "UPWARD_OBSERVATION"
    LATERAL_QUERY = "LATERAL_QUERY"


@dataclass(frozen=True)
class LayerSpecification:
    """Formal specification of an architectural layer and its boundary rules."""

    layer_id: ArchitectureLayerId
    name: str
    layer_number: int
    description: str
    primary_engines: List[str]
    allowed_upstream_callers: Set[ArchitectureLayerId]
    allowed_downstream_targets: Set[ArchitectureLayerId]
    privilege_envelope: str
    boundary_invariants: List[str]


class SevenLayerArchitectureRegistry:
    """Central registry of verified specifications for all seven architectural layers."""

    _LAYERS: Dict[ArchitectureLayerId, LayerSpecification] = {
        ArchitectureLayerId.L1_PRESENTATION: LayerSpecification(
            layer_id=ArchitectureLayerId.L1_PRESENTATION,
            name="Presentation & Interface Layer",
            layer_number=1,
            description="User-facing interfaces, caretaker reporting dashboards, CLI tooling, and consent dialogues.",
            primary_engines=["UI Viewers", "CLI Harness", "Dashboard Consumer"],
            allowed_upstream_callers=set(),  # Top of the stack
            allowed_downstream_targets={
                ArchitectureLayerId.L2_COGNITIVE_PLANE,
                ArchitectureLayerId.L4_DIGITAL_TWIN,
            },
            privilege_envelope="Unprivileged user space",
            boundary_invariants=[
                "Cannot directly invoke Layer 3, Layer 5, Layer 6, or Layer 7.",
                "All user intent passes through Layer 2 for structural decomposition.",
            ],
        ),
        ArchitectureLayerId.L2_COGNITIVE_PLANE: LayerSpecification(
            layer_id=ArchitectureLayerId.L2_COGNITIVE_PLANE,
            name="Cognitive Planning & Context Plane",
            layer_number=2,
            description="Multimodal LLM reasoning, intent decomposition, knowledge retrieval, and action planning.",
            primary_engines=["ENG-02 (App Context)", "ENG-08 (Developer Lifecycle)", "ENG-09 (Predictive Caretaker)", "ENG-11 (Knowledge Retrieval)"],
            allowed_upstream_callers={ArchitectureLayerId.L1_PRESENTATION},
            allowed_downstream_targets={
                ArchitectureLayerId.L3_POLICY_ENGINE,
                ArchitectureLayerId.L4_DIGITAL_TWIN,
            },
            privilege_envelope="Strictly unprivileged user process (Zero OS mutation rights)",
            boundary_invariants=[
                "Rule of Strict Adjacency: Cannot bypass Layer 3 to reach Layer 5, 6, or 7.",
                "Outputs strongly typed ActionContracts; never raw shell strings.",
            ],
        ),
        ArchitectureLayerId.L3_POLICY_ENGINE: LayerSpecification(
            layer_id=ArchitectureLayerId.L3_POLICY_ENGINE,
            name="Deterministic Policy & Governance Engine",
            layer_number=3,
            description="Independent non-LLM invariant checker, persona governance evaluator, and safety constraint validator.",
            primary_engines=["ENG-04 (Governance Policy)", "Charter Validator", "Persona Evaluator", "Safety Constraint Validator"],
            allowed_upstream_callers={ArchitectureLayerId.L2_COGNITIVE_PLANE},
            allowed_downstream_targets={
                ArchitectureLayerId.L4_DIGITAL_TWIN,
                ArchitectureLayerId.L5_EXECUTION_BROKER,
            },
            privilege_envelope="Unprivileged deterministic pure-function engine",
            boundary_invariants=[
                "Decoupled from LLM weights; non-bypassable deterministic verification.",
                "Issues VerifiedCapabilityGrant exclusively to Layer 5 upon full compliance.",
            ],
        ),
        ArchitectureLayerId.L4_DIGITAL_TWIN: LayerSpecification(
            layer_id=ArchitectureLayerId.L4_DIGITAL_TWIN,
            name="Temporal Digital Twin & Provenance Store",
            layer_number=4,
            description="Append-only event-sourced model of system state, configuration, file provenance, and telemetry history.",
            primary_engines=["ENG-01 (Digital Twin)", "ENG-06 (File Intelligence)"],
            allowed_upstream_callers={
                ArchitectureLayerId.L1_PRESENTATION,
                ArchitectureLayerId.L2_COGNITIVE_PLANE,
                ArchitectureLayerId.L3_POLICY_ENGINE,
                ArchitectureLayerId.L5_EXECUTION_BROKER,
                ArchitectureLayerId.L6_PLATFORM_ADAPTERS,
                ArchitectureLayerId.L7_KERNEL_HARDWARE,
            },
            allowed_downstream_targets=set(),  # State store serves queries and accepts ingestion
            privilege_envelope="Unprivileged local storage access (SQLite WAL)",
            boundary_invariants=[
                "Append-only immutable audit trail; tamper-evident hash chaining.",
                "Zero storage of unredacted private credentials or continuous OCR frames.",
            ],
        ),
        ArchitectureLayerId.L5_EXECUTION_BROKER: LayerSpecification(
            layer_id=ArchitectureLayerId.L5_EXECUTION_BROKER,
            name="Narrow Privileged Execution Broker",
            layer_number=5,
            description="Least-privilege execution daemon enforcing preconditions, postconditions, and atomic compensation rollbacks.",
            primary_engines=["ENG-10 (Verified Execution Broker)", "Compensation Rollback Engine"],
            allowed_upstream_callers={ArchitectureLayerId.L3_POLICY_ENGINE},
            allowed_downstream_targets={
                ArchitectureLayerId.L4_DIGITAL_TWIN,
                ArchitectureLayerId.L6_PLATFORM_ADAPTERS,
            },
            privilege_envelope="Narrow least-privilege daemon process (Isolated broker context)",
            boundary_invariants=[
                "Accepts actions only with a valid VerifiedCapabilityGrant from Layer 3.",
                "Enforces reverse-chronological rollback on postcondition failure.",
            ],
        ),
        ArchitectureLayerId.L6_PLATFORM_ADAPTERS: LayerSpecification(
            layer_id=ArchitectureLayerId.L6_PLATFORM_ADAPTERS,
            name="Platform Capability Adapters & Sandboxing",
            layer_number=6,
            description="OS-specific API normalization, disposable micro-VM isolation, and container containment.",
            primary_engines=["ENG-07 (Controlled Sandboxing)", "ENG-12 (Universal Capability Registry)", "ENG-13 (NixOS Engine)", "macOSAdapter", "WindowsAdapter", "LinuxAdapter"],
            allowed_upstream_callers={ArchitectureLayerId.L5_EXECUTION_BROKER},
            allowed_downstream_targets={
                ArchitectureLayerId.L4_DIGITAL_TWIN,
                ArchitectureLayerId.L7_KERNEL_HARDWARE,
            },
            privilege_envelope="Platform-specific entitlement envelope (Hypervisor, seccomp, Landlock)",
            boundary_invariants=[
                "Normalizes OS divergences without masking platform-specific safety limits.",
                "Untrusted external files routed to disposable isolation.",
            ],
        ),
        ArchitectureLayerId.L7_KERNEL_HARDWARE: LayerSpecification(
            layer_id=ArchitectureLayerId.L7_KERNEL_HARDWARE,
            name="Native OS Kernel & Physical Hardware",
            layer_number=7,
            description="Authoritative native OS kernel (Darwin/XNU, Windows NT, Linux), security controls (SIP/WDAC), and hardware sensors.",
            primary_engines=["ENG-03 (Sensors)", "ENG-14 (Host Companion Agents)", "Native Kernels & Hardware"],
            allowed_upstream_callers={ArchitectureLayerId.L6_PLATFORM_ADAPTERS},
            allowed_downstream_targets={
                ArchitectureLayerId.L4_DIGITAL_TWIN,
                ArchitectureLayerId.L6_PLATFORM_ADAPTERS,
            },
            privilege_envelope="Native OS Kernel and privileged hardware supervisor",
            boundary_invariants=[
                "Authoritative lower-level security enforcement boundary.",
                "Native OS security mechanisms (SIP, Gatekeeper, WDAC) cannot be disabled.",
            ],
        ),
    }

    @classmethod
    def get_all(cls) -> List[LayerSpecification]:
        """Return all layer specifications ordered by layer number."""
        return sorted(cls._LAYERS.values(), key=lambda l: l.layer_number)

    @classmethod
    def get(cls, layer_id: ArchitectureLayerId | str) -> LayerSpecification:
        """Retrieve a layer specification by ID or string name."""
        if isinstance(layer_id, str):
            for lid, spec in cls._LAYERS.items():
                if lid.value == layer_id or lid == layer_id:
                    return spec
            raise KeyError(f"Unknown Layer ID: {layer_id}")
        if layer_id not in cls._LAYERS:
            raise KeyError(f"Unknown Layer ID: {layer_id}")
        return cls._LAYERS[layer_id]

    @classmethod
    def get_by_number(cls, number: int) -> LayerSpecification:
        """Retrieve a layer specification by layer number (1-7)."""
        for spec in cls._LAYERS.values():
            if spec.layer_number == number:
                return spec
        raise KeyError(f"Unknown Layer Number: {number}")


class ArchitectureBoundaryEnforcer:
    """Enforces strict layer boundary invariants, directionality, and prevents execution bypasses."""

    @classmethod
    def validate_transition(
        cls,
        source: ArchitectureLayerId,
        target: ArchitectureLayerId,
        direction: DataflowDirection,
    ) -> Tuple[bool, Optional[str]]:
        """Validate an attempted inter-layer invocation against architectural boundary rules."""
        src_spec = SevenLayerArchitectureRegistry.get(source)
        dst_spec = SevenLayerArchitectureRegistry.get(target)

        # Invariant 1: Rule of Strict Layer Adjacency for Downward Execution
        if direction == DataflowDirection.DOWNWARD_EXECUTION:
            # Downward execution can only move downward in layer hierarchy
            if dst_spec.layer_number <= src_spec.layer_number:
                return False, (
                    f"Architecture Violation: Downward execution from Layer {src_spec.layer_number} ({source.value}) "
                    f"cannot target upstream Layer {dst_spec.layer_number} ({target.value})."
                )

            # Check if source is allowed to invoke target
            if target not in src_spec.allowed_downstream_targets:
                return False, (
                    f"Architecture Bypass Blocked: Layer {src_spec.layer_number} ({source.value}) "
                    f"is not permitted to directly invoke Layer {dst_spec.layer_number} ({target.value}). "
                    f"All execution must traverse intermediate policy and broker gates."
                )

            # Check if target permits source caller
            if source not in dst_spec.allowed_upstream_callers:
                return False, (
                    f"Architecture Violation: Layer {dst_spec.layer_number} ({target.value}) "
                    f"rejects execution invocation from unauthorized caller Layer {src_spec.layer_number} ({source.value})."
                )

        # Invariant 2: Upward Observation Dataflow
        elif direction == DataflowDirection.UPWARD_OBSERVATION:
            # Observation flows from hardware/adapters/twin upward to consumers
            if dst_spec.layer_number > src_spec.layer_number and target != ArchitectureLayerId.L4_DIGITAL_TWIN:
                return False, (
                    f"Architecture Violation: Upward observation cannot flow downward from "
                    f"Layer {src_spec.layer_number} to Layer {dst_spec.layer_number}."
                )

        # Invariant 3: Lateral State Queries
        elif direction == DataflowDirection.LATERAL_QUERY:
            # Lateral state queries are permitted primarily targeting Layer 4 (Digital Twin)
            if target != ArchitectureLayerId.L4_DIGITAL_TWIN:
                return False, (
                    f"Architecture Violation: Lateral queries are permitted only against "
                    f"Layer 4 (Temporal Digital Twin), attempted against Layer {dst_spec.layer_number} ({target.value})."
                )

        return True, None
