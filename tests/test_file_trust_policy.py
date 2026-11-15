"""Tests for File Trust States, Provenance Evidence, and Supported File-Handler Policy."""

from __future__ import annotations

import pytest

from system_mind.files.models import (
    FileCategory,
    FileEvidenceRecord,
    FileTrustEvaluation,
    FileTrustState,
    HandlerExecutionMode,
    deduce_file_category,
)
from system_mind.files.policy import FileTrustPolicyEvaluator


def test_file_category_deduction():
    """Verify accurate deduction of FileCategory from extensions and MIME types."""
    assert deduce_file_category("payload.exe") == FileCategory.EXECUTABLE_BINARY
    assert deduce_file_category("libsample.dylib") == FileCategory.EXECUTABLE_BINARY
    assert deduce_file_category("unknown_binary", mime_type="application/x-mach-binary") == FileCategory.EXECUTABLE_BINARY

    assert deduce_file_category("setup.sh") == FileCategory.SCRIPT_OR_INTERPRETER_PAYLOAD
    assert deduce_file_category("script.py") == FileCategory.SCRIPT_OR_INTERPRETER_PAYLOAD
    assert deduce_file_category("tool.ps1") == FileCategory.SCRIPT_OR_INTERPRETER_PAYLOAD

    assert deduce_file_category("app.jar") == FileCategory.COMPILED_BYTECODE_PACKAGE
    assert deduce_file_category("module.wasm") == FileCategory.COMPILED_BYTECODE_PACKAGE

    assert deduce_file_category("invoice.pdf") == FileCategory.ACTIVE_DOCUMENT
    assert deduce_file_category("report.docm") == FileCategory.ACTIVE_DOCUMENT

    assert deduce_file_category("config.yaml") == FileCategory.SYSTEM_CONFIGURATION
    assert deduce_file_category("settings.plist") == FileCategory.SYSTEM_CONFIGURATION

    assert deduce_file_category("archive.zip") == FileCategory.ARCHIVE_CONTAINER
    assert deduce_file_category("bundle.tar.gz") == FileCategory.ARCHIVE_CONTAINER

    assert deduce_file_category("notes.txt") == FileCategory.PASSIVE_DOCUMENT_DATA
    assert deduce_file_category("data.csv") == FileCategory.PASSIVE_DOCUMENT_DATA


def test_trust_state_evaluation_hierarchy():
    """Verify deterministic resolution of FileTrustState based on provenance evidence."""
    # 1. Unknown untracked file
    rec_unknown = FileEvidenceRecord(
        file_path="/Users/user/Downloads/random.dat",
        sha256_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        file_size_bytes=1024,
        mime_type="application/octet-stream",
        category=FileCategory.PASSIVE_DOCUMENT_DATA,
    )
    assert FileTrustPolicyEvaluator.evaluate_trust_state(rec_unknown) == FileTrustState.UNTRUSTED_UNKNOWN

    # 2. Quarantined file
    rec_quarantine = FileEvidenceRecord(
        file_path="/Users/user/Downloads/invoice.pdf",
        sha256_hash="aaaabbbbccccdddd1111222233334444555566667777888899990000aaaabbbb",
        file_size_bytes=4096,
        mime_type="application/pdf",
        category=FileCategory.ACTIVE_DOCUMENT,
        has_quarantine_marker=True,
    )
    assert FileTrustPolicyEvaluator.evaluate_trust_state(rec_quarantine) == FileTrustState.QUARANTINED

    # 3. Statically inspected file (Scan != Safe)
    rec_static = FileEvidenceRecord(
        file_path="/Users/user/Downloads/tool.sh",
        sha256_hash="1111222233334444555566667777888899990000aaaabbbbccccdddd11112222",
        file_size_bytes=2048,
        mime_type="text/x-shellscript",
        category=FileCategory.SCRIPT_OR_INTERPRETER_PAYLOAD,
        static_scan_clean=True,
    )
    assert FileTrustPolicyEvaluator.evaluate_trust_state(rec_static) == FileTrustState.STATICALLY_INSPECTED

    # 4. Sandbox verified file
    rec_sandbox = FileEvidenceRecord(
        file_path="/Users/user/Downloads/untrusted_app",
        sha256_hash="222233334444555566667777888899990000aaaabbbbccccdddd111122223333",
        file_size_bytes=1048576,
        mime_type="application/x-executable",
        category=FileCategory.EXECUTABLE_BINARY,
        sandbox_trace_clean=True,
    )
    assert FileTrustPolicyEvaluator.evaluate_trust_state(rec_sandbox) == FileTrustState.SANDBOX_VERIFIED

    # 5. Vendor signed verified file
    rec_vendor = FileEvidenceRecord(
        file_path="/Applications/VerifiedApp.app/Contents/MacOS/VerifiedApp",
        sha256_hash="33334444555566667777888899990000aaaabbbbccccdddd1111222233334444",
        file_size_bytes=5242880,
        mime_type="application/x-mach-binary",
        category=FileCategory.EXECUTABLE_BINARY,
        code_signature_valid=True,
        signature_vendor="Apple Developer ID: Valid Software Ltd.",
    )
    assert FileTrustPolicyEvaluator.evaluate_trust_state(rec_vendor) == FileTrustState.VENDOR_SIGNED_VERIFIED

    # 6. Immutable system core
    rec_sys = FileEvidenceRecord(
        file_path="/System/Library/CoreServices/Finder.app/Contents/MacOS/Finder",
        sha256_hash="4444555566667777888899990000aaaabbbbccccdddd11112222333344445555",
        file_size_bytes=8388608,
        mime_type="application/x-mach-binary",
        category=FileCategory.EXECUTABLE_BINARY,
        is_system_path=True,
        is_read_only_mount=True,
        code_signature_valid=True,
    )
    assert FileTrustPolicyEvaluator.evaluate_trust_state(rec_sys) == FileTrustState.SYSTEM_CORE_IMMUTABLE

    # 7. System path spoofing attempt (writable mount or missing signature)
    rec_spoofed = FileEvidenceRecord(
        file_path="/System/Library/CoreServices/SpoofedBinary",
        sha256_hash="555566667777888899990000aaaabbbbccccdddd111122223333444455556666",
        file_size_bytes=1024,
        mime_type="application/x-mach-binary",
        category=FileCategory.EXECUTABLE_BINARY,
        is_system_path=True,
        is_read_only_mount=False,  # Not read-only!
        code_signature_valid=False,
    )
    assert FileTrustPolicyEvaluator.evaluate_trust_state(rec_spoofed) == FileTrustState.BLOCKED_MALICIOUS

    # 8. Known malicious hash
    rec_malicious = FileEvidenceRecord(
        file_path="/Users/user/Downloads/trojan.exe",
        sha256_hash="66667777888899990000aaaabbbbccccdddd1111222233334444555566667777",
        file_size_bytes=512,
        mime_type="application/x-dosexec",
        category=FileCategory.EXECUTABLE_BINARY,
        is_known_malicious=True,
    )
    assert FileTrustPolicyEvaluator.evaluate_trust_state(rec_malicious) == FileTrustState.BLOCKED_MALICIOUS


