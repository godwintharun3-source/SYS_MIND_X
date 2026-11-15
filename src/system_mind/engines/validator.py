"""Pipeline validation and safety boundary checking across the fourteen intelligence engines."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from system_mind.engines.contracts import (
    EngineId,
    EngineMaturityTier,
    EngineRegistry,
    EngineSpecification,
)


@dataclass
class EngineValidationReport:
    """Outcome of engine specifications and pipeline compatibility validation."""

    is_valid: bool
    total_engines_checked: int
    pipeline_connections_valid: bool
    violations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class EngineContractValidator:
    """Audits engine specifications and verifies inter-engine pipeline contract compatibility."""

    # Validated directed pipeline linkages in the SYSTEM MIND X topology
    _VALID_PIPELINE_TRANSITIONS: List[Tuple[EngineId, EngineId]] = [
        (EngineId.ENG_03_SENSOR_AWARENESS, EngineId.ENG_01_TEMPORAL_DIGITAL_TWIN),
        (EngineId.ENG_14_HOST_COMPANION_AGENTS, EngineId.ENG_01_TEMPORAL_DIGITAL_TWIN),
        (EngineId.ENG_02_APPLICATION_CONTEXT, EngineId.ENG_01_TEMPORAL_DIGITAL_TWIN),
        (EngineId.ENG_01_TEMPORAL_DIGITAL_TWIN, EngineId.ENG_09_PREDICTIVE_CARETAKER),
        (EngineId.ENG_01_TEMPORAL_DIGITAL_TWIN, EngineId.ENG_05_AUTONOMOUS_MAINTENANCE),
        (EngineId.ENG_05_AUTONOMOUS_MAINTENANCE, EngineId.ENG_04_GOVERNANCE_POLICY),
        (EngineId.ENG_08_DEVELOPER_LIFECYCLE, EngineId.ENG_04_GOVERNANCE_POLICY),
        (EngineId.ENG_04_GOVERNANCE_POLICY, EngineId.ENG_10_VERIFIED_EXECUTION_BROKER),
        (EngineId.ENG_10_VERIFIED_EXECUTION_BROKER, EngineId.ENG_07_CONTROLLED_SANDBOXING),
        (EngineId.ENG_10_VERIFIED_EXECUTION_BROKER, EngineId.ENG_12_UNIVERSAL_CAPABILITY_REGISTRY),
        (EngineId.ENG_10_VERIFIED_EXECUTION_BROKER, EngineId.ENG_13_NIXOS_SYSTEM_MIND_OS),
    ]

    @classmethod
    def validate_all_engines(cls) -> EngineValidationReport:
        """Audit all 14 engine specifications for completeness, safety constraints, and contract integrity."""
        violations: List[str] = []
        warnings: List[str] = []
        engines = EngineRegistry.get_all()

        if len(engines) != 14:
            violations.append(f"Specification Incomplete: Expected 14 intelligence engines, found {len(engines)}.")

        for spec in engines:
            # Check requirements completeness
            if not spec.functional_requirements:
                violations.append(f"Engine {spec.engine_id.value} ({spec.name}) has no functional requirements defined.")

            for req in spec.functional_requirements:
                if not req.error_states:
                    violations.append(f"Requirement {req.req_id} in {spec.engine_id.value} defines no error states.")
                if not req.permission_requirements:
                    violations.append(f"Requirement {req.req_id} in {spec.engine_id.value} defines no permission requirements.")
                if not req.unsupported_platform_behavior:
                    violations.append(f"Requirement {req.req_id} in {spec.engine_id.value} defines no unsupported platform behavior.")
                if not req.safety_constraints:
                    violations.append(f"Requirement {req.req_id} in {spec.engine_id.value} defines no safety constraints.")

            if not spec.primary_safety_boundary:
                violations.append(f"Engine {spec.engine_id.value} defines no primary safety boundary.")

        # Validate pipeline transitions
        pipeline_valid = True
        for src, dst in cls._VALID_PIPELINE_TRANSITIONS:
            try:
                src_spec = EngineRegistry.get(src)
                dst_spec = EngineRegistry.get(dst)
                if not src_spec.output_schema_types or not dst_spec.input_schema_types:
                    violations.append(f"Pipeline contract mismatch between {src.value} and {dst.value}.")
                    pipeline_valid = False
            except KeyError as e:
                violations.append(f"Missing pipeline engine: {str(e)}")
                pipeline_valid = False

        is_valid = (len(violations) == 0)
        return EngineValidationReport(
            is_valid=is_valid,
            total_engines_checked=len(engines),
            pipeline_connections_valid=pipeline_valid,
            violations=violations,
            warnings=warnings,
        )

    @classmethod
    def is_pipeline_transition_permitted(cls, source: EngineId, target: EngineId) -> bool:
        """Check whether direct dataflow from source to target engine is permitted in the system topology."""
        return (source, target) in cls._VALID_PIPELINE_TRANSITIONS
