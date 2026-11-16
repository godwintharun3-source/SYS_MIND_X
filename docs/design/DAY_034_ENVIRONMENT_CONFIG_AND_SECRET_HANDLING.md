# DAY 034 — Architecture Design Note: Environment Configuration and Secret-Handling Conventions

**Component:** Environment Configuration & Secret Masking Architecture  
**Layer:** Cross-Cutting Configuration, Security & Governance  
**Date:** 2026-11-16  
**Author:** Principal Software Architect & SYSTEM MIND Core Team  
**Status:** Approved for Implementation  

---

## 1. Executive Summary & Purpose

Today establishes the **Environment Configuration and Secret-Handling Conventions**, fulfilling the Day 034 objective of Milestone 3 (Repository and development foundation, Days 026–040).

In accordance with the SYSTEM MIND X Product Charter and Security Rules:
> *"Do not store secrets, tokens, passwords or private file contents in logs, telemetry or prompts. Redact secrets and sensitive data from logs and test artifacts."*

To uphold this inviolable charter constraint from the repository foundation:
1. **Environment Separation**: Execution profiles (`DEVELOPMENT`, `TESTING`, `STAGING`, `PRODUCTION`) must be strictly segregated with safe default configurations that bind exclusively to loopback addresses (`127.0.0.1`), mandate non-privileged ports, and enforce strict safety invariants.
2. **Zero-Plaintext Storage Conventions**:
   - `.env.example` provides explicit documentation of configuration parameters with dummy template values and security warnings.
   - Real `.env` and credential files (`*.pem`, `*.key`, `*.pfx`, `id_rsa*`) are strictly excluded in `.gitignore` and audited against accidental commit.
3. **Secret Masking Primitives**:
   - Python: Strongly typed `SecretStr` wrapper that masks secrets in `__str__` and `__repr__` as `"***REDACTED***"`, providing `get_secret_value()` exclusively for validated call sites and `hash_fingerprint()` for audit tracing.
   - Rust: `SecretValue` struct in `system-mind-common` implementing masked `fmt::Debug` and `fmt::Display` (`"[REDACTED]"`).
4. **Secret Leak Detection**:
   - Programmatic scanner (`SecretLeakDetector`) inspecting payloads, environment files, and code for known token formats (`ghp_`, `sk-`, `AIzaSy`, `AKIA...`) and cryptographic private key headers.
5. **Programmatic Audit Validator**:
   - `EnvironmentConfigValidator` in `src/system_mind/packaging/env_config.py` verifying template completeness, gitignore exclusions, and absence of committed secrets.

---

## 2. Configuration Model Architecture

```
SYSTEM_MIND_ANTIGRAVITY_365_DAY_PACK/
├── .env.example                               # Canonical documented environment template
├── .gitignore                                 # Expanded secret and credential exclusion rules
├── src/system_mind/config/
│   ├── __init__.py                            # Clean configuration exports
│   ├── environment.py                         # EnvironmentProfile, SystemMindConfig, ConfigLoader
│   └── secrets.py                             # SecretStr, SecretStore interface, SecretLeakDetector
├── crates/system-mind-common/
│   └── src/secret.rs                          # Rust SecretValue with masked Display/Debug
├── tools/
│   └── check_secrets.py                       # CLI secret leak scanner for developer pre-commit & CI
├── src/system_mind/packaging/
│   └── env_config.py                          # EnvironmentConfigValidator & audit engine
└── tests/
    └── test_environment_config.py            # Comprehensive unit and contract tests
```

---

## 3. Environment Profiles & Parameter Matrix

| Parameter | Type | Default | Constraint / Invariant |
|---|---|---|---|
| `SYSTEM_MIND_ENV` | `EnvironmentProfile` | `DEVELOPMENT` | Enum: `DEVELOPMENT`, `TESTING`, `STAGING`, `PRODUCTION` |
| `SYSTEM_MIND_HOST` | `str` | `127.0.0.1` | Must be loopback (`127.0.0.1` or `::1`) by default. External binding requires explicit override. |
| `SYSTEM_MIND_PORT` | `int` | `8765` | Unprivileged port range (1024–65535). |
| `SYSTEM_MIND_IPC_SOCKET` | `str` | `/tmp/system_mind.sock` | Safe local domain socket path. |
| `SYSTEM_MIND_LOG_LEVEL` | `str` | `INFO` | Enum: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. |
| `SYSTEM_MIND_SECRET_BACKEND` | `SecretStoreBackend` | `MOCK_MEMORY` | Enum: `MOCK_MEMORY`, `ENV_VARS`, `MACOS_KEYCHAIN`, `WINDOWS_CREDENTIAL_MANAGER`, `LINUX_SECRET_SERVICE`. |
| `SYSTEM_MIND_STRICT_INVARIANTS`| `bool` | `True` | Inviolable: Charter invariants (SC-01..SC-08) cannot be disabled. |
| `SYSTEM_MIND_ALLOW_UNTRUSTED` | `bool` | `False` | Inviolable: "Scan != Safe" invariant (SC-03) forbids unrestricted host execution. |

---

## 4. Secret Masking & Redaction Semantics

```python
secret = SecretStr("ghp_super_secret_token_123456789")
print(str(secret))        # "***REDACTED***"
print(repr(secret))       # "SecretStr('***REDACTED***')"
f"{secret}"               # "***REDACTED***"
secret.hash_fingerprint() # Deterministic SHA-256 for audit logging (never logs secret)
secret.get_secret_value() # Returns raw secret string exclusively when explicitly requested
```

---

## 5. Verification & Acceptance Criteria

1. `.env.example` exists with comprehensive comments, placeholder variables, and security warnings.
2. `.gitignore` strictly excludes `.env`, `.env.*.local`, `*.pem`, `*.key`, `*.pfx`, and credential files.
3. `SystemMindConfig` enforces type safety, default loopback binding, and safe configuration inspection.
4. `SecretStr` in Python and `SecretValue` in Rust mask secrets in all formatting, debugging, and logging contexts.
5. `SecretLeakDetector` catches known token patterns and PEM headers.
6. `EnvironmentConfigValidator` audits all configuration and secret safety criteria.
7. All existing and new tests pass across Python and Rust workspaces with zero regressions.
