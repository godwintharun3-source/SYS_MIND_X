# DAY 035 — Architecture Design Note: Structured Logging with Sensitive-Data Redaction

**Component:** Structured Logging Subsystem & Automated Redaction Engine  
**Layer:** Cross-Cutting Observability, Security & Audit  
**Date:** 2026-11-16  
**Author:** Principal Software Architect & SYSTEM MIND Core Team  
**Status:** Approved for Implementation  

---

## 1. Executive Summary & Purpose

Today establishes the **Structured Logging with Sensitive-Data Redaction Subsystem**, fulfilling the Day 035 objective of Milestone 3 (Repository and development foundation, Days 026–040).

In a safety-critical operating system architecture, unstructured text logs and unmediated print statements create severe security vulnerabilities:
1. **Accidental Credential Leakage**: Unsanitized parameters, stack traces, and API responses frequently expose bearer tokens, private keys, passwords, and user identifiers.
2. **Parsing Ambiguity**: Free-form text lines impede automated anomaly detection, forensic audits, and SIEM integration.
3. **Missing Correlation Context**: Without distributed trace IDs and structured execution context, asynchronous event causality across frontend, control plane, and broker daemon cannot be reconstructed.

To resolve these risks at the repository foundation:
- **Canonical JSON Structure**: Every log record emits a single-line, schema-compliant JSON object containing standardized observability fields (`timestamp_iso`, `level`, `subsystem`, `event`, `trace_id`, `span_id`, `context`).
- **Multi-Tier Defense-in-Depth Redaction**:
  - `SensitiveDataRedactingFilter`: Sanitizes record messages, positional arguments, and structured context in-place before handlers process them.
  - `StructuredJsonFormatter`: Deeply scrubs nested dictionaries, lists, and exception tracebacks using regex key-matching and pattern scanners.
- **Contextual Bound Logger**: `StructuredLogger` providing clean, ergonomic API (`logger.bind(**context)`) with immutable context propagation.
- **Polyglot Rust Support**: Standardized structured log record formatter in `system-mind-common` with sensitive field redaction.
- **Programmatic CI Gate**: `LoggingConfigValidator` auditing logging subsystem integrity, redactor presence, and zero secret leakage.

---

## 2. Structured Log Event Schema

Each structured log entry is serialized as a single-line JSON document:

```json
{
  "timestamp_iso": "2026-11-16T13:45:00.123456Z",
  "level": "INFO",
  "subsystem": "system_mind.twin",
  "event": "entity_state_updated",
  "trace_id": "trace-uuid-12345",
  "span_id": "span-67890",
  "context": {
    "entity_id": "entity:sys:macos",
    "ownership": "SYSTEM_MANAGED",
    "auth_token": "[REDACTED_SECRET]",
    "cpu_usage_pct": 14.2
  },
  "exception": null
}
```

---

## 3. Sensitive Data Redaction Rules

| Target | Detection Mechanism | Action |
|---|---|---|
| **Sensitive Key Names** | Case-insensitive regex: `password`, `passwd`, `token`, `secret`, `api_?key`, `credential`, `private_?key`, `auth`, `bearer`, `cookie`, `session_?id` | Value replaced with `"[REDACTED_SECRET]"` |
| **Cryptographic Headers** | Regex: `-----BEGIN [A-Z ]*PRIVATE KEY-----` | Entire block replaced with `"[REDACTED_SECRET]"` |
| **API Token Prefixes** | Regex: `ghp_`, `gho_`, `sk-ant-`, `sk-`, `AIzaSy`, `AKIA` | Token matched and replaced with `"[REDACTED_SECRET]"` |
| **Bearer Headers** | Regex: `Bearer eyJ...` or `Bearer <token>` | Header token replaced with `"[REDACTED_SECRET]"` |
| **Exception Tracebacks** | Sanitized line-by-line using `SecretRedactor` | In-flight parameters and local frames scrubbed |

---

## 4. Repository Layout for Logging Subsystem

```
SYSTEM_MIND_ANTIGRAVITY_365_DAY_PACK/
├── src/system_mind/logging/
│   ├── __init__.py                            # Public logging exports
│   ├── formatter.py                           # StructuredJsonFormatter with deep redaction
│   ├── filter.py                              # SensitiveDataRedactingFilter
│   └── logger.py                              # StructuredLogger & LoggerFactory (get_logger)
├── crates/system-mind-common/
│   └── src/logging.rs                         # Rust StructuredLogRecord with secret masking
├── src/system_mind/packaging/
│   └── logging_config.py                      # LoggingConfigValidator for CI quality gates
└── tests/
    └── test_structured_logging.py            # Comprehensive unit and integration test suite
```

---

## 5. Verification & Acceptance Criteria

1. Structured logging produces strictly valid, single-line JSON logs with required keys.
2. All sensitive keys and credential patterns are scrubbed automatically without developer intervention.
3. Exception tracebacks containing sensitive tokens are sanitized before emission.
4. Bound loggers (`logger.bind(...)`) immutably propagate correlation and trace IDs.
5. Rust structured logging in `system-mind-common` redacts sensitive fields and verifies formatting.
6. `LoggingConfigValidator` passes clean repository audit and flags unredacted or malformed loggers.
7. All 289+ existing tests pass with zero regressions.
