# DAY 052: Read-Only macOS Application Signatures and Notarization Telemetry Architecture

## Executive Summary
In macOS, binary trust and integrity verification rest upon Darwin's cryptographic Code Signing subsystem and Gatekeeper Notarization services. A valid cryptographic code signature guarantees that an application has not been altered since it was sealed by its developer, while Gatekeeper notarization confirms that Apple's automated malware analysis verified the binary before distribution.

In strict alignment with the SYSTEM MIND X charter—specifically `SC-01` (Zero Ambient Shell Authority), the non-negotiable principle that **"Scan != Safe"** (a valid signature or clean scan does not prove a binary is safe), and read-only unprivileged operation—Day 052 establishes a passive signature inspection engine.

This component inspects application bundles (`.app`) using native Darwin tools (`/usr/bin/codesign` and `/usr/sbin/spctl`), extracts certificate authority chains, Developer Team Identifiers, CodeDirectory hashes (CDHash), Hardened Runtime flags, and Gatekeeper notarization verdicts, providing essential provenance evidence for the Temporal Digital Twin without executing untrusted code or mutating host security controls.

---

## 1. Cryptographic Trust & Provenance Architecture

macOS establishes code provenance through hierarchical cryptographic structures:

1. **CodeDirectory & CDHash**:
   - The CodeDirectory contains SHA-256 digests of every code page and executable segment in the Mach-O binary.
   - The `CDHash` (digest of the CodeDirectory itself) uniquely and deterministically identifies the precise binary revision.
2. **Certificate Authority Chains**:
   - **Apple System**: `macOS Software Signing` -> `Apple Code Signing Certification Authority` -> `Apple Root CA`.
   - **Identified Developer**: `Developer ID Application: <Developer Name> (<Team ID>)` -> `Developer ID Certification Authority` -> `Apple Root CA`.
   - **Mac App Store**: `Apple Mac OS Application Signing` -> `Apple Worldwide Developer Relations CA` -> `Apple Root CA`.
   - **Ad-Hoc**: Self-signed with identity `-` (no root CA anchor).
   - **Unsigned**: No code signature embedded in Mach-O headers or resource forks.
3. **Hardened Runtime (`runtime` flag `0x10000`)**:
   - Protects applications against memory corruption, dylib hijacking, and unauthorized code injection.
4. **Gatekeeper Assessment & Notarization**:
   - Evaluated via `spctl --assess --type execute --verbose <path>`.
   - Identifies whether Apple has signed a notarization ticket (either stapled to the bundle or cached in CloudKit) confirming automated security checks passed.
5. **The Non-Negotiable Charter Invariant: "Scan != Safe"**:
   - Code signing proves **authenticity** (who built it) and **integrity** (it was not modified in transit).
   - It does **not** prove the application is safe, non-malicious, or free of design flaws.
   - All models explicitly maintain `scan_proves_safe = False`.

---

## 2. Invariants & Safety Guarantees

| Invariant | Description | Verification Method |
|---|---|---|
| `SC-01` / `INV-SIG-01` | **Zero Ambient Shell Authority**: All subcommands (`codesign`, `spctl`) execute using tokenized argument vectors (`shell=False`) with strict timeouts (<= 5s). | AST static check & unit tests |
| `INV-SIG-02` | **Strictly Read-Only / Zero Mutation**: No signature manipulation (`codesign --sign`, `codesign --remove-signature`), no Gatekeeper disabling (`spctl --master-disable`), and no binary execution. | AST audit & packaging validator |
| `INV-SIG-03` | **Scan != Safe Enforcement**: The model and reports explicitly affirm `scan_proves_safe=False`, prohibiting the AI agent from claiming a signed binary is unconditionally safe. | Contract tests & model assertions |
| `INV-SIG-04` | **Cryptographic Origin & Team ID Attribution**: Extracts Developer Team Identifiers (10-char alphanumeric) and full CA chains for tamper-evident provenance tracking. | Unit tests & live benchmarks |
| `INV-SIG-05` | **Sensitive Path Privacy**: Custom application paths outside standard roots are handled safely without traversing personal file contents. | Secret leak scanner & unit tests |
| `INV-SIG-06` | **Graceful Non-Darwin Fallback**: On non-Darwin hosts (Linux, Windows, CI), delegates to `MockPlatformAdapter` returning simulated Apple Silicon signature profiles. | Mock & multi-platform tests |