def test_scan_does_not_prove_safety_invariant():
    """Verify that static_scan_clean NEVER authorizes native host execution."""
    evidence = FileEvidenceRecord(
        file_path="/Users/user/Downloads/clean_looking_script.sh",
        sha256_hash="abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
        file_size_bytes=1024,
        mime_type="text/x-shellscript",
        category=FileCategory.SCRIPT_OR_INTERPRETER_PAYLOAD,
        static_scan_clean=True,  # Scan indicates clean!
    )

    eval_result = FileTrustPolicyEvaluator.validate_handler_request(
        evidence=evidence,
        requested_mode=HandlerExecutionMode.NATIVE_HOST_EXECUTION,
        user_approved=False,
    )

    assert eval_result.permitted is False
    assert eval_result.is_native_execution_allowed is False
    assert any("ScanDoesNotProveSafetyViolation" in v for v in eval_result.violations)
    assert HandlerExecutionMode.NATIVE_HOST_EXECUTION not in eval_result.allowed_handler_modes
    assert HandlerExecutionMode.DISPOSABLE_SANDBOX_EXECUTION in eval_result.allowed_handler_modes


def test_quarantine_blocks_native_execution():
    """Verify that quarantined files cannot execute natively on host."""
    evidence = FileEvidenceRecord(
        file_path="/Users/user/Downloads/downloaded_app.zip",
        sha256_hash="1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        file_size_bytes=2048,
        mime_type="application/zip",
        category=FileCategory.ARCHIVE_CONTAINER,
        has_quarantine_marker=True,
    )

    eval_result = FileTrustPolicyEvaluator.validate_handler_request(
        evidence=evidence,
        requested_mode=HandlerExecutionMode.NATIVE_HOST_EXECUTION,
    )

    assert eval_result.permitted is False
    assert any("QuarantineActiveViolation" in v for v in eval_result.violations)
    assert eval_result.max_execution_mode == HandlerExecutionMode.STATIC_PARSER_ONLY


def test_blocked_malicious_denies_all_handlers():
    """Verify that known malicious files are denied all handlers including static parsers."""
    evidence = FileEvidenceRecord(
        file_path="/tmp/malware.exe",
        sha256_hash="badf00dbadf00dbadf00dbadf00dbadf00dbadf00dbadf00dbadf00dbadf00d",
        file_size_bytes=4096,
        mime_type="application/x-executable",
        category=FileCategory.EXECUTABLE_BINARY,
        is_known_malicious=True,
    )

    eval_result = FileTrustPolicyEvaluator.validate_handler_request(
        evidence=evidence,
        requested_mode=HandlerExecutionMode.STATIC_PARSER_ONLY,
    )

    assert eval_result.permitted is False
    assert eval_result.allowed_handler_modes == [HandlerExecutionMode.DENIED]
    assert any("MaliciousFileBlockedViolation" in v for v in eval_result.violations)


