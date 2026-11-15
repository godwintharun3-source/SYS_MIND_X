# Design Note: Day 014 — Architecture Decision Records for the AI and Native System Split

- **Date:** 2026-11-15
- **Author:** Principal Software Architect
- **Status:** Draft / Awaiting Review
- **Component:** Core Architecture / AI & Native System Split / ADR-021..024
- **Milestone:** Milestone 2: Requirements and Architecture Specification (Days 011–025)

---

## 1. Overview & Problem Statement

Current computer-use agents and AI-native operating systems suffer from a fatal architectural flaw: **the ambient authority collapse**. In typical agent frameworks, the LLM is given direct access to a bash/powershell process or a visual GUI virtual mouse/keyboard with unrestricted ambient user permissions. When an adversarial prompt injection is encountered (e.g., hidden instructions in a downloaded README or webpage), the LLM executes destructive, unmediated commands directly against the operating system.

SYSTEM MIND X eliminates this vulnerability by enforcing a **strict, non-negotiable physical and logical split** between the **AI Cognitive Plane** and the **Native Operating System**:

```
+------------------------------------------------------------------------------------+
|                               THE AI / NATIVE SYSTEM SPLIT                         |
+------------------------------------------------------------------------------------+
|                                                                                    |
|  [UNTRUSTED USER-SPACE REALM]                                                      |
|  Plane 1: AI Cognitive Planning Plane (Layer 2)                                    |
|  - Role: Multimodal planner, explainer, intent decomposer                          |
|  - Privilege: Strictly unprivileged user process                                   |
|  - Output: Strongly typed declarative ActionContracts ONLY                        |
|                                         │                                          |
|                                         ▼ (Declarative Contract)                   |
|  [DETERMINISTIC FIREWALL REALM]                                                    |
|  Plane 2: Independent Policy Engine (Layer 3)                                      |
|  - Role: Invariant verification, charter rules, persona envelopes                 |
|  - Privilege: Deterministic pure function (Non-LLM logic)                          |
|  - Output: VerifiedCapabilityGrant (Cryptographically validated)                   |
|                                         │                                          |
|                                         ▼ (Verified Capability Grant)              |
|  [NATIVE LEAST-PRIVILEGE BROKER REALM]                                             |
|  Plane 3: Narrow Privileged Execution Broker (Layer 5)                             |
|  - Role: Pre/post assertions, atomic rollback handlers, audit hashing             |
|  - Privilege: Narrow broker daemon (Least privilege required for action)          |
|  - Output: BrokerExecutionReceipt + Provenance Records                             |
|                                         │                                          |
|                                         ▼ (Typed System API Calls)                 |
|  [AUTHORITATIVE KERNEL & HARDWARE REALM]                                           |
|  Plane 4: Native OS Kernel & Physical Hardware (Layer 7)                           |
|  - Role: Authoritative security enforcement (SIP, Gatekeeper, WDAC, Landlock)      |
|  - Privilege: Kernel / Supervisor / TPM                                            |
|                                                                                    |
+------------------------------------------------------------------------------------+
```

---

## 2. Formal Architecture Decision Records (ADR-021 to ADR-024)

### ADR-021: AI Cognitive Plane as an Untrusted Planner Isolated in User Space
- **Status:** Accepted.
- **Context:** Running LLM code generation or raw shell commands with ambient credentials creates fatal prompt injection and hallucination risks.
- **Decision:** The AI cognitive plane (multimodal reasoning, LLM explainer, planning context) is classified as an untrusted planner. It executes in unprivileged user space, possesses zero OS mutation rights, has no direct IPC socket to the execution broker, and can only communicate outward by generating strongly typed declarative `ActionContract`s.
- **Consequences:** All actions require downstream policy validation; prompt injection attacks cannot directly trigger native OS system calls.

### ADR-022: Narrow Privileged Execution Broker with Cryptographic Provenance and Atomic Rollback
- **Status:** Accepted.
- **Context:** Direct execution of administrative or mutating actions without pre/post checks or rollback plans causes irreversible state drift.
- **Decision:** All state modifications are dispatched through a narrow execution broker daemon that accepts only `VerifiedCapabilityGrant` tokens from the policy engine. The broker validates pre-conditions, enforces atomic rollback compensation handlers on post-condition failure, and generates immutable SHA-256 audit receipts.
- **Consequences:** Eliminates ambient shell authority; guarantees fault-tolerant recovery for reversible operations.

### ADR-023: Deterministic Non-LLM Invariant Firewall as the Authority Gate
- **Status:** Accepted.
- **Context:** Security enforcement cannot rely on LLM self-evaluation or natural-language system prompts, as LLM reasoning can be subverted via jailbreaking or context confusion.
- **Decision:** An independent, deterministic policy engine implemented in verified code evaluates every proposed contract against inviolable charter invariants, component ownership models, and persona boundaries. It operates strictly outside LLM weights.
- **Consequences:** The AI cannot convince the policy engine to bypass a rule; security boundaries remain deterministic and mathematically verifiable.

### ADR-024: Native Operating System Kernel and Security Controls as Authoritative Enforcers
- **Status:** Accepted.
- **Context:** Platform-level security mechanisms (SIP, Gatekeeper, WDAC, AppArmor) provide hardware-backed roots of trust that must not be subverted.
- **Decision:** Native OS security controls remain the authoritative lower-level security enforcement boundary. SYSTEM MIND X works strictly within native platform entitlements and never attempts to disable, weaken, or bypass native OS security mechanisms.
- **Consequences:** Protects developer host stability; ensures compatibility with enterprise endpoint security policies.

---

## 3. Four Cardinal Invariants of the Split

1. **No Ambient Root / Shell Execution:**
   $$\text{Caller} = \text{AI\_PLANE} \implies \text{ActionType} \ne \text{"raw\_shell"} \land \text{Privilege} = \text{UNPRIVILEGED}$$

2. **Mandatory Policy Engine Intermediation:**
   $$\text{BrokerExecution}(\text{contract}) \iff \text{PolicyEngine}(\text{contract}) = \text{PERMITTED}$$

3. **Cryptographic Audit Provenance:**
   Every broker execution must record $\text{SHA256}(\text{pre\_state}) \mathbin{\Vert} \text{SHA256}(\text{post\_state}) \mathbin{\Vert} \text{SessionID}$.

4. **Native Security Non-Bypass:**
   Zero execution contracts targeting `csrutil disable`, `setenforce 0`, or Gatekeeper bypasses.