---

## 3. Data Schema

### `SignatureStatus`
- `SIGNED_VALID`: Cryptographically signed with valid chain and intact seal.
- `SIGNED_INVALID`: Signature present but corrupted, modified, or expired.
- `UNSIGNED`: No code signature present.
- `ADHOC_SIGNED`: Ad-hoc signature without verified certificate authority.
- `UNKNOWN`: Unchecked or unsupported platform.

### `NotarizationStatus`
- `NOTARIZED_DEVELOPER_ID`: Notarized by Apple (`accepted source=Notarized Developer ID`).
- `APPLE_SYSTEM`: First-party Apple macOS core system binary (`accepted source=Apple System`).
- `MAC_APP_STORE`: Distributed via Mac App Store (`accepted source=Mac App Store`).
- `NOT_NOTARIZED`: Validly signed developer binary without Apple notarization ticket.
- `REJECTED`: Explicitly rejected by Gatekeeper policy.
- `NOT_APPLICABLE`: Unsigned or ad-hoc binary where notarization does not apply.
- `UNKNOWN`: Unassessed or unsupported platform.

### `SigningAuthorityType`
- `APPLE_SYSTEM`: First-party Apple Software Signing.
- `DEVELOPER_ID`: Apple Developer Program verified developer.
- `APP_STORE`: Mac App Store verified receipt.
- `ADHOC`: Ad-hoc local signature.
- `THIRD_PARTY_CA`: Custom enterprise certificate authority.
- `UNSIGNED`: Unsigned binary.
- `UNKNOWN`: Unverified.

### `MacAppSignatureInfo`
- `bundle_id`: str (e.g. `"com.google.Chrome"`)
- `bundle_path`: str (e.g. `"/Applications/Google Chrome.app"`)
- `executable_path`: Optional[str]
- `signature_status`: `SignatureStatus`
- `notarization_status`: `NotarizationStatus`
- `authority_type`: `SigningAuthorityType`
- `authorities`: List[str] (e.g. `["Developer ID Application: Google LLC (EQHXZ8M8AV)", "Developer ID Certification Authority", "Apple Root CA"]`)
- `team_id`: Optional[str] (e.g. `"EQHXZ8M8AV"`)
- `cdhash`: Optional[str] (CodeDirectory SHA-256 digest)
- `is_hardened_runtime`: bool (Whether hardened runtime flag is present)
- `is_apple`: bool (Whether signed by Apple Inc.)
- `is_valid`: bool (Whether strict code verification passed)
- `scan_proves_safe`: bool = False (Charter invariant: Scan != Safe)

### `MacAppSignatureReport`
- `collection_method`: str (`"NATIVE_DARWIN_CODESIGN"`, `"MOCK_PLATFORM_ADAPTER"`)
- `timestamp`: str (ISO 8601 UTC)
- `host_platform`: str
- `inspected_apps_count`: int
- `validly_signed_count`: int
- `notarized_count`: int
- `apple_system_count`: int
- `unsigned_count`: int
- `signatures`: List[MacAppSignatureInfo]
- `warnings`: List[str]
- `unavailable_telemetry`: List[str]

---

## 4. Query & Inspection Strategy

1. **Detailed Signature Extraction (`/usr/bin/codesign -dv --verbose=4 <path>`)**:
   - Parses stderr for `Identifier`, `Authority`, `TeamIdentifier`, `CDHash`, `CodeDirectory` flags (detecting `runtime`), and `Notarization Ticket=stapled`.
2. **Integrity Verification (`/usr/bin/codesign -v --strict <path>`)**:
   - Exit code 0 indicates sealed resources and code pages match signatures exactly.
3. **Gatekeeper Assessment (`/usr/sbin/spctl --assess --type execute --verbose <path>`)**:
   - Parses output to extract Gatekeeper acceptance verdict and source (`Notarized Developer ID`, `Apple System`, `Mac App Store`, `rejected`).
4. **Mock Execution for Testing & Non-Darwin Hosts**:
   - Supplies canonical Apple Silicon mock profiles for Apple first-party apps, identified developer apps (Google, Microsoft), and unsigned test fixtures.
