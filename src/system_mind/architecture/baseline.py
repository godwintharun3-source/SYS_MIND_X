"""Architecture Baseline v1.0 specification, manifest, and cryptographic freeze verifier."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class BaselineComponentId(str, Enum):
    """The 14 foundational architectural subsystems established in Milestone 2."""

    ENGINE_CONTRACTS = "ENGINE_CONTRACTS"
    NFR_BENCHMARKS = "NFR_BENCHMARKS"
    SEVEN_LAYER_SYSTEM = "SEVEN_LAYER_SYSTEM"
    AI_NATIVE_SPLIT = "AI_NATIVE_SPLIT"
    CAPABILITY_PARITY = "CAPABILITY_PARITY"
    DIGITAL_TWIN_GRAPH = "DIGITAL_TWIN_GRAPH"
    TEMPORAL_OBSERVATIONS = "TEMPORAL_OBSERVATIONS"
    APPLICATION_OWNERSHIP = "APPLICATION_OWNERSHIP"
    SYSTEM_UPDATE_TAXONOMY = "SYSTEM_UPDATE_TAXONOMY"
    FILE_TRUST_POLICY = "FILE_TRUST_POLICY"
    TYPED_ACTION_CONTRACTS = "TYPED_ACTION_CONTRACTS"
    POLICY_PRECEDENCE = "POLICY_PRECEDENCE"
    AUDIT_LEDGER = "AUDIT_LEDGER"
    API_CONVENTIONS = "API_CONVENTIONS"


class FreezeStatus(str, Enum):
    """Freeze lifecycle state of an architectural subsystem specification."""

    FROZEN_APPROVED = "FROZEN_APPROVED"
    PROVISIONAL_REVIEW = "PROVISIONAL_REVIEW"
    DRIFT_DETECTED = "DRIFT_DETECTED"


@dataclass(frozen=True)
class ArchitectureComponentSpec:
    """Detailed frozen specification contract for an architectural subsystem."""

    component_id: BaselineComponentId
    name: str
    milestone_day: int
    layer_id: str
    adr_reference: str
    core_invariants: List[str]
    implementation_module: str
    status: FreezeStatus = FreezeStatus.FROZEN_APPROVED

    @property
    def specification_hash(self) -> str:
        """Deterministic SHA-256 digest of the component contract."""
        payload = {
            "component_id": self.component_id.value,
            "name": self.name,
            "milestone_day": self.milestone_day,
            "layer_id": self.layer_id,
            "adr_reference": self.adr_reference,
            "core_invariants": self.core_invariants,
            "implementation_module": self.implementation_module,
            "status": self.status.value,
        }
        canonical_str = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ArchitectureBaselineManifest:
    """Immutable v1.0 architecture baseline manifest sealing Milestone 2."""

    baseline_version: str
    frozen_date: str
    total_components: int
    components: Dict[BaselineComponentId, ArchitectureComponentSpec]
    baseline_fingerprint: str


@dataclass(frozen=True)
class ArchitectureBaselineAudit:
    """Formal audit report evaluating compliance and freeze integrity."""

    is_frozen: bool
    baseline_version: str
    baseline_fingerprint: str
    verified_components_count: int
    total_invariants_count: int
    unfrozen_components: List[BaselineComponentId]
    issues: List[str] = field(default_factory=list)


class ArchitectureBaselineRegistry:
    """Canonical registry containing the frozen specifications of all 14 subsystems."""

    _COMPONENTS: Dict[BaselineComponentId, ArchitectureComponentSpec] = {
        BaselineComponentId.ENGINE_CONTRACTS: ArchitectureComponentSpec(
            component_id=BaselineComponentId.ENGINE_CONTRACTS,
            name="14 Intelligence Engines Functional Requirements",
            milestone_day=11,
            layer_id="LAYER_4_INTELLIGENCE_ENGINES",
            adr_reference="ADR-011",
            core_invariants=[
                "All 14 intelligence engines expose typed action contracts.",
                "Zero raw shell or ambient execution authority granted to any engine.",
                "Engine outputs are structured proposals requiring broker mediation.",
            ],
            implementation_module="system_mind.engines",
        ),
        BaselineComponentId.NFR_BENCHMARKS: ArchitectureComponentSpec(
            component_id=BaselineComponentId.NFR_BENCHMARKS,
            name="Non-Functional Requirements for Reliability, Privacy, and Performance",
            milestone_day=12,
            layer_id="CROSS_LAYER_NFR",
            adr_reference="ADR-012",
            core_invariants=[
                "Policy evaluation latency strictly bounded (<100ms).",
                "Baseline resident set memory strictly capped (<500MB).",
                "Mandatory offline local inference fallback capability.",
            ],
            implementation_module="system_mind.nfr",
        ),
        BaselineComponentId.SEVEN_LAYER_SYSTEM: ArchitectureComponentSpec(
            component_id=BaselineComponentId.SEVEN_LAYER_SYSTEM,
            name="Seven-Layer System Architecture and Component Boundaries",
            milestone_day=13,
            layer_id="ALL_LAYERS_1_TO_7",
            adr_reference="ADR-013",
            core_invariants=[
                "Downward execution flow strictly follows layer adjacency.",
                "Direct bypass from Layer 7/Layer 4 to Layer 2/Layer 1 is prohibited.",
                "Upward observation telemetry flows asynchronously via Layer 5 Twin.",
            ],
            implementation_module="system_mind.architecture.layers",
        ),
        BaselineComponentId.AI_NATIVE_SPLIT: ArchitectureComponentSpec(
            component_id=BaselineComponentId.AI_NATIVE_SPLIT,
            name="AI and Native System Split Architecture Decision Records",
            milestone_day=14,
            layer_id="CROSS_PLANE_SPLIT",
            adr_reference="ADR-021..024",
            core_invariants=[
                "AI Control Plane is strictly an observer, planner, and explainer.",
                "Native OS Kernel and Trusted Broker are sole authoritative executors.",
                "Direct execution of LLM-generated code on the host OS is prohibited.",
            ],
            implementation_module="system_mind.architecture.split",
        ),
        BaselineComponentId.CAPABILITY_PARITY: ArchitectureComponentSpec(
            component_id=BaselineComponentId.CAPABILITY_PARITY,
            name="Cross-Platform Capability Parity Matrix",
            milestone_day=15,
            layer_id="LAYER_2_CAPABILITY_BROKER",
            adr_reference="ADR-025",
            core_invariants=[
                "Five-tier capability parity hierarchy across 8 core capability domains.",
                "Degraded or unsupported platform features must be explicitly declared.",
                "Zero simulation or fabrication of native OS security mechanisms.",
            ],
            implementation_module="system_mind.platform.parity",
        ),
        BaselineComponentId.DIGITAL_TWIN_GRAPH: ArchitectureComponentSpec(
            component_id=BaselineComponentId.DIGITAL_TWIN_GRAPH,
            name="Digital-Twin Entity and Relationship Property Graph",
            milestone_day=16,
            layer_id="LAYER_5_TEMPORAL_TWIN",
            adr_reference="ADR-026",
            core_invariants=[
                "Append-only property graph tracking system hardware, processes, and configs.",
                "Strict typing of all 8 core entity kinds with cryptographic provenance.",
                "Bidirectional relationships model hardware containment and process parentage.",
            ],
            implementation_module="system_mind.twin.graph",
        ),
        BaselineComponentId.TEMPORAL_OBSERVATIONS: ArchitectureComponentSpec(
            component_id=BaselineComponentId.TEMPORAL_OBSERVATIONS,
            name="Temporal Observations, Provenance, and Bounded Freshness",
            milestone_day=17,
            layer_id="LAYER_5_TEMPORAL_TWIN",
            adr_reference="ADR-027",
            core_invariants=[
                "Strictly monotonic observation sequence numbers with SHA-256 hashing.",
                "Observation freshness decays deterministically across 5 lifecycle stages.",
                "Staleness Guard blocks mutating operations against stale target entities.",
            ],
            implementation_module="system_mind.twin.temporal",
        ),
        BaselineComponentId.APPLICATION_OWNERSHIP: ArchitectureComponentSpec(
            component_id=BaselineComponentId.APPLICATION_OWNERSHIP,
            name="Application Ownership and User-App Exclusion Model",
            milestone_day=18,
            layer_id="LAYER_6_DETERMINISTIC_POLICY",
            adr_reference="ADR-028",
            core_invariants=[
                "Tripartite component ownership: SYSTEM_MANAGED, VENDOR_MANAGED, USER_MANAGED.",
                "User apps, project dependencies, and IDEs are permanently USER_MANAGED.",
                "Autonomous maintenance is strictly prohibited from mutating user applications.",
            ],
            implementation_module="system_mind.applications",
        ),
        BaselineComponentId.SYSTEM_UPDATE_TAXONOMY: ArchitectureComponentSpec(
            component_id=BaselineComponentId.SYSTEM_UPDATE_TAXONOMY,
            name="System-Update Ownership Taxonomy and Safety Lifecycle",
            milestone_day=19,
            layer_id="LAYER_6_DETERMINISTIC_POLICY",
            adr_reference="ADR-029",
            core_invariants=[
                "Six-tier update taxonomy restricting autonomous execution to Tiers 1 and 2.",
                "Cumulative OS updates require pre-update snapshots and maintenance windows.",
                "Firmware updates require explicit human approval, snapshots, and AC power.",
            ],
            implementation_module="system_mind.updates",
        ),
        BaselineComponentId.FILE_TRUST_POLICY: ArchitectureComponentSpec(
            component_id=BaselineComponentId.FILE_TRUST_POLICY,
            name="File Trust State Machine and Supported File-Handler Policy",
            milestone_day=20,
            layer_id="LAYER_6_DETERMINISTIC_POLICY",
            adr_reference="ADR-030",
            core_invariants=[
                "Eight-state discrete file trust lifecycle governed by 'Scan != Safe'.",
                "Quarantined and untrusted files restricted to static parsers or micro-VMs.",
                "Native host execution restricted to verified immutable or user-attested binaries.",
            ],
            implementation_module="system_mind.files",
        ),
        BaselineComponentId.TYPED_ACTION_CONTRACTS: ArchitectureComponentSpec(
            component_id=BaselineComponentId.TYPED_ACTION_CONTRACTS,
            name="Typed Action Contracts, Pre/Postconditions, and Atomic Rollback",
            milestone_day=21,
            layer_id="LAYER_6_TRUSTED_BROKER",
            adr_reference="ADR-031",
            core_invariants=[
                "All consequential operations mediated through TypedActionContracts.",
                "Broker dispatch mathematically blocked if any precondition evaluates False.",
                "Automated atomic rollback triggered immediately if any postcondition fails.",
            ],
            implementation_module="system_mind.contracts",
        ),
        BaselineComponentId.POLICY_PRECEDENCE: ArchitectureComponentSpec(
            component_id=BaselineComponentId.POLICY_PRECEDENCE,
            name="Identity, Role Authority, and Deterministic 4-Tier Policy Precedence",
            milestone_day=22,
            layer_id="LAYER_6_DETERMINISTIC_POLICY",
            adr_reference="ADR-032",
            core_invariants=[
                "Tier 1 Hard Charter Invariants override Enterprise Policies, Users, and AI.",
                "Unauthenticated identity requests are unconditionally rejected.",
                "Critical privileged operations mandate two-person or biometric authorization.",
            ],
            implementation_module="system_mind.governance",
        ),
        BaselineComponentId.AUDIT_LEDGER: ArchitectureComponentSpec(
            component_id=BaselineComponentId.AUDIT_LEDGER,
            name="Immutable Cryptographic Audit Ledger, Secret Redaction, and Retention",
            milestone_day=23,
            layer_id="LAYER_6_TRUSTED_BROKER",
            adr_reference="ADR-033",
            core_invariants=[
                "Append-only SHA-256 cryptographic hash-chaining prevents retroactive tampering.",
                "Automated recursive secret scrubbing protects credentials before persistence.",
                "Critical security audit records are permanently immutable and cannot be pruned.",
            ],
            implementation_module="system_mind.audit",
        ),
        BaselineComponentId.API_CONVENTIONS: ArchitectureComponentSpec(
            component_id=BaselineComponentId.API_CONVENTIONS,
            name="Unified API Wire Envelopes, RFC 7807 Error Model, and SemVer 2.0.0",
            milestone_day=24,
            layer_id="LAYER_7_APPLICATION_PRESENTATION",
            adr_reference="ADR-034",
            core_invariants=[
                "Universal ApiRequest and ApiResponse envelopes across all execution planes.",
                "Mutating operations strictly mandate unique idempotency keys.",
                "SemVer 2.0.0 negotiation strictly rejects breaking major version mismatches.",
            ],
            implementation_module="system_mind.api",
        ),
    }

    @classmethod
    def get_all(cls) -> Dict[BaselineComponentId, ArchitectureComponentSpec]:
        """Return shallow copy of all registered component specifications."""
        return dict(cls._COMPONENTS)

    @classmethod
    def get(cls, component_id: BaselineComponentId) -> ArchitectureComponentSpec:
        """Retrieve component specification by its identifier."""
        if component_id not in cls._COMPONENTS:
            raise KeyError(f"Component '{component_id}' is not in the architecture baseline.")
        return cls._COMPONENTS[component_id]


class ArchitectureBaselineVerifier:
    """Evaluates the completeness, invariant integrity, and cryptographic fingerprint of v1.0."""

    BASELINE_VERSION = "1.0.0"
    FROZEN_DATE = "2026-11-15"

    @classmethod
    def compute_fingerprint(cls, components: Dict[BaselineComponentId, ArchitectureComponentSpec]) -> str:
        """Compute the deterministic SHA-256 fingerprint over all sorted component specification hashes."""
        sorted_hashes = [
            components[cid].specification_hash
            for cid in sorted(components.keys(), key=lambda c: c.value)
        ]
        composite_payload = ":".join(sorted_hashes)
        return hashlib.sha256(composite_payload.encode("utf-8")).hexdigest()

    @classmethod
    def build_manifest(cls) -> ArchitectureBaselineManifest:
        """Construct the immutable v1.0 architecture baseline manifest."""
        components = ArchitectureBaselineRegistry.get_all()
        fingerprint = cls.compute_fingerprint(components)
        return ArchitectureBaselineManifest(
            baseline_version=cls.BASELINE_VERSION,
            frozen_date=cls.FROZEN_DATE,
            total_components=len(components),
            components=components,
            baseline_fingerprint=fingerprint,
        )

    @classmethod
    def audit_baseline(
        cls,
        manifest: Optional[ArchitectureBaselineManifest] = None,
    ) -> ArchitectureBaselineAudit:
        """Audit the baseline manifest against Milestone 2 completion criteria."""
        manifest = manifest or cls.build_manifest()
        issues: List[str] = []
        unfrozen: List[BaselineComponentId] = []
        total_invariants = 0

        # 1. Verify all 14 components are present
        expected_ids = set(BaselineComponentId)
        present_ids = set(manifest.components.keys())

        missing = expected_ids - present_ids
        if missing:
            issues.append(f"Missing required baseline components: {[m.value for m in missing]}")

        # 2. Verify status and invariants for each component
        for cid, spec in manifest.components.items():
            if spec.status != FreezeStatus.FROZEN_APPROVED:
                unfrozen.append(cid)
                issues.append(f"Component '{cid.value}' is not frozen (status: {spec.status.value}).")

            if len(spec.core_invariants) < 3:
                issues.append(
                    f"Component '{cid.value}' has insufficient core invariants ({len(spec.core_invariants)} < 3)."
                )
            total_invariants += len(spec.core_invariants)

        # 3. Fingerprint integrity check
        recalculated_fp = cls.compute_fingerprint(manifest.components)
        if recalculated_fp != manifest.baseline_fingerprint:
            issues.append(
                f"Baseline fingerprint mismatch: Manifest specifies '{manifest.baseline_fingerprint}', "
                f"but calculated digest is '{recalculated_fp}'."
            )

        is_frozen = len(issues) == 0

        return ArchitectureBaselineAudit(
            is_frozen=is_frozen,
            baseline_version=manifest.baseline_version,
            baseline_fingerprint=manifest.baseline_fingerprint,
            verified_components_count=len(manifest.components) - len(unfrozen),
            total_invariants_count=total_invariants,
            unfrozen_components=unfrozen,
            issues=issues,
        )
