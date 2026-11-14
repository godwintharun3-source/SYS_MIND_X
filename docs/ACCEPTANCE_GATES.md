# First-Release Acceptance Gates & Research Questions

Release and daily gate approval requirements for SYSTEM MIND X. A feature, milestone, or release is not complete until all eight gates pass.

---

## 1. The Eight Release Acceptance Gates

| Gate ID | Gate Name | Required Verification & Standard | Failure Condition |
| :--- | :--- | :--- | :--- |
| **AG-01** | **Functional Completeness** | Requirement is fully implemented with strongly typed action contracts, defined inputs, outputs, error states, and demonstrable behavior. | Speculative stubs, unhandled error states, missing contract types. |
| **AG-02** | **Tests & Regression Pass** | All unit, contract, integration, and benchmark tests pass with 100% success rate. Real results reported honestly. | Any failing test, mocked success where real tests are required, fabricated test counts. |
| **AG-03** | **Security & Trust Boundaries** | Adheres strictly to Six Trust Zones (Zone 0–Zone 5), the Rule of Strict Adjacency, and all eight Explicit Safety Constraints (SC-01 to SC-08). | Direct Zone 2 -> Zone 4/5 bypass, uncontained Zone 0 execution, raw root/shell commands. |
| **AG-04** | **Reliability & Rollback** | Preconditions and postconditions verified for all actions. Reversible operations must specify an executable rollback plan or snapshot strategy. | Irreversible state mutation without explicit user confirmation; missing rollback handlers. |
| **AG-05** | **Platform Matrix Verification** | Every platform capability is explicitly labeled `SUPPORTED`, `PARTIAL`, or `UNSUPPORTED`. Uncertified platforms are rejected by policy. | Unsupported capability labeled as complete; bypassing OS security mechanisms. |
| **AG-06** | **Documentation & Architecture** | Complete engineering design notes in `docs/design/`, updated API references, and architecture decisions recorded in `docs/DECISION_LOG.md`. | Undocumented architectural changes; missing design notes; outdated state files. |
| **AG-07** | **Evidence & Secret Redaction** | Real test outputs, hashes, and execution artifacts recorded in repository state. All credentials (`~/.ssh`, `.env`, tokens) strictly redacted. | Secrets leaked in logs, test output, or prompts; missing execution proof. |
| **AG-08** | **Human Review & Day Gate** | Human engineer reviews the Git diff and test evidence before confirming completion via the day tracker (`--reviewed`). | Automated self-advancement of the day tracker without human review. |

---

## 2. Inviolable Gate Invariants

1. **No Unsupported Feature Merged:** No capability may be labeled complete until verified on certified hardware.
2. **Scan != Safe Invariant:** No file scan can be documented as a guarantee of safety.
3. **User-App Segregation:** No user application update may be included in the OS maintenance scope.
4. **Zero Ambient Authority:** The AI planner must never be granted ambient root or shell rights.
5. **Mandatory Human Sign-off:** The day tracker cannot advance without human review confirmation (`--reviewed`).
