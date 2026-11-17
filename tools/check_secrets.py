#!/usr/bin/env python3
"""Secret scanner and credential leak detector for SYSTEM MIND X.

Scans the repository for:
1. Accidental committed .env or credential files (.pem, .key, .pfx, id_rsa).
2. Known high-entropy API key patterns and private key blocks in tracked source files.

Invariants:
- SC-01: Zero ambient shell execution.
- Charter: Never store secrets, tokens, or private keys in logs or version control.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

# Ensure src/ is on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))

from system_mind.config.secrets import SecretLeakDetector

EXCLUDED_DIRS = {
    ".git",
    ".pytest_cache",
    ".venv",
    "venv",
    "target",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
}

BANNED_FILE_EXTENSIONS = {
    ".pem",
    ".key",
    ".pfx",
    ".p12",
    ".keystore",
    ".jks",
}

IGNORED_SCAN_FILES = {
    ".env.example",  # Example template is intentionally public
    "secrets.py",    # Contains pattern definitions
    "test_environment_config.py",  # Contains test token samples
    "test_audit_ledger.py",        # Contains test token samples for redaction tests
    "test_api_conventions.py",     # Contains test token samples for redaction tests
    "test_e2e_governance_session.py",
    "test_integration_pipeline.py",
    "test_structured_logging.py",   # Contains test token samples for redaction tests
    "test_macos_privacy_filter.py", # Contains test token samples for redaction tests
    "logging_config.py",           # Contains test token samples for validator audit
    "macos_privacy.py",            # Contains test token samples for validator audit
    "detect_privacy_filter.py",    # Contains test token samples for privacy demonstration
    "test_macos_collectors_unit.py", # Contains test token samples for redaction tests
}


def scan_repository_for_secrets(root: Path, verbose: bool = False) -> tuple[int, list[str]]:
    """Scans all repository files for prohibited secret files and credential patterns."""
    violations: list[str] = []
    scanned_file_count = 0

    for path in root.rglob("*"):
        if path.is_dir():
            continue

        # Skip excluded directories
        rel_parts = path.relative_to(root).parts
        if any(part in EXCLUDED_DIRS for part in rel_parts):
            continue

        rel_path_str = str(path.relative_to(root))

        # 1. Prohibited secret file check
        if path.name == ".env" or path.name.startswith(".env.") and path.name != ".env.example":
            violations.append(f"BANNED SECRET FILE DETECTED: '{rel_path_str}' must not be present or committed.")

        if path.suffix.lower() in BANNED_FILE_EXTENSIONS:
            violations.append(f"BANNED CREDENTIAL FILE DETECTED: '{rel_path_str}' (extension: {path.suffix})")

        if path.name.startswith("id_rsa") or path.name.startswith("id_ed25519"):
            violations.append(f"BANNED PRIVATE KEY FILE DETECTED: '{rel_path_str}'")

        # 2. Skip files known to contain test regexes
        if path.name in IGNORED_SCAN_FILES:
            continue

        # 3. Text content scanning
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
            scanned_file_count += 1
            findings = SecretLeakDetector.detect_secrets_in_text(content)
            for finding in findings:
                violations.append(f"{rel_path_str}: {finding}")
        except Exception:
            # Binary file or unreadable, ignore
            pass

    return scanned_file_count, violations


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SYSTEM MIND X Secret Leak Scanner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--path", type=str, default=str(ROOT_DIR), help="Root directory to scan")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()
    scan_root = Path(args.path).resolve()

    print(f"[*] SYSTEM MIND X — Secret Leak Scanner")
    print(f"[*] Scanning directory: {scan_root}")

    file_count, violations = scan_repository_for_secrets(scan_root, verbose=args.verbose)

    print(f"[*] Scanned {file_count} text files.")
    if violations:
        print(f"\n[!] VIOLATIONS DETECTED: {len(violations)} secret leak(s) found:", file=sys.stderr)
        for v in violations:
            print(f"    - {v}", file=sys.stderr)
        return 1

    print("[+] Zero secret leaks detected. Repository complies with secret-handling conventions.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
