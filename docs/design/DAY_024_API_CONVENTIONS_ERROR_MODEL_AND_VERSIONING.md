# DAY 024 — Architecture Design Note: API Conventions, Error Model and Versioning Strategy

**Component:** System Architecture, API Conventions & Wire Protocols  
**Layer:** Layer 7 (Application & Presentation) down through Layer 2 (Capability Broker & Adapters)  
**Date:** 2026-11-15  
**Author:** Principal Software Architect & SYSTEM MIND Core Team  
**Status:** Approved for Implementation  

---

## 1. Executive Summary & Problem Formulation

In a multi-process, cross-platform architecture spanning a high-level cognitive plane (Python AI reasoning), a narrow privileged broker (Rust system daemon), desktop UI (Tauri/React), and native kernel sensors (macOS EndpointSec/APFS, Windows ETW/WDAC, Linux eBPF/Landlock), ad-hoc IPC messaging causes three fatal failures:
1. **Ambiguous Error Semantics**: Unstructured exceptions or raw integer error codes fail to differentiate between client mistakes (e.g. invalid syntax), non-negotiable policy denials (e.g. charter invariant breach), and operational failures (e.g. precondition failure, hypervisor timeout).
2. **Credential and Trace Leakage in Error Payloads**: Unchecked stack traces and exception strings inadvertently capture passwords, API keys, private document snippets, or internal memory pointers, creating serious privacy and security leaks.
3. **Silent Version Skew and Breaking Changes**: Desynchronized updates between the frontend UI, Python control plane, and Rust broker lead to serialization crashes, dropped fields, or unexpected semantic drift.

**The SYSTEM MIND Solution:**  
SYSTEM MIND X establishes unified **API Conventions**, an RFC 7807-inspired **Structured Error Model**, and a strict **Semantic Versioning Strategy (SemVer 2.0.0)**:
- Standardized typed Request and Response Envelopes (`ApiRequest`, `ApiResponse`) with unique request IDs, URN-based routing, caller identity headers, and mandatory idempotency keys for mutating actions.
- Categorized error codes with explicit remediation hints, retryability flags, and mandatory secret redaction.
- SemVer 2.0.0 negotiation ensuring backwards compatibility and documented deprecation cycles across all execution planes.

---

## 2. API Request & Response Wire Envelopes

```
CLIENT / CALLER (UI, CLI, AI Planner)
                 |
                 | ApiRequest Envelope
                 v
+-----------------------------------------------------------------------------+
|                               API REQUEST                                   |
| - request_id: UUIDv4                                                        |
| - api_version: "1.0.0"                                                      |
| - method_urn: "system_mind.<domain>.<action>"                              |
| - caller_identity: ActorIdentity                                            |
| - idempotency_key: UUID / Hash (Mandatory for mutating methods)             |
| - timestamp_iso: ISO 8601 UTC                                               |
| - params: Strongly Typed Dictionary                                         |
+-----------------------------------------------------------------------------+
                                 |
                                 v
                 [ DISPATCH & POLICY VERIFICATION ]
                                 |
                                 v
+-----------------------------------------------------------------------------+
|                               API RESPONSE                                  |
| - request_id: (Echoes client request_id)                                    |
| - api_version: "1.0.0"                                                      |
| - status: SUCCESS | CLIENT_ERROR | SERVER_ERROR | POLICY_REJECTED           |
| - data: Optional[TypedResult]                                               |
| - error: Optional[ApiErrorDetail] (RFC 7807-structured)                     |
| - audit_event_id: Optional[str] (Audit Ledger Receipt Link)                 |
| - duration_ms: float                                                        |
| - warnings: List[str] (e.g. Deprecation warnings, degraded parity notices)  |
+-----------------------------------------------------------------------------+
```

---

## 3. Standardized Error Taxonomy (RFC 7807 Inspired)

Errors are strongly typed (`ApiErrorDetail`) and categorized into deterministic ranges:

| Error Code Range | Category | Description | Example Error Code |
| :--- | :--- | :--- | :--- |
| **`E1000..E1999`** | `AUTH_AND_IDENTITY` | Authentication failure, invalid session, unverified actor identity. | `E1001_UNAUTHENTICATED_IDENTITY` |
| **`E2000..E2999`** | `GOVERNANCE_CHARTER_INVARIANT`| Non-negotiable charter rule violation (SC-01 to SC-08); strictly non-retryable. | `E2001_CHARTER_INVARIANT_BREACH` |
| **`E3000..E3999`** | `PRECONDITION_FAILURE` | System readiness check failed (disk space, AC power, snapshot missing). | `E3002_INSUFFICIENT_STORAGE` |
| **`E4000..E4999`** | `BROKER_EXECUTION` | Privileged broker failure, entitlement missing, execution timeout. | `E4003_BROKER_TIMEOUT` |
| **`E5000..E5999`** | `POSTCONDITION_AND_ROLLBACK` | Post-execution verification failed; rollback contract executed. | `E5001_POSTCONDITION_FAILED_ROLLED_BACK` |
| **`E6000..E6999`** | `PLATFORM_ADAPTER` | Platform capability unsupported or degraded on current OS. | `E6002_CAPABILITY_UNSUPPORTED` |
| **`E7000..E7999`** | `SYSTEM_INTERNAL` | Serialization error, internal bug, unexpected exception. | `E7001_INTERNAL_SERVER_ERROR` |

### Error Detail Fields
- **`code`**: Machine-readable error enum string.
- **`category`**: High-level classification enum.
- **`message`**: Clear, non-technical explanation for users and operators.
- **`target`**: Target entity, field, or method causing the failure.
- **`remediation_hint`**: Concrete, actionable guidance explaining how to resolve the error.
- **`is_retryable`**: Boolean indicating whether the caller can safely retry the request.
- **`details`**: Sanitized diagnostic dictionary (secrets strictly redacted).

---

## 4. Semantic Versioning & Compatibility Strategy

SYSTEM MIND X strictly adheres to **Semantic Versioning 2.0.0**:
$$\text{Version} = \text{MAJOR} . \text{MINOR} . \text{PATCH}$$

1. **Major Version Bump (`X.y.z`)**:
   - Incompatible API envelope changes, removal of methods, or changes to mandatory parameters.
   - Requires a minimum 6-month deprecation notice period.
2. **Minor Version Bump (`x.Y.z`)**:
   - Backwards-compatible additions: new method URNs, optional parameters, or new response fields.
3. **Patch Version Bump (`x.y.Z`)**:
   - Backwards-compatible bug fixes and internal performance optimizations.

### Version Negotiation Protocol
When a client sends an `ApiRequest`, the server evaluates version compatibility:
- **`COMPATIBLE`**: Client major == Server major AND Client minor <= Server minor.
- **`INCOMPATIBLE_MAJOR`**: Client major != Server major. Request rejected with `E1005_API_VERSION_MISMATCH`.
- **`INCOMPATIBLE_CLIENT_NEWER`**: Client minor > Server minor (client requests features not yet supported by server).
- **`DEPRECATION_WARNING`**: If the requested method is scheduled for removal in the next major version, a `warning` header is returned with the migration path.
