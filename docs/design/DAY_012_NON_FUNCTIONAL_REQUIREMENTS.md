# Design Note: Day 012 — Non-Functional Requirements for Reliability, Privacy, and Performance

- **Date:** 2026-11-15
- **Author:** Principal Software Architect
- **Status:** Draft / Awaiting Review
- **Component:** Core Architecture / Non-Functional Requirements (NFR)
- **Milestone:** Milestone 2: Requirements and Architecture Specification (Days 011–025)

---

## 1. Overview & Non-Functional Quality Framework

For a safety-critical computer-operation platform with autonomous ambient capabilities, non-functional requirements (NFRs) are not aspirational guidelines—they are **quantifiable engineering invariants**. If an agent is slow, users disable it; if an agent consumes excessive CPU or battery, users terminate it; if an agent leaks a single credential or clobbers a user file, the system is fundamentally disqualified.

SYSTEM MIND X establishes precise, machine-measurable thresholds across four critical quality dimensions:
1. **Reliability & Availability (REL):** Deterministic state recovery, crash tolerance, atomic rollbacks, and pre/post validation.
2. **Privacy & Confidentiality (PRIV):** Zero cleartext secret leakage, zero ambient screen scraping, local-first offline operation, and cryptographic auditability.
3. **Performance & Resource Limits (PERF):** Sub-millisecond policy evaluation, bounded memory footprint, sub-half-percent idle CPU, and low-latency digital twin convergence.
4. **Safety & Non-Interference (SAFE):** Absolute non-interference with user workspaces and mandatory zero-trust isolation for untrusted binaries.

---

## 2. Quantitative Non-Functional Requirements Matrix

| NFR ID | Category | Title | Target Threshold | Metric Unit | Operator | Verification Strategy |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **NFR-REL-01** | **Reliability** | Atomic Rollback Convergence | $\le 5000.0$ | Milliseconds | $\le$ | Inject synthetic step failures during multi-step journeys; benchmark duration to restore pre-state. |
| **NFR-REL-02** | **Reliability** | Crash Recovery Convergence | $\le 500.0$ | Milliseconds | $\le$ | Abruptly kill daemon during active WAL writes; measure database recovery and reconciliation time on restart. |
| **NFR-REL-03** | **Reliability** | Daemon Availability Uptime | $\ge 99.99$ | Percentage | $\ge$ | Soak-test host companion and broker daemons under continuous background polling over 72+ hours. |
| **NFR-REL-04** | **Reliability** | Pre/Postcondition Enforcement | $100.0$ | Percentage | $=$ | Audit all broker execution traces for verified pre-check and post-assertion execution. |
| **NFR-PRIV-01** | **Privacy** | Secret Ingestion Redaction | $0.0$ | Count (leaks) | $=$ | Pass synthetic credentials (`id_rsa`, `.env`, tokens) through telemetry collectors; assert 100% redaction. |
| **NFR-PRIV-02** | **Privacy** | Ambient OCR Screen Recording | $0.0$ | Count (frames) | $=$ | Continuous background runtime audit; assert zero OCR frames or raw bitmaps stored on disk. |
| **NFR-PRIV-03** | **Privacy** | Local-First Offline Autonomy | $100.0$ | Percentage | $=$ | Disconnect network interfaces; execute full telemetry, policy evaluation, and maintenance sweeps offline. |
| **NFR-PRIV-04** | **Privacy** | Cryptographic Audit Integrity | $100.0$ | Percentage | $=$ | Verify SHA-256 hash chains across all state modification receipts in event history. |
| **NFR-PERF-01**| **Performance**| Policy Evaluation Latency ($P_{95}$) | $\le 5.0$ | Milliseconds | $\le$ | Benchmark `ENG-04` deterministic contract evaluation under 10,000 synthetic action contracts. |
| **NFR-PERF-02**| **Performance**| Digital Twin Convergence Latency | $\le 50.0$ | Milliseconds | $\le$ | Measure latency from native kernel event emission (FSEvents/ETW/eBPF) to digital twin index commit. |
| **NFR-PERF-03**| **Performance**| Host Agent Memory Ceiling (RSS) | $\le 50.0$ | Megabytes | $\le$ | Monitor RSS footprint of native companion agent during continuous 24-hour operation. |
| **NFR-PERF-04**| **Performance**| Idle CPU Utilization Ceiling | $\le 0.5$ | Percentage | $\le$ | Measure average CPU usage across 10-minute idle monitoring intervals on certified hardware. |
| **NFR-PERF-05**| **Performance**| Broker IPC Overhead | $\le 25.0$ | Milliseconds | $\le$ | Benchmark round-trip IPC latency (contract deserialization, pre-check, execution, post-check, receipt). |
| **NFR-SAFE-01**| **Safety** | User-Managed Non-Interference | $0.0$ | Count (modifications)| $=$ | Run autonomous maintenance sweeps; assert zero modifications to user applications or virtual environments. |
| **NFR-SAFE-02**| **Safety** | Zero-Trust File Isolation | $100.0$ | Percentage | $=$ | Detonate untrusted external binaries; verify 100% confinement in disposable micro-VMs. |

---

## 3. Compliance Evaluation Architecture

The `NfrComplianceEvaluator` programmatically evaluates benchmark measurements against the established thresholds:
```
                      +-----------------------------------------+
                      |         Test / Benchmark Metrics        |
                      +-----------------------------------------+
                                           │
                                           ▼
                      +-----------------------------------------+
                      |          NfrComplianceEvaluator         |
                      |  - Compares measurement vs threshold    |
                      |  - Evaluates comparison operator        |
                      |  - Collects violation diagnostics       |
                      +-----------------------------------------+
                                           │
                                           ▼
                      +-----------------------------------------+
                      |          NfrEvaluationResult            |
                      |  - is_compliant: bool                   |
                      |  - evaluations: Dict[nfr_id, bool]      |
                      |  - violations: List[str]                |
                      +-----------------------------------------+
```
