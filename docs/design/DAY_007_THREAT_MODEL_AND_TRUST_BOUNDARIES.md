# Design Note: Day 007 — Threat Model & Trust Boundaries

- **Date:** 2026-11-14
- **Author:** Principal Software Architect
- **Status:** Draft / Awaiting Review
- **Component:** Security / Threat Modeling / Trust Boundaries

---

## 1. Overview & Security Philosophy

An AI computer operator with ambient OS interaction capabilities creates an unprecedented threat landscape. Traditional software vulnerabilities (buffer overflows, SQL injection) are compounded by AI-specific attack vectors: **indirect prompt injection**, **semantic goal hijacking**, **hallucinated privilege escalation**, and **silent privacy exfiltration**.

SYSTEM MIND X applies a **Zero-Trust Defense-in-Depth** model:
1. **The AI Model is an Untrusted Planner:** The AI is never trusted to self-police, evaluate its own permissions, or execute unmediated OS commands.
2. **Independent Deterministic Policy Engine:** Deterministic rule evaluators operating outside LLM weights act as an impenetrable gate.
3. **Narrow Capability Broker:** Consequential execution requires typed contracts, validated preconditions, and cryptographic audit records.
4. **Native OS Kernel Supremacy:** Native security mechanisms (SIP, Gatekeeper, WDAC, Landlock) remain the authoritative lower-level security enforcement boundary.

---

## 2. The Six Trust Zones

SYSTEM MIND X formally partitions system operations into six hierarchical Trust Zones:

```
+------------------------------------------------------------------------------------+
|                                 THE SIX TRUST ZONES                                |
+------------------------------------------------------------------------------------+
| Zone 0: UNTRUSTED EXTERNAL    | Internet, external downloads, remote repositories  |
|                               v                                                    |
| Zone 1: USER WORKSPACE        | User apps, local files, developer project trees    |
|                               v                                                    |
| Zone 2: AI CONTROL PLANE      | Multimodal planner, LLM reasoning, context engine  |
|                               v  (Typed Contract Only - NEVER direct kernel access)|
| Zone 3: DETERMINISTIC POLICY  | Non-LLM rule validator, invariant checker, schemas |
|                               v  (Verified Capability Grant)                       |
| Zone 4: PRIVILEGED BROKER     | Narrow least-privilege daemon, atomic rollbacks    |
|                               v  (Native OS API Calls)                             |
| Zone 5: KERNEL & HARDWARE     | Native OS Kernel (XNU/NT/Linux), SIP, WDAC, TPM    |
+------------------------------------------------------------------------------------+
```

### Trust Zone Invariants:
- **Rule of Strict Adjacency:** Transition from Zone 2 (AI Control Plane) directly to Zone 4 (Privileged Broker) or Zone 5 (Kernel) is **physically and logically impossible**. All requests from Zone 2 must pass through Zone 3 (Independent Deterministic Policy Engine).
- **Rule of Non-Execution of Zone 0:** Untrusted binaries from Zone 0 can never transition directly to Zone 1 or Zone 5 for execution. They must be routed to isolated containment (disposable micro-VM or read-only viewer).

---

## 3. STRIDE Threat Analysis for AI-Native Computer Operations

| STRIDE Category | Threat Description & Attack Vector | Impact | SYSTEM MIND X Countermeasure |
| :--- | :--- | :--- | :--- |
| **Spoofing (S)** | Attacker spoofs an approved user action contract or crafts a forged authorization token. | Unauthorized execution of high-impact action. | Cryptographically signed contracts; session verification; verified process IDs via kernel (`proc_pidinfo`). |
| **Tampering (T)** | Indirect prompt injection in a downloaded README modifies action contract parameters (e.g. injecting shell escapes or altering target path). | Arbitrary file manipulation or rogue command execution. | Strongly typed dataclasses (no raw shell strings); strict path normalization; deterministic policy verification. |
| **Repudiation (R)** | Malicious or buggy action occurs without an audit record linking it to the session and rationale. | Loss of forensic accountability; inability to diagnose fault. | Append-only, immutable audit trail recording: timestamp, actor ID, pre-state hash, post-state hash, and recovery handle. |
| **Information Disclosure (I)**| Telemetry collector or prompt context captures cleartext private data (SSH keys, passwords, personal photos). | Confidentiality breach, credential theft. | Privacy exclusion perimeters (`~/.ssh`, `~/.gnupg`, `~/Documents`, `.env`); zero continuous OCR screen recording. |
| **Denial of Service (D)**| Runaway autonomous maintenance consumes 100% CPU, exhausts disk space, or restarts vital network daemons. | Host instability, battery drain, workflow disruption. | Resource ceilings via cgroups v2; execution timeouts; pre-flight checks verifying system idle and AC power. |
| **Elevation of Privilege (E)**| AI attempts to execute `sudo`, load kernel extensions, or bypass SIP/WDAC protections. | Full system compromise; host operating system subversion. | The AI is unprivileged; raw root/shell commands are hard-rejected by `CharterValidator`; broker accepts only typed contracts. |

---

## 4. Threat Vectors Catalog

1. **THREAT-01 (Elevation of Privilege - Raw Shell Execution):** Attacker or hallucinating LLM generates raw shell commands with ambient root/sudo rights. *Mitigation:* Hardcoded rejection in `CharterValidator` (Invariant 1).
2. **THREAT-02 (Tampering - Indirect Prompt Injection):** Untrusted document contains instructions directing the agent to modify system settings. *Mitigation:* The policy engine evaluates actions independently of LLM reasoning against strict invariant schemas.
3. **THREAT-03 (Information Disclosure - Secret Key Exfiltration):** Diagnostic collector attempts to read SSH keys or `.env` files into prompt context. *Mitigation:* Pattern matching against `excluded_privacy_paths` blocks access in `PersonaPolicyEvaluator`.
4. **THREAT-04 (Repudiation - Unaudited State Change):** State change executed without audit trail. *Mitigation:* `JourneyExecutionEngine` mandates immutable audit records for every step transition.
5. **THREAT-05 (Tampering - Component Ownership Clobbering):** Autonomous updater silently updates user applications or developer virtualenvs. *Mitigation:* Hardcoded non-interference invariant on `USER_MANAGED` components.
6. **THREAT-06 (Denial of Service - Uncontained Untrusted File Execution):** Malware binary executed natively on host OS. *Mitigation:* Mandatory zero-trust containment (`DISPOSABLE_ISOLATION` or `HARDENED_VIEWER`).
7. **THREAT-07 (Spoofing - Action Contract & Session Forgery):** Malicious prompt injection or rogue sub-agent crafts a forged action contract claiming user-explicit consent. *Mitigation:* Cryptographic contract signing, session ID provenance verification, and mandatory interactive user consent gates.
