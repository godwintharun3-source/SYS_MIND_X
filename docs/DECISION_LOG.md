# Architecture Decision Log

## ADR-001: AI is the high-level control plane; native kernels remain the execution foundation
Status: proposed baseline. The model plans and explains. Trusted brokers and native OS APIs execute bounded operations.

## ADR-002: Cross-platform adapters
Status: proposed baseline. Use one capability contract and separate macOS, Windows and Linux adapters.

## ADR-003: Start with macOS companion agent, then NixOS VM, then Windows
Status: proposed baseline. Keep the developer's host safe; validate OS changes in disposable VMs.

## ADR-004: SQLite first
Status: proposed baseline. Start with SQLite and event tables; introduce PostgreSQL/graph storage only when measured needs justify it.

## ADR-005: No unrestricted file execution
Status: non-negotiable. Trust is evidence-based and time-sensitive. Unknown files are isolated or handled by a restricted viewer.

## ADR-006: System updates exclude user applications
Status: non-negotiable. Maintain component ownership and never silently update user-installed apps or project dependencies.

## ADR-007: Persistent files, not chat history, are project memory
Status: non-negotiable. Every daily agent session reloads project state from repository files.

## ADR-008: Machine-Enforceable Charter Contracts and Read-Only Host Telemetry
Status: accepted. Charter boundaries (rejection of raw root/shell, strict exclusion of user applications from autonomous updates, zero-trust execution confinement, explicit approvals for critical operations) are implemented as typed contracts and deterministic validators rather than natural-language instructions alone. Non-destructive host inspection verifies environment facts (Apple Silicon M1, SIP, Gatekeeper) without mutating host system configuration.

## ADR-009: Persona-Driven Contextual Governance Envelopes
Status: accepted. SYSTEM MIND X enforces distinct contextual governance envelopes for Personal, Developer, and Enterprise Admin personas. Personal users are bounded to Low/Medium impact with strict privacy perimeter protection; Developers have scoped high-impact workspace capabilities with absolute protection against autonomous dependency updates; Enterprise Admins have full audit visibility and require dual-person or break-glass approval for critical privileged actions.

## ADR-010: State-Machine User Journey Execution, Compensation Rollback, and Quantitative Outcomes
Status: accepted. User journeys are structured as formal state-machine step sequences. Every step enforces independent policy checks, preconditions, broker execution, postconditions, and audit records. Any mid-sequence failure triggers automatic reverse-chronological compensation rollbacks. Journey success is evaluated against strict quantitative metrics (latency, non-interference invariants, containment isolation, audit completeness).

## ADR-011: Granular Capability-Level Platform & Hardware Support Matrix
Status: accepted. The first-release support matrix is strictly bounded to four verified platform profiles: macOS on Apple Silicon M1 (Tier 1 Development Host & Companion), Windows 11 x64 (Tier 2 Companion), Ubuntu LTS x86_64 (Tier 2 Companion), and NixOS VM (Tier 3 Prototype OS). Operating system APIs are not treated as fungible; every engine capability must be explicitly tagged as SUPPORTED, PARTIAL (with documented limitations), or MOCK_ONLY. Uncertified platforms (Intel macOS, Windows 10/32-bit, non-systemd Linux) are rejected by policy.

## ADR-012: Countermeasure Architecture Derived from Prior Art Failure Modes
Status: accepted. Systematic analysis of current AI-native OS and computer-use agent prior art identifies six core failure modes: Ambient Authority Abuse (F1), Prompt Injection via Uncontained Inputs (F2), Hallucinated Destructive Execution (F3), Irreversible State Drift (F4), Ambient Screen Scraping Privacy Leaks (F5), and Component Ownership Contamination (F6). SYSTEM MIND X incorporates explicit architectural countermeasures rejecting all six patterns through typed broker mediation, deterministic policy verification, zero ambient screen recording, and strict component ownership protection.

## ADR-013: Research-Gap Closure via Independent Policy Broker and Component Segregation
Status: accepted. Benchmarking against seven competitive and prior art systems across eight core dimensions establishes that SYSTEM MIND X addresses five critical industry research gaps: Gap 1 (AI-Native Policy-Broker Disconnect), Gap 2 (Component Ownership Vacuum & Dependency Clobbering), Gap 3 (The 'Scan is Safe' Fallacy & Ambient Host Execution), Gap 4 (Screen Ephemerality vs Persistent Temporal Digital Twin), and Gap 5 (The All-or-Nothing Privilege Trap). Full native compliance across all dimensions is enforced as an architectural invariant.

