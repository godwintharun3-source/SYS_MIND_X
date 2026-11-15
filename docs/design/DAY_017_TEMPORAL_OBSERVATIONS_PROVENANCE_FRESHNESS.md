# Design Note: Day 017 — Temporal Observations, Provenance and Freshness Metadata

- **Date:** 2026-11-15
- **Author:** Principal Software Architect
- **Status:** Draft / Awaiting Review
- **Component:** Temporal Digital Twin (Layer 4) / Temporal Observations & Freshness / ADR-027
- **Milestone:** Milestone 2: Requirements and Architecture Specification (Days 011–025)

---

## 1. Overview & Problem Statement

A digital twin that records only instantaneous static state is vulnerable to **temporal desynchronization**:
1. **The Staleness Trap**: A process or file may change milliseconds after an observation. If an agent executes an administrative action against an entity whose state is minutes old (e.g. killing a recycled PID or modifying an already updated configuration), severe collateral damage occurs.
2. **The Provenance Vacuum**: Without cryptographic provenance, an agent cannot distinguish between kernel-authoritative telemetry (e.g. eBPF / FSEvents) and unverified user-space claims, leaving the system susceptible to telemetry spoofing.
3. **Loss of Historical Causality**: Without a chronological observation log, diagnosing how the system drifted into an erroneous state or performing automated compensation rollback is impossible.

SYSTEM MIND X resolves these challenges by augmenting the Digital Twin Graph with **Temporal Observations, Cryptographic Provenance, and Bounded Freshness Enforcement**.

---

## 2. Temporal Architecture & Dataflow

```
+---------------------------------------------------------------------------------------------------------+
|                                TEMPORAL OBSERVATION & FRESHNESS LIFECYCLE                               |
+---------------------------------------------------------------------------------------------------------+
|                                                                                                         |
|  [OBSERVATION EVENT]                                                                                    |
|  Native Telemetry / Sensor / Event (ENG-01, ENG-09)                                                     |
|          │                                                                                              |
|          ▼                                                                                              |
|  [TEMPORAL OBSERVATION]                                                                                 |
|  - observation_id: urn:twin:obs:20261115-001                                                            |
|  - entity_id: urn:twin:proc:4012                                                                        |
|  - timestamp: 2026-11-15T21:05:00.123456Z                                                              |
|  - observation_seq: 142 (Monotonically increasing)                                                      |
|  - provenance: source=ENG-01, collector=libproc, hash=SHA256(...), status=VERIFIED_KERNEL              |
|  - freshness: ttl=5.0s, max_staleness=1.0s, last_verified=21:05:00Z                                      |
|          │                                                                                              |
|          ├──► Append to [TEMPORAL TIMELINE STORE] (Point-in-time reconstruction & state diffing)        |
|          │                                                                                              |
|          ▼                                                                                              |
|  [FRESHNESS EVALUATOR]                                                                                  |
|  Time Delta (now - observed_at):                                                                        |
|  ├── delta <= ttl/2          ──► Status: FRESH                                                          |
|  ├── ttl/2 < delta <= ttl    ──► Status: AGING (Valid, but refresh recommended)                         |
|  ├── ttl < delta <= max_stale──► Status: STALE (Forbidden for critical mutations without re-check)      |
|  └── delta > max_stale       ──► Status: EXPIRED / TOMBSTONE                                            |
|                                                                                                         |
+---------------------------------------------------------------------------------------------------------+
```

---

## 3. Core Temporal Constructs

### 3.1 Observation Types (`ObservationType`)
- `STATE_SNAPSHOT`: Full state capture of an entity at a discrete point in time.
- `ATTRIBUTE_DELTA`: Incremental update recording only mutated attributes.
- `LIFECYCLE_EVENT`: Discrete transition event (e.g. `PROCESS_SPAWNED`, `PROCESS_EXITED`, `FILE_DELETED`).
- `HEARTBEAT`: Proof of liveness without attribute mutations.
- `SECURITY_ATTESTATION`: Periodic cryptographic audit or security posture validation.

### 3.2 Provenance Verification Status (`ProvenanceStatus`)
- `VERIFIED_KERNEL`: Collected via authoritative kernel interface (e.g. eBPF, FSEvents, ETW, auditd).
- `VERIFIED_BROKER`: Collected via narrow privileged broker execution receipt.
- `UNVERIFIED_USER_SPACE`: Collected via unprivileged user-space inspection (e.g. `ps`, `which`).
- `SYNTHETIC_TEST`: Emulated or mock fixture for automated testing.

### 3.3 Freshness States (`FreshnessState`)
- `FRESH`: Observation is within initial freshness window; safe for immediate policy evaluation and execution.
- `AGING`: Observation is nearing expiration; valid for read operations, but refresh recommended before critical actions.
- `STALE`: Observation exceeds TTL; hard-rejected for consequential mutations without live re-observation.
- `EXPIRED`: Observation is invalid; state cannot be relied upon.
- `TOMBSTONED`: Entity has been destroyed or uninstalled (e.g. process terminated, file unlinked).

---

## 4. Cardinal Invariants of Temporal Observations

1. **Strict Monotonic Sequencing:**
   $$\forall o_1, o_2 \in \text{EntityTimeline}(E): \text{seq}(o_2) > \text{seq}(o_1) \implies t(o_2) \ge t(o_1)$$
   Observations for any entity must maintain strictly increasing sequence numbers.

2. **Cryptographic Payload Integrity:**
   Every temporal observation must record the cryptographic SHA-256 digest of its state payload:
   $$\text{payload\_hash} = \text{SHA256}(\text{canonical\_json}(\text{observed\_state}))$$

3. **Staleness Guard on Mutating Dispatches:**
   $$\text{ActionRisk} \ge \text{MEDIUM\_IMPACT} \implies \text{TargetEntityFreshness} \in \{\text{FRESH}, \text{AGING}\}$$
   Any planned operation of Medium impact or above must verify that target entities are not `STALE` or `EXPIRED`. Dispatches against stale state are blocked by the policy engine.

4. **Immutable Historical Timeline:**
   Historical observations are append-only. Existing observation records can never be mutated or backdated.

---

## 5. Architectural Decision Record (ADR-027)

- **Title:** Temporal Observations, Cryptographic Provenance, and Bounded Freshness Enforcement
- **Status:** Accepted.
- **Context:** Classical system automation fails when operations are executed against stale or unverified host state.
- **Decision:** SYSTEM MIND X implements an append-only `TemporalTimelineStore` in Layer 4 with strongly typed observations, SHA-256 payload integrity hashing, provenance verification tiers, and deterministic freshness lifecycle evaluation (`FRESH` to `EXPIRED`). The policy engine blocks consequential actions targeting stale entities.
- **Consequences:** Eliminates time-of-check to time-of-use (TOCTOU) desynchronization; guarantees forensic traceability for all state transitions; enables historical state diffing and recovery point selection.