def test_executable_binary_confinement():
    """Verify containment states for executable binaries across trust progression."""
    # Untrusted binary: All handler modes denied
    rec_untrusted = FileEvidenceRecord(
        file_path="/tmp/unknown_binary",
        sha256_hash="1111111111111111111111111111111111111111111111111111111111111111",
        file_size_bytes=2048,
        mime_type="application/x-executable",
        category=FileCategory.EXECUTABLE_BINARY,
    )
    res_untrusted = FileTrustPolicyEvaluator.validate_handler_request(
        evidence=rec_untrusted,
        requested_mode=HandlerExecutionMode.STATIC_PARSER_ONLY,
    )
    assert res_untrusted.permitted is False
    assert res_untrusted.allowed_handler_modes == [HandlerExecutionMode.DENIED]

    # Sandbox verified binary: Allowed DISPOSABLE_SANDBOX_EXECUTION, denied native
    rec_sandboxed = FileEvidenceRecord(
        file_path="/tmp/sandboxed_binary",
        sha256_hash="2222222222222222222222222222222222222222222222222222222222222222",
        file_size_bytes=2048,
        mime_type="application/x-executable",
        category=FileCategory.EXECUTABLE_BINARY,
        sandbox_trace_clean=True,
    )
    res_sandbox = FileTrustPolicyEvaluator.validate_handler_request(
        evidence=rec_sandboxed,
        requested_mode=HandlerExecutionMode.DISPOSABLE_SANDBOX_EXECUTION,
    )
    assert res_sandbox.permitted is True
    assert res_sandbox.is_native_execution_allowed is False

    # Vendor signed binary: Allowed NATIVE_HOST_EXECUTION
    rec_vendor = FileEvidenceRecord(
        file_path="/Applications/VendorApp",
        sha256_hash="3333333333333333333333333333333333333333333333333333333333333333",
        file_size_bytes=2048,
        mime_type="application/x-executable",
        category=FileCategory.EXECUTABLE_BINARY,
        code_signature_valid=True,
        signature_vendor="Verified Developer ID",
    )
    res_vendor = FileTrustPolicyEvaluator.validate_handler_request(
        evidence=rec_vendor,
        requested_mode=HandlerExecutionMode.NATIVE_HOST_EXECUTION,
    )
    assert res_vendor.permitted is True
    assert res_vendor.is_native_execution_allowed is True


def test_script_user_attestation_and_approval_requirement():
    """Verify that user-attested scripts require explicit user_approved=True for native execution."""
    rec_script = FileEvidenceRecord(
        file_path="/Users/user/workspace/build.py",
        sha256_hash="4444444444444444444444444444444444444444444444444444444444444444",
        file_size_bytes=1024,
        mime_type="text/x-python",
        category=FileCategory.SCRIPT_OR_INTERPRETER_PAYLOAD,
        user_attestation=True,
    )

    # Without explicit user approval confirmation
    res_unapproved = FileTrustPolicyEvaluator.validate_handler_request(
        evidence=rec_script,
        requested_mode=HandlerExecutionMode.NATIVE_HOST_EXECUTION,
        user_approved=False,
    )
    assert res_unapproved.permitted is False
    assert any("UserApprovalRequiredViolation" in v for v in res_unapproved.violations)

    # With explicit user approval confirmation
    res_approved = FileTrustPolicyEvaluator.validate_handler_request(
        evidence=rec_script,
        requested_mode=HandlerExecutionMode.NATIVE_HOST_EXECUTION,
        user_approved=True,
    )
    assert res_approved.permitted is True
    assert res_approved.is_native_execution_allowed is True


def test_active_document_isolation():
    """Verify that active documents with macros cannot be opened by unconfined handlers."""
    evidence = FileEvidenceRecord(
        file_path="/Users/user/Documents/macro_sheet.xlsm",
        sha256_hash="5555555555555555555555555555555555555555555555555555555555555555",
        file_size_bytes=8192,
        mime_type="application/vnd.ms-excel.sheet.macroEnabled.12",
        category=FileCategory.ACTIVE_DOCUMENT,
        static_scan_clean=True,
    )

    # Hardened viewer is allowed
    res_viewer = FileTrustPolicyEvaluator.validate_handler_request(
        evidence=evidence,
        requested_mode=HandlerExecutionMode.HARDENED_ISOLATED_VIEWER,
    )
    assert res_viewer.permitted is True

    # Native unconfined execution is denied
    res_native = FileTrustPolicyEvaluator.validate_handler_request(
        evidence=evidence,
        requested_mode=HandlerExecutionMode.NATIVE_HOST_EXECUTION,
    )
    assert res_native.permitted is False
    assert any("HandlerModeDisallowedViolation" in v for v in res_native.violations)