## ADR-014: Six-Zone Trust Boundary Architecture and STRIDE Threat Model
Status: accepted. SYSTEM MIND X formally stratifies system operations across six hierarchical Trust Zones (Zone 0: Untrusted External, Zone 1: User Space, Zone 2: AI Control Plane, Zone 3: Deterministic Policy Engine, Zone 4: Privileged Broker, Zone 5: Kernel & Hardware). Transitions must strictly obey the Rule of Strict Adjacency (AI Control Plane Zone 2 cannot bypass Policy Engine Zone 3 to reach Broker Zone 4 or Kernel Zone 5) and the Rule of Untrusted External Non-Execution (Zone 0 binaries can never execute in Zone 1/5 without verified containment). All six STRIDE threat categories (Spoofing, Tampering, Repudiation, Information Disclosure, Denial of Service, Elevation of Privilege) are cataloged into typed threat vectors with verified architectural mitigations.

## ADR-015: Operation Classification Taxonomy, Privilege Levels, and Reversibility
Status: accepted. All SYSTEM MIND X system operations are categorized across three orthogonal dimensions: Impact (OperationRiskTier: READ_ONLY to CRITICAL_PRIVILEGED), Privilege Level (PrivilegeLevel: UNPRIVILEGED_USER, USER_CONSENT_GRANTED, ELEVATED_BROKER_REQUIRED, HARDWARE_FIRMWARE_ENTITLED), and Reversibility (Reversibility: REVERSIBLE, PARTIALLY_REVERSIBLE, IRREVERSIBLE) paired with concrete rollback strategies (RollbackStrategy: ATOMIC_FILE_RESTORE, STATE_INVERSE_ACTION, TRANSACTIONAL_SNAPSHOT, NOT_REVERSIBLE_COMPENSATION_ONLY). Autonomous unattended maintenance is strictly limited to SYSTEM_MANAGED components with risk not exceeding MEDIUM_IMPACT; USER_MANAGED components and HIGH_IMPACT / CRITICAL_PRIVILEGED operations are strictly excluded.

## ADR-016: Formal Product Non-Goals and Explicit Safety Constraints
Status: accepted. SYSTEM MIND X formalizes ten explicit Product Non-Goals (NG-01 to NG-10: no unrestricted shell, no ambient screen OCR, no autonomous user-app mutation, no scan-means-safe native execution, no security control bypass, no mandatory cloud exfiltration, no unbounded fleet mutation, no monolithic kernel from scratch, no unattended firmware flashing, no speculative capability fabrication). These negative requirements are enforced at runtime through eight machine-enforceable safety constraints (SC-01 to SC-08) by the SafetyConstraintValidator, providing hard non-bypassable architectural gates before broker execution.

## ADR-017: Core Research Questions and First-Release Acceptance Gates
Status: accepted. SYSTEM MIND X formalizes eight foundational research questions (RQ-01 to RQ-08) covering policy-broker decoupling, component ownership segregation, zero-trust file containment, temporal digital twin fidelity, contextual persona governance, automated compensation rollback, cross-platform capability parity, and zero ambient authority. All software increments and releases must programmatically satisfy eight First-Release Acceptance Gates (AG-01: Functional Completeness, AG-02: Tests & Regression Pass, AG-03: Security & Trust Boundaries, AG-04: Reliability & Rollback, AG-05: Platform Matrix Verification, AG-06: Documentation & Architecture, AG-07: Evidence & Secret Redaction, AG-08: Human Review & Day Gate) evaluated by ReleaseGateVerifier.

## ADR-018: Functional Requirements and Pipeline Topology for the Fourteen Intelligence Engines
Status: accepted. SYSTEM MIND X formalizes the functional requirements, input/output schemas, error states, and safety boundaries for all fourteen specialized intelligence engines (ENG-01 to ENG-14). Rather than routing OS execution through an undifferentiated monolithic LLM, system operations must traverse a verified pipeline topology: observation engines (Sensors, App Context, Companions) feed the Temporal Digital Twin; synthesis engines (Knowledge Retrieval, Caretaker, Developer Intelligence, Autonomous Maintenance) feed the Adaptive Governance & Policy Engine; and the Policy Engine verifies typed contracts before passing them to the Risk-Adaptive Verified Execution Broker and sandboxing adapters. Direct bypass of governance or execution boundaries is strictly prohibited.

