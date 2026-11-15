"""Functional requirements, contracts, and data models for all fourteen intelligence engines."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class EngineId(str, Enum):
    """Unique identifiers for the fourteen intelligence engines."""

    ENG_01_TEMPORAL_DIGITAL_TWIN = "ENG-01"
    ENG_02_APPLICATION_CONTEXT = "ENG-02"
    ENG_03_SENSOR_AWARENESS = "ENG-03"
    ENG_04_GOVERNANCE_POLICY = "ENG-04"
    ENG_05_AUTONOMOUS_MAINTENANCE = "ENG-05"
    ENG_06_FILE_INTELLIGENCE = "ENG-06"
    ENG_07_CONTROLLED_SANDBOXING = "ENG-07"
    ENG_08_DEVELOPER_LIFECYCLE = "ENG-08"
    ENG_09_PREDICTIVE_CARETAKER = "ENG-09"
    ENG_10_VERIFIED_EXECUTION_BROKER = "ENG-10"
    ENG_11_KNOWLEDGE_RETRIEVAL = "ENG-11"
    ENG_12_UNIVERSAL_CAPABILITY_REGISTRY = "ENG-12"
    ENG_13_NIXOS_SYSTEM_MIND_OS = "ENG-13"
    ENG_14_HOST_COMPANION_AGENTS = "ENG-14"


class EngineMaturityTier(str, Enum):
    """Architectural classification of engine roles."""

    CORE_FOUNDATION = "CORE_FOUNDATION"
    ANALYSIS_AND_PLANNING = "ANALYSIS_AND_PLANNING"
    EXECUTION_AND_GOVERNANCE = "EXECUTION_AND_GOVERNANCE"
    PLATFORM_ADAPTER = "PLATFORM_ADAPTER"


@dataclass(frozen=True)
class EngineFunctionalRequirement:
    """Formal functional requirement contract for an intelligence engine."""

    req_id: str
    engine_id: EngineId
    title: str
    description: str
    input_contract: str
    output_contract: str
    error_states: List[str]
    permission_requirements: List[str]
    unsupported_platform_behavior: str
    safety_constraints: List[str]


@dataclass(frozen=True)
class EngineSpecification:
    """Consolidated architecture specification for an intelligence engine."""

    engine_id: EngineId
    name: str
    maturity_tier: EngineMaturityTier
    phase: str
    summary: str
    functional_requirements: List[EngineFunctionalRequirement]
    input_schema_types: List[str]
    output_schema_types: List[str]
    primary_safety_boundary: str


class EngineRegistry:
    """Central registry of verified specifications for all fourteen intelligence engines."""

    _ENGINES: Dict[EngineId, EngineSpecification] = {
        EngineId.ENG_01_TEMPORAL_DIGITAL_TWIN: EngineSpecification(
            engine_id=EngineId.ENG_01_TEMPORAL_DIGITAL_TWIN,
            name="Persistent Temporal Digital Twin",
            maturity_tier=EngineMaturityTier.CORE_FOUNDATION,
            phase="Phase 5: Days 066-090",
            summary="Append-only temporal graph and event log tracking system configuration, processes, and state over time.",
            functional_requirements=[
                EngineFunctionalRequirement(
                    req_id="FR-ENG01-01",
                    engine_id=EngineId.ENG_01_TEMPORAL_DIGITAL_TWIN,
                    title="Append-Only Observation Ingestion",
                    description="Ingest and timestamp observations from sensors and companion agents with provenance hashes.",
                    input_contract="ObservationEvent(timestamp, source_engine, payload_hash, payload)",
                    output_contract="EventReceipt(event_id, sequence_number, stored_timestamp)",
                    error_states=["CORRUPTED_EVENT_LOG", "STORAGE_CEILING_REACHED", "CLOCK_SKEW_DETECTED"],
                    permission_requirements=["Unprivileged local storage access (SQLite/WAL)"],
                    unsupported_platform_behavior="Falls back to in-memory circular buffer if disk persistence unavailable.",
                    safety_constraints=["SC-04: Protected privacy perimeters (~/.ssh, ~/.gnupg) are strictly excluded from event logs."],
                ),
                EngineFunctionalRequirement(
                    req_id="FR-ENG01-02",
                    engine_id=EngineId.ENG_01_TEMPORAL_DIGITAL_TWIN,
                    title="Temporal State Querying and Diffing",
                    description="Compute point-in-time snapshots and state deltas between two timestamps.",
                    input_contract="TemporalQuery(start_time, end_time, entity_filter)",
                    output_contract="TemporalDiff(entities_added, entities_modified, entities_removed)",
                    error_states=["QUERY_RANGE_INVALID", "CHECKPOINT_NOT_FOUND"],
                    permission_requirements=["Read-only internal query entitlement"],
                    unsupported_platform_behavior="Full query support across all platforms.",
                    safety_constraints=["SC-04: Queries cannot expose redacted secrets."],
                ),
            ],
            input_schema_types=["ObservationEvent", "TemporalQuery"],
            output_schema_types=["EventReceipt", "TemporalDiff", "DigitalTwinSnapshot"],
            primary_safety_boundary="Append-only immutable storage; zero indexing of private folders or keystrokes.",
        ),
        EngineId.ENG_02_APPLICATION_CONTEXT: EngineSpecification(
            engine_id=EngineId.ENG_02_APPLICATION_CONTEXT,
            name="Application Context Intelligence",
            maturity_tier=EngineMaturityTier.ANALYSIS_AND_PLANNING,
            phase="Phase 6: Days 091-110",
            summary="Semantic awareness of running applications, frontmost window focus, and background resource usage.",
            functional_requirements=[
                EngineFunctionalRequirement(
                    req_id="FR-ENG02-01",
                    engine_id=EngineId.ENG_02_APPLICATION_CONTEXT,
                    title="Window Focus and App Context Tracking",
                    description="Detect frontmost window focus shifts, active application bundle IDs, and document titles.",
                    input_contract="FocusChangeEvent(window_id, bundle_id, window_title)",
                    output_contract="ApplicationContextSnapshot(bundle_id, app_name, is_frontmost, context_tags)",
                    error_states=["ACCESSIBILITY_PERMISSION_DENIED", "WINDOW_LOOKUP_TIMEOUT"],
                    permission_requirements=["OS Accessibility / Window Server read permission"],
                    unsupported_platform_behavior="Falls back to process list polling if Accessibility API is uncertified.",
                    safety_constraints=["SC-04: Exclude password managers, private browser windows, and lock screens."],
                )
            ],
            input_schema_types=["FocusChangeEvent", "ProcessStateEvent"],
            output_schema_types=["ApplicationContextSnapshot"],
            primary_safety_boundary="No continuous screen OCR; zero capture of credential fields.",
        ),
        EngineId.ENG_03_SENSOR_AWARENESS: EngineSpecification(
            engine_id=EngineId.ENG_03_SENSOR_AWARENESS,
            name="Hardware & OS Sensor Awareness",
            maturity_tier=EngineMaturityTier.CORE_FOUNDATION,
            phase="Phase 4: Days 041-065",
            summary="Deep telemetry collection for CPU thermals, fan speeds, memory pressure, and battery health.",
            functional_requirements=[
                EngineFunctionalRequirement(
                    req_id="FR-ENG03-01",
                    engine_id=EngineId.ENG_03_SENSOR_AWARENESS,
                    title="Hardware Sensor Metric Collection",
                    description="Collect normalized hardware metrics from native platform kernel interfaces.",
                    input_contract="SensorPollRequest(metric_types)",
                    output_contract="SensorTelemetryReport(cpu_temp_c, fan_rpm, memory_pressure_pct, battery_cycles)",
                    error_states=["SENSOR_READ_FAILED", "PERMISSION_DENIED_SMC", "INTERFACE_UNAVAILABLE"],
                    permission_requirements=["Read-only hardware sensor entitlements"],
                    unsupported_platform_behavior="Tags missing sensors as PARTIAL with documented limitation notes.",
                    safety_constraints=["Read-only telemetry; zero write capability to hardware registers."],
                )
            ],
            input_schema_types=["SensorPollRequest"],
            output_schema_types=["SensorTelemetryReport"],
            primary_safety_boundary="Strictly read-only; zero hardware register mutation.",
        ),
        EngineId.ENG_04_GOVERNANCE_POLICY: EngineSpecification(
            engine_id=EngineId.ENG_04_GOVERNANCE_POLICY,
            name="Adaptive Governance & Policy Engine",
            maturity_tier=EngineMaturityTier.EXECUTION_AND_GOVERNANCE,
            phase="Phase 9: Days 151-175",
            summary="Independent deterministic rules engine evaluating action contracts against invariants and threat constraints.",
            functional_requirements=[
                EngineFunctionalRequirement(
                    req_id="FR-ENG04-01",
                    engine_id=EngineId.ENG_04_GOVERNANCE_POLICY,
                    title="Deterministic Action Contract Verification",
                    description="Evaluate proposed action contracts against charter invariants, persona envelopes, and STRIDE constraints.",
                    input_contract="ActionContract(action_id, action_type, target_component, risk_tier)",
                    output_contract="PolicyDecision(is_permitted, required_approval, violations, warnings)",
                    error_states=["INVALID_CONTRACT_SCHEMA", "UNKNOWN_PERSONA", "POLICY_CONFLICT"],
                    permission_requirements=["Unprivileged pure-function evaluation"],
                    unsupported_platform_behavior="Evaluates identical deterministic rules on all platforms.",
                    safety_constraints=["SC-01..08: Fully independent of LLM reasoning; hard invariants are non-bypassable."],
                )
            ],
            input_schema_types=["ActionContract"],
            output_schema_types=["PolicyDecision"],
            primary_safety_boundary="Deterministic pure evaluation decoupled from LLM weights.",
        ),
        EngineId.ENG_05_AUTONOMOUS_MAINTENANCE: EngineSpecification(
            engine_id=EngineId.ENG_05_AUTONOMOUS_MAINTENANCE,
            name="Autonomous OS Maintenance Engine",
            maturity_tier=EngineMaturityTier.ANALYSIS_AND_PLANNING,
            phase="Phase 13: Days 245-269",
            summary="Policy-driven preventative OS maintenance, cache cleanups, log rotations, and security definition updates.",
            functional_requirements=[
                EngineFunctionalRequirement(
                    req_id="FR-ENG05-01",
                    engine_id=EngineId.ENG_05_AUTONOMOUS_MAINTENANCE,
                    title="Autonomous System Maintenance Dispatch",
                    description="Generate maintenance action contracts for SYSTEM_MANAGED components when host is idle and on AC power.",
                    input_contract="MaintenanceTrigger(is_idle, on_ac_power, battery_pct)",
                    output_contract="MaintenanceActionBatch(actions, total_risk_tier)",
                    error_states=["HOST_BUSY_DEFERRAL", "BATTERY_POWER_DEFERRAL", "COMPONENT_OWNERSHIP_CONFLICT"],
                    permission_requirements=["Generates unprivileged action contracts for broker validation"],
                    unsupported_platform_behavior="Omits unsupported platform maintenance tasks with explicit log notes.",
                    safety_constraints=["SC-02: Strictly forbidden from touching USER_MANAGED components (browsers, IDEs, virtualenvs)."],
                )
            ],
            input_schema_types=["MaintenanceTrigger"],
            output_schema_types=["MaintenanceActionBatch"],
            primary_safety_boundary="Component ownership invariant: SYSTEM_MANAGED only, never USER_MANAGED.",
        ),
        EngineId.ENG_06_FILE_INTELLIGENCE: EngineSpecification(
            engine_id=EngineId.ENG_06_FILE_INTELLIGENCE,
            name="Universal File Intelligence & Provenance",
            maturity_tier=EngineMaturityTier.ANALYSIS_AND_PLANNING,
            phase="Phase 11: Days 200-224",
            summary="Tracks file origins, cryptographic hashes, quarantine attributes, and static risk heuristics.",
            functional_requirements=[
                EngineFunctionalRequirement(
                    req_id="FR-ENG06-01",
                    engine_id=EngineId.ENG_06_FILE_INTELLIGENCE,
                    title="File Provenance and Cryptographic Hash Tracking",
                    description="Inspect file path, calculate SHA-256 hash, and extract origin quarantine metadata.",
                    input_contract="FileInspectRequest(file_path)",
                    output_contract="FileProvenanceRecord(sha256, origin_url, quarantine_status, mime_type, risk_score)",
                    error_states=["FILE_NOT_FOUND", "PERMISSION_DENIED", "METADATA_UNAVAILABLE"],
                    permission_requirements=["Read-only filesystem inspection"],
                    unsupported_platform_behavior="Maintains hash tracking across all platforms; adapts quarantine extraction.",
                    safety_constraints=["Scan != Safe Invariant: A clean scan score never grants native execution."],
                )
            ],
            input_schema_types=["FileInspectRequest"],
            output_schema_types=["FileProvenanceRecord"],
            primary_safety_boundary="Scan does not prove safety; mandatory quarantine for untrusted origins.",
        ),
        EngineId.ENG_07_CONTROLLED_SANDBOXING: EngineSpecification(
            engine_id=EngineId.ENG_07_CONTROLLED_SANDBOXING,
            name="Controlled File Execution & Sandboxing",
            maturity_tier=EngineMaturityTier.EXECUTION_AND_GOVERNANCE,
            phase="Phase 12: Days 225-244",
            summary="Zero-trust containment of untrusted binaries in disposable micro-VMs or restricted viewers.",
            functional_requirements=[
                EngineFunctionalRequirement(
                    req_id="FR-ENG07-01",
                    engine_id=EngineId.ENG_07_CONTROLLED_SANDBOXING,
                    title="Disposable Micro-Isolation Detonation",
                    description="Execute external untrusted binary in an isolated micro-VM without host filesystem or network access.",
                    input_contract="SandboxExecutionRequest(binary_path, isolation_type, timeout_seconds)",
                    output_contract="SandboxedExecutionTrace(exit_code, syscalls_observed, file_mods_isolated, did_timeout)",
                    error_states=["HYPERVISOR_UNAVAILABLE", "SPAWN_TIMEOUT", "SANDBOX_ESCAPE_ALERT"],
                    permission_requirements=["Platform virtualization entitlement (Hypervisor.framework, KVM, WHPX)"],
                    unsupported_platform_behavior="Falls back to HARDENED_VIEWER or denies execution if hypervisor unavailable.",
                    safety_constraints=["SC-03: Untrusted external binaries can never execute natively on the host."],
                )
            ],
            input_schema_types=["SandboxExecutionRequest"],
            output_schema_types=["SandboxedExecutionTrace"],
            primary_safety_boundary="Zero host filesystem or ambient network access during untrusted detonation.",
        ),
        EngineId.ENG_08_DEVELOPER_LIFECYCLE: EngineSpecification(
            engine_id=EngineId.ENG_08_DEVELOPER_LIFECYCLE,
            name="Developer Lifecycle Intelligence",
            maturity_tier=EngineMaturityTier.ANALYSIS_AND_PLANNING,
            phase="Phase 14: Days 270-284",
            summary="Diagnoses developer toolchains, build dependency graphs, compiler diagnostics, and virtualenv health.",
            functional_requirements=[
                EngineFunctionalRequirement(
                    req_id="FR-ENG08-01",
                    engine_id=EngineId.ENG_08_DEVELOPER_LIFECYCLE,
                    title="Toolchain & Build Graph Diagnostics",
                    description="Inspect active workspace manifests (pyproject.toml, package.json, Cargo.toml) and toolchains.",
                    input_contract="WorkspaceDiagnosticRequest(workspace_path)",
                    output_contract="ToolchainDiagnosticsReport(compilers_found, missing_tools, lockfile_healthy)",
                    error_states=["UNKNOWN_BUILD_SYSTEM", "CORRUPTED_MANIFEST", "WORKSPACE_UNREADABLE"],
                    permission_requirements=["Read-only workspace inspection"],
                    unsupported_platform_behavior="Cross-platform manifest parsing across all supported hosts.",
                    safety_constraints=["SC-02: Never automatically update project dependencies or virtual environments."],
                )
            ],
            input_schema_types=["WorkspaceDiagnosticRequest"],
            output_schema_types=["ToolchainDiagnosticsReport"],
            primary_safety_boundary="Zero automated dependency mutation; user-initiated diagnostics only.",
        ),
        EngineId.ENG_09_PREDICTIVE_CARETAKER: EngineSpecification(
            engine_id=EngineId.ENG_09_PREDICTIVE_CARETAKER,
            name="Predictive Diagnosis & Caretaker Reporting",
            maturity_tier=EngineMaturityTier.ANALYSIS_AND_PLANNING,
            phase="Phase 15: Days 285-299",
            summary="Analyzes temporal telemetry to detect early host degradation and generates plain-language caretaker reports.",
            functional_requirements=[
                EngineFunctionalRequirement(
                    req_id="FR-ENG09-01",
                    engine_id=EngineId.ENG_09_PREDICTIVE_CARETAKER,
                    title="Proactive Degradation Prediction & Explanation",
                    description="Forecast disk wear, memory exhaustion, or zombie processes and output plain-language caretaker reports.",
                    input_contract="CaretakerAnalysisRequest(telemetry_stream, history_depth_hours)",
                    output_contract="CaretakerReport(health_score, degradation_flags, plain_text_explanation, recommended_actions)",
                    error_states=["INSUFFICIENT_TELEMETRY_DATA", "METRIC_SKEW_DETECTED"],
                    permission_requirements=["Read-only analytics"],
                    unsupported_platform_behavior="Adapts predictions to available platform metrics.",
                    safety_constraints=["Recommendations cannot auto-execute without policy engine validation."],
                )
            ],
            input_schema_types=["CaretakerAnalysisRequest"],
            output_schema_types=["CaretakerReport"],
            primary_safety_boundary="Pure analysis; recommended actions must pass ENG-04 and ENG-10 gates.",
        ),
        EngineId.ENG_10_VERIFIED_EXECUTION_BROKER: EngineSpecification(
            engine_id=EngineId.ENG_10_VERIFIED_EXECUTION_BROKER,
            name="Risk-Adaptive Verified Execution Broker",
            maturity_tier=EngineMaturityTier.EXECUTION_AND_GOVERNANCE,
            phase="Phase 10: Days 176-199",
            summary="Narrow, least-privilege execution daemon enforcing preconditions, postconditions, and atomic rollbacks.",
            functional_requirements=[
                EngineFunctionalRequirement(
                    req_id="FR-ENG10-01",
                    engine_id=EngineId.ENG_10_VERIFIED_EXECUTION_BROKER,
                    title="Brokered Contract Execution & Rollback",
                    description="Execute approved action contract, verify preconditions, assert postconditions, and trigger rollback upon failure.",
                    input_contract="ValidatedActionContract(contract_id, action_type, pre_conditions, post_conditions, rollback_handler)",
                    output_contract="BrokerExecutionReceipt(success, pre_state_hash, post_state_hash, rollback_triggered, duration_ms)",
                    error_states=["PRECONDITION_VIOLATION", "POSTCONDITION_VIOLATION", "ROLLBACK_FAILED", "BROKER_IPC_TIMEOUT"],
                    permission_requirements=["Narrow least-privilege broker daemon execution"],
                    unsupported_platform_behavior="Dispatches through platform-specific broker adapters.",
                    safety_constraints=["SC-01: Rejects raw shell execution; enforces atomic compensation on failure."],
                )
            ],
            input_schema_types=["ValidatedActionContract"],
            output_schema_types=["BrokerExecutionReceipt"],
            primary_safety_boundary="Typed contracts only; narrow daemon execution; mandatory rollback handlers.",
        ),
        EngineId.ENG_11_KNOWLEDGE_RETRIEVAL: EngineSpecification(
            engine_id=EngineId.ENG_11_KNOWLEDGE_RETRIEVAL,
            name="Knowledge & Cognitive Retrieval Plane",
            maturity_tier=EngineMaturityTier.ANALYSIS_AND_PLANNING,
            phase="Phase 7: Days 111-130",
            summary="Local, offline-capable vector and graph retrieval indexing system manuals, schemas, and incident playbooks.",
            functional_requirements=[
                EngineFunctionalRequirement(
                    req_id="FR-ENG11-01",
                    engine_id=EngineId.ENG_11_KNOWLEDGE_RETRIEVAL,
                    title="Offline Playbook and Schema Retrieval",
                    description="Query indexed system manuals, command schemas, and remediation playbooks with source attribution.",
                    input_contract="KnowledgeQuery(query_text, domain_filter, max_results)",
                    output_contract="KnowledgeRetrievalResult(passages, source_documents, relevance_scores)",
                    error_states=["INDEX_CORRUPTED", "EMBEDDING_FAILED", "EMPTY_QUERY"],
                    permission_requirements=["Unprivileged local file read access to indexed docs"],
                    unsupported_platform_behavior="Fully portable local storage across all supported hosts.",
                    safety_constraints=["SC-04: Never ingests or indexes private directories (~/.ssh, ~/.gnupg, ~/Documents)."],
                )
            ],
            input_schema_types=["KnowledgeQuery"],
            output_schema_types=["KnowledgeRetrievalResult"],
            primary_safety_boundary="Local-first offline retrieval; strict exclusion of private user folders.",
        ),
        EngineId.ENG_12_UNIVERSAL_CAPABILITY_REGISTRY: EngineSpecification(
            engine_id=EngineId.ENG_12_UNIVERSAL_CAPABILITY_REGISTRY,
            name="Universal Capability Registry",
            maturity_tier=EngineMaturityTier.PLATFORM_ADAPTER,
            phase="Phase 8: Days 131-150",
            summary="Normalizes operating system API divergences behind typed platform-agnostic capability contracts.",
            functional_requirements=[
                EngineFunctionalRequirement(
                    req_id="FR-ENG12-01",
                    engine_id=EngineId.ENG_12_UNIVERSAL_CAPABILITY_REGISTRY,
                    title="Platform Capability Status Query",
                    description="Query whether a specific OS capability is SUPPORTED, PARTIAL, or UNSUPPORTED on the active host.",
                    input_contract="CapabilityQuery(capability_id, platform_target)",
                    output_contract="CapabilityStatusDetail(capability_id, status, limitations, platform_adapter)",
                    error_states=["UNKNOWN_CAPABILITY_ID", "ADAPTER_NOT_BOUND"],
                    permission_requirements=["Unprivileged registry query"],
                    unsupported_platform_behavior="Returns explicit UNSUPPORTED status with limitation notes.",
                    safety_constraints=["No speculative capability fabrication: uncertified features marked UNSUPPORTED."],
                )
            ],
            input_schema_types=["CapabilityQuery"],
            output_schema_types=["CapabilityStatusDetail"],
            primary_safety_boundary="Forbids claiming support for unverified or unavailable platform capabilities.",
        ),
        EngineId.ENG_13_NIXOS_SYSTEM_MIND_OS: EngineSpecification(
            engine_id=EngineId.ENG_13_NIXOS_SYSTEM_MIND_OS,
            name="Linux / NixOS System Mind OS Foundation",
            maturity_tier=EngineMaturityTier.PLATFORM_ADAPTER,
            phase="Phase 16: Days 300-324",
            summary="Manages declarative, reproducible system configurations and atomic generation rollbacks on NixOS.",
            functional_requirements=[
                EngineFunctionalRequirement(
                    req_id="FR-ENG13-01",
                    engine_id=EngineId.ENG_13_NIXOS_SYSTEM_MIND_OS,
                    title="Declarative Generation Management & Rollback",
                    description="Build, activate, or roll back declarative NixOS system configurations with cryptographic closure hashes.",
                    input_contract="NixRebuildRequest(configuration_expr, target_action)",
                    output_contract="NixGenerationReceipt(generation_id, closure_hash, build_success, rollback_ready)",
                    error_states=["NIX_EVALUATION_ERROR", "BUILD_FAILED", "GENERATION_NOT_FOUND"],
                    permission_requirements=["Narrow broker daemon for nixos-rebuild invocation"],
                    unsupported_platform_behavior="Marked UNSUPPORTED on macOS/Windows hosts; active in Linux/NixOS VMs.",
                    safety_constraints=["Atomic rollbacks: activation failures automatically revert to previous generation."],
                )
            ],
            input_schema_types=["NixRebuildRequest"],
            output_schema_types=["NixGenerationReceipt"],
            primary_safety_boundary="Declarative generation immutability; automatic fallback on activation failure.",
        ),
        EngineId.ENG_14_HOST_COMPANION_AGENTS: EngineSpecification(
            engine_id=EngineId.ENG_14_HOST_COMPANION_AGENTS,
            name="Cross-Platform Host Companion Agents",
            maturity_tier=EngineMaturityTier.PLATFORM_ADAPTER,
            phase="Phase 4, 16, 17: Days 041+, 300+, 325+",
            summary="Lightweight native daemons providing uniform telemetry capture and authenticated local IPC.",
            functional_requirements=[
                EngineFunctionalRequirement(
                    req_id="FR-ENG14-01",
                    engine_id=EngineId.ENG_14_HOST_COMPANION_AGENTS,
                    title="Authenticated Host Telemetry and IPC Stream",
                    description="Stream standardized process, network, and mount events to the control plane over authenticated local IPC.",
                    input_contract="HostDaemonStreamRequest(channel, sample_rate_hz)",
                    output_contract="HostTelemetryStream(events, daemon_version, host_uptime_s)",
                    error_states=["IPC_SOCKET_ERROR", "AUTHENTICATION_FAILED", "PERMISSION_REVOKED"],
                    permission_requirements=["Native daemon service entitlement (LaunchDaemon, Windows Service, systemd)"],
                    unsupported_platform_behavior="Native daemon tailored to each certified platform target.",
                    safety_constraints=["Mutually authenticated local IPC; credentials redacted before transmission."],
                )
            ],
            input_schema_types=["HostDaemonStreamRequest"],
            output_schema_types=["HostTelemetryStream"],
            primary_safety_boundary="Local authenticated IPC only; zero unredacted secret transmission.",
        ),
    }

    @classmethod
    def get_all(cls) -> List[EngineSpecification]:
        """Return specifications for all fourteen engines."""
        return list(cls._ENGINES.values())

    @classmethod
    def get(cls, engine_id: EngineId | str) -> EngineSpecification:
        """Retrieve an engine specification by EngineId or string identifier."""
        if isinstance(engine_id, str):
            for eid, spec in cls._ENGINES.items():
                if eid.value == engine_id or eid == engine_id:
                    return spec
            raise KeyError(f"Unknown Engine ID: {engine_id}")
        if engine_id not in cls._ENGINES:
            raise KeyError(f"Unknown Engine ID: {engine_id}")
        return cls._ENGINES[engine_id]

    @classmethod
    def filter_by_maturity_tier(cls, tier: EngineMaturityTier) -> List[EngineSpecification]:
        """Filter engines by maturity tier."""
        return [spec for spec in cls._ENGINES.values() if spec.maturity_tier == tier]
