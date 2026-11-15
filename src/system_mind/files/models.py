"""Data models, enums, and evidence contracts for File Trust States and Handler Policies."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Set


class FileTrustState(str, Enum):
    """Discrete, deterministic trust states of a file in SYSTEM MIND X."""

    UNTRUSTED_UNKNOWN = "UNTRUSTED_UNKNOWN"
    QUARANTINED = "QUARANTINED"
    STATICALLY_INSPECTED = "STATICALLY_INSPECTED"
    SANDBOX_VERIFIED = "SANDBOX_VERIFIED"
    USER_ATTESTED = "USER_ATTESTED"
    VENDOR_SIGNED_VERIFIED = "VENDOR_SIGNED_VERIFIED"
    SYSTEM_CORE_IMMUTABLE = "SYSTEM_CORE_IMMUTABLE"
    BLOCKED_MALICIOUS = "BLOCKED_MALICIOUS"


class FileCategory(str, Enum):
    """Classification of file content and execution potential."""

    EXECUTABLE_BINARY = "EXECUTABLE_BINARY"
    SCRIPT_OR_INTERPRETER_PAYLOAD = "SCRIPT_OR_INTERPRETER_PAYLOAD"
    COMPILED_BYTECODE_PACKAGE = "COMPILED_BYTECODE_PACKAGE"
    ACTIVE_DOCUMENT = "ACTIVE_DOCUMENT"
    PASSIVE_DOCUMENT_DATA = "PASSIVE_DOCUMENT_DATA"
    SYSTEM_CONFIGURATION = "SYSTEM_CONFIGURATION"
    ARCHIVE_CONTAINER = "ARCHIVE_CONTAINER"


class HandlerExecutionMode(str, Enum):
    """Execution containment levels for opening or handling a file."""

    DENIED = "DENIED"
    STATIC_PARSER_ONLY = "STATIC_PARSER_ONLY"
    HARDENED_ISOLATED_VIEWER = "HARDENED_ISOLATED_VIEWER"
    DISPOSABLE_SANDBOX_EXECUTION = "DISPOSABLE_SANDBOX_EXECUTION"
    NATIVE_HOST_EXECUTION = "NATIVE_HOST_EXECUTION"


@dataclass(frozen=True)
class FileEvidenceRecord:
    """Cryptographic provenance and security telemetry associated with a file."""

    file_path: str
    sha256_hash: str
    file_size_bytes: int
    mime_type: str
    category: FileCategory
    has_quarantine_marker: bool = False
    origin_url: Optional[str] = None
    is_known_malicious: bool = False
    static_scan_clean: bool = False
    sandbox_trace_clean: bool = False
    code_signature_valid: bool = False
    signature_vendor: Optional[str] = None
    is_system_path: bool = False
    is_read_only_mount: bool = False
    user_attestation: bool = False


@dataclass
class FileTrustEvaluation:
    """Outcome of file trust evaluation and handler policy validation."""

    file_path: str
    sha256_hash: str
    trust_state: FileTrustState
    category: FileCategory
    allowed_handler_modes: List[HandlerExecutionMode]
    max_execution_mode: HandlerExecutionMode
    is_native_execution_allowed: bool
    permitted: bool
    violations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def deduce_file_category(file_path: str, mime_type: str = "") -> FileCategory:
    """Deduce FileCategory from file extension and optional MIME type."""
    ext = file_path.lower().split(".")[-1] if "." in file_path else ""

    # Executable binaries
    if ext in {"exe", "dll", "dylib", "so", "bin", "elf", "macho"} or mime_type in {
        "application/x-mach-binary",
        "application/x-executable",
        "application/x-dosexec",
        "application/x-sharedlib",
    }:
        return FileCategory.EXECUTABLE_BINARY

    # Scripts / interpreter payloads
    if ext in {"sh", "bash", "zsh", "py", "js", "ts", "ps1", "bat", "cmd", "rb", "php", "pl"} or mime_type in {
        "text/x-shellscript",
        "text/x-python",
        "application/javascript",
        "application/x-powershell",
    }:
        return FileCategory.SCRIPT_OR_INTERPRETER_PAYLOAD

    # Compiled bytecode or installer packages
    if ext in {"jar", "pyc", "class", "wasm", "pkg", "msi", "deb", "rpm", "apk"} or mime_type in {
        "application/java-archive",
        "application/wasm",
        "application/x-msi",
        "application/x-debian-package",
    }:
        return FileCategory.COMPILED_BYTECODE_PACKAGE

    # Active documents (macros / dynamic scripting)
    if ext in {"docm", "xlsm", "pptm", "pdf", "html", "htm"}:
        return FileCategory.ACTIVE_DOCUMENT

    # System configs
    if ext in {"conf", "ini", "yaml", "yml", "plist", "toml", "env"}:
        return FileCategory.SYSTEM_CONFIGURATION

    # Archive containers
    if ext in {"zip", "tar", "gz", "tgz", "7z", "bz2", "xz", "iso", "dmg"} or mime_type in {
        "application/zip",
        "application/x-tar",
        "application/gzip",
        "application/x-7z-compressed",
    }:
        return FileCategory.ARCHIVE_CONTAINER

    # Default to passive document/data
    return FileCategory.PASSIVE_DOCUMENT_DATA