## ADR-019: Non-Functional Requirements Framework for Reliability, Privacy, and Performance
Status: accepted. SYSTEM MIND X formalizes fifteen measurable Non-Functional Requirements across four categories: Reliability (NFR-REL-01: rollback convergence <= 5000ms, NFR-REL-02: crash recovery <= 500ms, NFR-REL-03: 99.99% uptime, NFR-REL-04: 100% pre/post assertion), Privacy (NFR-PRIV-01: 0 cleartext secrets, NFR-PRIV-02: 0 ambient screen OCR frames, NFR-PRIV-03: 100% offline local autonomy, NFR-PRIV-04: 100% cryptographic audit chains), Performance (NFR-PERF-01: policy evaluation P95 <= 5.0ms, NFR-PERF-02: twin convergence <= 50.0ms, NFR-PERF-03: companion memory <= 50 MB RSS, NFR-PERF-04: idle CPU <= 0.5%, NFR-PERF-05: broker IPC overhead <= 25.0ms), and Safety (NFR-SAFE-01: 0 user-managed app modifications, NFR-SAFE-02: 100% zero-trust binary containment). All requirements are enforced programmatically by NfrComplianceEvaluator.

## ADR-020: Seven-Layer System Architecture and Inter-Layer Component Boundaries
Status: accepted. SYSTEM MIND X establishes a strict Seven-Layer System Architecture: Layer 1 (Presentation & Interface), Layer 2 (Cognitive Planning & Context Plane), Layer 3 (Deterministic Policy & Governance Engine), Layer 4 (Temporal Digital Twin & Provenance Store), Layer 5 (Narrow Privileged Execution Broker), Layer 6 (Platform Capability Adapters & Sandboxing), and Layer 7 (Native OS Kernel & Physical Hardware). Inter-layer communication is enforced programmatically by ArchitectureBoundaryEnforcer according to three cardinal invariants: the Rule of Strict Adjacency (Layer 2 cannot bypass Layer 3 to directly invoke Layer 5, 6, or 7), Directional Separation (downward execution requests vs upward telemetry/event observations), and Autonomous Non-Interference with user-managed components.

## ADR-021: AI Cognitive Plane as an Untrusted Planner Isolated in User Space
Status: accepted. The AI cognitive plane runs in unprivileged user space with zero OS mutation rights and communicates outward solely via typed declarative ActionContracts. All consequential actions require downstream deterministic policy approval, ensuring prompt injections cannot trigger native system calls.

## ADR-022: Narrow Privileged Execution Broker with Cryptographic Provenance and Atomic Rollback
Status: accepted. Consequential state modifications are dispatched exclusively through a narrow broker daemon that validates preconditions, enforces atomic rollbacks upon postcondition failure, and logs immutable SHA-256 audit receipts. Ambient shell execution is eliminated.

## ADR-023: Deterministic Non-LLM Invariant Firewall as Authority Gate
Status: accepted. An independent deterministic rules engine operating strictly outside LLM weights evaluates all proposed contracts against charter invariants and component ownership boundaries. The AI model cannot convince or bypass the policy engine, and policy evaluation is mathematically guaranteed.

## ADR-024: Native OS Kernel and Security Controls as Authoritative Enforcers
Status: accepted. Native OS kernels remain the authoritative lower-level security enforcement boundary. SYSTEM MIND X works strictly within native OS entitlements and never disables or weakens native security controls (SIP, Gatekeeper, WDAC, AppArmor).

## ADR-025: Cross-Platform Capability Parity Levels and Adapter Contracts
Status: accepted. Operating systems are fundamentally non-fungible and cannot be flattened into a lowest-common-denominator abstraction. SYSTEM MIND X formalizes a five-tier capability parity hierarchy (LEVEL_1_FULL_PARITY, LEVEL_2_EQUIVALENT_PARITY, LEVEL_3_DEGRADED_PARITY, LEVEL_4_EMULATED_SIMULATED, LEVEL_5_UNSUPPORTED) across eight core domains (FS_OBSERVATION, PROCESS_TELEMETRY, HARDWARE_TELEMETRY, FILE_PROVENANCE, EXECUTION_CONTAINMENT, SYSTEM_SNAPSHOT_ROLLBACK, SYSTEM_PACKAGE_MAINTENANCE, SECURITY_AUTHORITY_ENFORCEMENT). The CapabilityParityEvaluator enforces typed contracts, documented degradation warnings, and mandatory fallback strategies before broker dispatch, ensuring zero capability hallucination or security dilution.
