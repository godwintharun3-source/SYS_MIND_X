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
