"""Deterministic policy evaluation engine for File Trust States and Supported File Handlers."""

from __future__ import annotations

from typing import List, Optional

from system_mind.files.models import (
    FileCategory,
    FileEvidenceRecord,
    FileTrustEvaluation,
    FileTrustState,
    HandlerExecutionMode,
)


class FileTrustPolicyEvaluator:
    """Independent deterministic policy evaluator governing file trust states and handler confinement."""

    _MODE_HIERARCHY = {
        HandlerExecutionMode.DENIED: 0,
        HandlerExecutionMode.STATIC_PARSER_ONLY: 1,
        HandlerExecutionMode.HARDENED_ISOLATED_VIEWER: 2,
        HandlerExecutionMode.DISPOSABLE_SANDBOX_EXECUTION: 3,
        HandlerExecutionMode.NATIVE_HOST_EXECUTION: 4,
    }

    @classmethod
    def evaluate_trust_state(cls, evidence: FileEvidenceRecord) -> FileTrustState:
        """Deterministically derive the FileTrustState from cryptographic provenance and evidence."""
        # 1. Malicious hash or known exploit
        if evidence.is_known_malicious:
            return FileTrustState.BLOCKED_MALICIOUS

        # 2. System path check with anti-spoofing verification
        if evidence.is_system_path:
            # Spoofing check: Must be on read-only mount and have valid OS vendor signature
            if not (evidence.is_read_only_mount and evidence.code_signature_valid):
                return FileTrustState.BLOCKED_MALICIOUS
            return FileTrustState.SYSTEM_CORE_IMMUTABLE

        # 3. Active quarantine markers take precedence over unverified execution
        if evidence.has_quarantine_marker:
            return FileTrustState.QUARANTINED

        # 4. User attestation (explicit human acceptance)
        if evidence.user_attestation:
            return FileTrustState.USER_ATTESTED

        # 5. Verified vendor cryptographic signature
        if evidence.code_signature_valid and evidence.signature_vendor:
            return FileTrustState.VENDOR_SIGNED_VERIFIED

        # 6. Isolated sandbox detonation verified clean
        if evidence.sandbox_trace_clean:
            return FileTrustState.SANDBOX_VERIFIED

        # 7. Static vulnerability and heuristic scan clean
        if evidence.static_scan_clean:
            return FileTrustState.STATICALLY_INSPECTED

        # Default fallback
        return FileTrustState.UNTRUSTED_UNKNOWN

    @classmethod
    def get_allowed_handler_modes(
        cls,
        category: FileCategory,
        trust_state: FileTrustState,
    ) -> List[HandlerExecutionMode]:
        """Return the allowed handler execution modes for a category and trust state."""
        # Blocked files cannot be opened by any handler
        if trust_state == FileTrustState.BLOCKED_MALICIOUS:
            return [HandlerExecutionMode.DENIED]

        # Passive documents and configuration files
        if category in {FileCategory.PASSIVE_DOCUMENT_DATA, FileCategory.SYSTEM_CONFIGURATION}:
            if trust_state in {FileTrustState.UNTRUSTED_UNKNOWN, FileTrustState.QUARANTINED}:
                return [HandlerExecutionMode.STATIC_PARSER_ONLY]
            return [
                HandlerExecutionMode.STATIC_PARSER_ONLY,
                HandlerExecutionMode.HARDENED_ISOLATED_VIEWER,
            ]

        # Active documents (macros, dynamic scripting in PDFs/Office)
        if category == FileCategory.ACTIVE_DOCUMENT:
            if trust_state in {FileTrustState.UNTRUSTED_UNKNOWN, FileTrustState.QUARANTINED}:
                return [HandlerExecutionMode.DENIED]
            if trust_state == FileTrustState.STATICALLY_INSPECTED:
                return [
                    HandlerExecutionMode.HARDENED_ISOLATED_VIEWER,
                    HandlerExecutionMode.DISPOSABLE_SANDBOX_EXECUTION,
                ]
            return [
                HandlerExecutionMode.HARDENED_ISOLATED_VIEWER,
                HandlerExecutionMode.DISPOSABLE_SANDBOX_EXECUTION,
            ]

        # Scripts and interpreter payloads
        if category in {FileCategory.SCRIPT_OR_INTERPRETER_PAYLOAD, FileCategory.COMPILED_BYTECODE_PACKAGE}:
            if trust_state in {FileTrustState.UNTRUSTED_UNKNOWN, FileTrustState.QUARANTINED}:
                return [HandlerExecutionMode.STATIC_PARSER_ONLY]
            if trust_state in {FileTrustState.STATICALLY_INSPECTED, FileTrustState.SANDBOX_VERIFIED}:
                return [
                    HandlerExecutionMode.STATIC_PARSER_ONLY,
                    HandlerExecutionMode.DISPOSABLE_SANDBOX_EXECUTION,
                ]
            if trust_state == FileTrustState.USER_ATTESTED:
                return [
                    HandlerExecutionMode.STATIC_PARSER_ONLY,
                    HandlerExecutionMode.DISPOSABLE_SANDBOX_EXECUTION,
                    HandlerExecutionMode.NATIVE_HOST_EXECUTION,
                ]
            if trust_state in {FileTrustState.VENDOR_SIGNED_VERIFIED, FileTrustState.SYSTEM_CORE_IMMUTABLE}:
                return [
                    HandlerExecutionMode.STATIC_PARSER_ONLY,
                    HandlerExecutionMode.DISPOSABLE_SANDBOX_EXECUTION,
                    HandlerExecutionMode.NATIVE_HOST_EXECUTION,
                ]

        # Executable native binaries
        if category == FileCategory.EXECUTABLE_BINARY:
            if trust_state in {
                FileTrustState.UNTRUSTED_UNKNOWN,
                FileTrustState.QUARANTINED,
                FileTrustState.STATICALLY_INSPECTED,
            }:
                return [HandlerExecutionMode.DENIED]
            if trust_state == FileTrustState.SANDBOX_VERIFIED:
                return [HandlerExecutionMode.DISPOSABLE_SANDBOX_EXECUTION]
            if trust_state == FileTrustState.USER_ATTESTED:
                return [
                    HandlerExecutionMode.DISPOSABLE_SANDBOX_EXECUTION,
                    HandlerExecutionMode.NATIVE_HOST_EXECUTION,
                ]
            if trust_state in {FileTrustState.VENDOR_SIGNED_VERIFIED, FileTrustState.SYSTEM_CORE_IMMUTABLE}:
                return [
                    HandlerExecutionMode.DISPOSABLE_SANDBOX_EXECUTION,
                    HandlerExecutionMode.NATIVE_HOST_EXECUTION,
                ]

        # Archive containers
        if category == FileCategory.ARCHIVE_CONTAINER:
            if trust_state in {FileTrustState.UNTRUSTED_UNKNOWN, FileTrustState.QUARANTINED}:
                return [HandlerExecutionMode.STATIC_PARSER_ONLY]
            return [
                HandlerExecutionMode.STATIC_PARSER_ONLY,
                HandlerExecutionMode.DISPOSABLE_SANDBOX_EXECUTION,
            ]

        # Fail-safe default
        return [HandlerExecutionMode.DENIED]

    @classmethod
    def validate_handler_request(
        cls,
        evidence: FileEvidenceRecord,
        requested_mode: HandlerExecutionMode,
        user_approved: bool = False,
    ) -> FileTrustEvaluation:
        """Validate an intended file handling or execution mode against safety invariants."""
        violations: List[str] = []
        warnings: List[str] = []

        trust_state = cls.evaluate_trust_state(evidence)
        allowed_modes = cls.get_allowed_handler_modes(evidence.category, trust_state)

        # Compute max permitted execution mode
        max_mode = max(allowed_modes, key=lambda m: cls._MODE_HIERARCHY.get(m, 0))

        # Invariant 1: Malicious files blocked completely
        if trust_state == FileTrustState.BLOCKED_MALICIOUS:
            violations.append(
                f"MaliciousFileBlockedViolation: File '{evidence.file_path}' (hash: {evidence.sha256_hash}) "
                "is flagged as malicious or forged. All operations are strictly denied."
            )

        # Invariant 2: "Scan != Safe" Invariant
        if (
            requested_mode == HandlerExecutionMode.NATIVE_HOST_EXECUTION
            and trust_state == FileTrustState.STATICALLY_INSPECTED
        ):
            violations.append(
                f"ScanDoesNotProveSafetyViolation: File '{evidence.file_path}' has passed static inspection, "
                "but static scans never grant native host execution permissions."
            )

        # Invariant 3: Quarantine Containment Invariant
        if evidence.has_quarantine_marker and requested_mode == HandlerExecutionMode.NATIVE_HOST_EXECUTION:
            violations.append(
                f"QuarantineActiveViolation: File '{evidence.file_path}' carries active quarantine attributes. "
                "Native host execution is prohibited while in quarantine."
            )

        # Invariant 4: Mode Permission Check
        if requested_mode not in allowed_modes:
            violations.append(
                f"HandlerModeDisallowedViolation: Requested execution mode {requested_mode.value} is not "
                f"permitted for category {evidence.category.value} under trust state {trust_state.value}."
            )

        # Invariant 5: Native Host Execution Gating
        if requested_mode == HandlerExecutionMode.NATIVE_HOST_EXECUTION:
            if trust_state == FileTrustState.USER_ATTESTED and not user_approved:
                violations.append(
                    f"UserApprovalRequiredViolation: Native host execution of user-attested file '{evidence.file_path}' "
                    "requires explicit human consent (user_approved=True)."
                )
            elif trust_state not in {
                FileTrustState.SYSTEM_CORE_IMMUTABLE,
                FileTrustState.VENDOR_SIGNED_VERIFIED,
                FileTrustState.USER_ATTESTED,
            }:
                violations.append(
                    f"UnverifiedNativeExecutionViolation: Native host execution is strictly restricted to "
                    "SYSTEM_CORE_IMMUTABLE, VENDOR_SIGNED_VERIFIED, or USER_ATTESTED states."
                )

        permitted = len(violations) == 0
        is_native_allowed = HandlerExecutionMode.NATIVE_HOST_EXECUTION in allowed_modes and permitted

        return FileTrustEvaluation(
            file_path=evidence.file_path,
            sha256_hash=evidence.sha256_hash,
            trust_state=trust_state,
            category=evidence.category,
            allowed_handler_modes=allowed_modes,
            max_execution_mode=max_mode,
            is_native_execution_allowed=is_native_allowed,
            permitted=permitted,
            violations=violations,
            warnings=warnings,
        )
